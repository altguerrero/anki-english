"""Exercise the real HTTP adapter and CLI against a local AnkiConnect test server."""

from contextlib import redirect_stdout, redirect_stderr
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import io
import json
from pathlib import Path
import tempfile
from threading import Thread
import unittest
from unittest.mock import patch

from anki_english.anki import AnkiConnect, AnkiError
from anki_english.audio import AudioError
from anki_english.cli import main
from anki_english.compiler import compile_card, FIELDS
from anki_english.config import AnkiConfig
from anki_english.service import publish
from anki_english.spec import SentenceChunk
from test_compiler import example, ROOT


class State:
    def __init__(self):
        self.model = None
        self.decks = []
        self.notes = {}
        self.calls = []
        self.fail_add = None
        self.fail_style = False
        self.mode = "normal"

    def invoke(self, action, params):
        if action == "version": return 6
        if action == "modelNames": return [self.model["modelName"]] if self.model else []
        if action == "deckNames": return self.decks
        if action == "createModel":
            self.model = params
            return {"id": 1, "type": 1}
        if action == "modelFieldNames": return self.model["inOrderFields"]
        if action == "modelTemplates":
            return {t["Name"]: {"Front": t["Front"], "Back": t["Back"]} for t in self.model["cardTemplates"]}
        if action == "modelStyling": return {"css": self.model["css"]}
        if action == "updateModelTemplates":
            for template in self.model["cardTemplates"]:
                template.update(params["model"]["templates"].get(template["Name"], {}))
            return None
        if action == "updateModelStyling":
            if self.fail_style: raise ValueError("simulated styling failure")
            self.model["css"] = params["model"]["css"]
            return None
        if action == "createDeck":
            if params["deck"] not in self.decks: self.decks.append(params["deck"])
            return 1
        if action == "findNotes":
            uid = params["query"].removeprefix("UID:")
            return [self.notes[uid][0]] if uid in self.notes else []
        if action == "storeMediaFile": return params["filename"]
        if action == "addNote":
            uid = params["note"]["fields"]["UID"]
            if uid == self.fail_add: raise ValueError("simulated write failure")
            if uid in self.notes: raise ValueError("duplicate")
            note_id = len(self.notes) + 100
            self.notes[uid] = (note_id, params["note"])
            return note_id
        raise ValueError(f"unexpected action: {action}")


class IntegrationTests(unittest.TestCase):
    def setUp(self):
        self.state = State()
        state = self.state

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args): pass

            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                state.calls.append(body)
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                if state.mode == "malformed":
                    self.wfile.write(b'{"result":6}')
                    return
                try:
                    result = {"result": state.invoke(body["action"], body["params"]), "error": None}
                except ValueError as error:
                    result = {"result": None, "error": str(error)}
                self.wfile.write(json.dumps(result).encode())

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.config = AnkiConfig(endpoint=f"http://127.0.0.1:{self.server.server_port}")
        self.gateway = AnkiConnect(self.config, key="test-key")
        self.temp = tempfile.TemporaryDirectory()
        self.config_path = Path(self.temp.name) / "config.toml"
        self.config_path.write_text(f'[anki]\nendpoint = "{self.config.endpoint}"\n')

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.temp.cleanup()

    def cli(self, *args):
        out = io.StringIO()
        with redirect_stdout(out), redirect_stderr(out):
            code = main(["--config", str(self.config_path), *args])
        return code, out.getvalue()

    def test_init_is_idempotent_and_creates_real_cloze_payload(self):
        self.gateway.initialize()
        self.gateway.initialize()
        self.assertTrue(self.state.model["isCloze"])
        self.assertEqual(self.state.model["inOrderFields"][0], "UID")
        self.assertEqual(sum(c["action"] == "createModel" for c in self.state.calls), 1)
        self.assertEqual(len(self.state.decks), 1)
        self.assertTrue(all(c["version"] == 6 and c["key"] == "test-key" for c in self.state.calls))

    def test_existing_incompatible_model_is_not_overwritten(self):
        self.gateway.initialize()
        self.state.model["inOrderFields"] = ["Front", "Back"]
        self.state.calls.clear()
        with self.assertRaises(AnkiError): self.gateway.initialize()
        self.assertFalse(any(c["action"].startswith("create") for c in self.state.calls))

    def test_changed_template_blocks_publication(self):
        self.gateway.initialize()
        self.state.model["cardTemplates"][0]["Front"] = "{{Sentence}}"
        with self.assertRaises(AnkiError): self.gateway.verify()

    def test_cli_import_and_retry_skip_all_duplicates(self):
        self.assertEqual(self.cli("init")[0], 0)
        self.assertEqual(self.cli("add", str(ROOT / "examples/cards.json"), "--no-audio", "--yes")[0], 0)
        self.assertEqual(len(self.state.notes), 2)
        for _, note in self.state.notes.values():
            self.assertFalse(note["options"]["allowDuplicate"])
            self.assertEqual(list(note["fields"]), FIELDS)
        code, output = self.cli("add", str(ROOT / "examples/cards.json"), "--no-audio", "--yes")
        self.assertEqual(code, 0)
        self.assertIn("Nothing to publish", output)
        self.assertEqual(len(self.state.notes), 2)

    def test_offline_dry_run_never_contacts_anki(self):
        code, output = self.cli("add", str(ROOT / "examples/cards.json"), "--dry-run")
        self.assertEqual(code, 0)
        self.assertEqual(self.state.calls, [])
        self.assertIn("Offline", output)

    def test_invalid_batch_has_no_network_side_effects(self):
        path = Path(self.temp.name) / "bad.json"
        path.write_text(json.dumps({"schema_version": "1.0", "cards": [example(), example(answer="missing")]}))
        self.assertEqual(self.cli("add", str(path), "--yes")[0], 1)
        self.assertEqual(self.state.calls, [])

    def test_cancel_does_not_generate_media_or_notes(self):
        self.gateway.initialize()
        with patch("sys.stdin.isatty", return_value=True), patch("builtins.input", return_value="n"):
            code, output = self.cli("add", str(ROOT / "examples/cards.json"))
        self.assertEqual(code, 0)
        self.assertIn("Cancelled", output)
        self.assertFalse(any(c["action"] in {"storeMediaFile", "addNote"} for c in self.state.calls))

    def test_partial_failure_then_retry_keeps_successes(self):
        self.gateway.initialize()
        cards = [compile_card(SentenceChunk.model_validate(data)) for data in
                 json.loads((ROOT / "examples/cards.json").read_text())["cards"]]
        self.state.fail_add = cards[1].uid
        first = publish(cards, self.gateway, None)
        self.assertEqual([r.status for r in first], ["added", "failed"])
        self.state.fail_add = None
        second = publish(cards, self.gateway, None)
        self.assertEqual([r.status for r in second], ["skipped", "added"])
        self.assertEqual(len(self.state.notes), 2)

    def test_audio_failure_does_not_publish_silent_note(self):
        self.gateway.initialize()
        class BrokenTTS:
            def synthesize(self, text): raise AudioError("broken TTS")
        result = publish([compile_card(SentenceChunk.model_validate(example()))], self.gateway, BrokenTTS())
        self.assertEqual(result[0].status, "failed")
        self.assertEqual(self.state.notes, {})

    def test_media_upload_precedes_note_and_uses_returned_filename(self):
        self.gateway.initialize()
        audio = Path(self.temp.name) / "eng_test.mp3"
        audio.write_bytes(b"fake-test-media")
        card = compile_card(SentenceChunk.model_validate(example()))
        self.gateway.add(card, audio)
        actions = [c["action"] for c in self.state.calls]
        self.assertLess(actions.index("storeMediaFile"), actions.index("addNote"))
        self.assertEqual(self.state.notes[card.uid][1]["fields"]["Audio"], "[sound:eng_test.mp3]")

    def test_malformed_response_rejected(self):
        self.state.mode = "malformed"
        with self.assertRaises(AnkiError): self.gateway.call("version")

    def test_style_update_backs_up_and_preserves_notes_and_template_name(self):
        self.gateway.initialize()
        card = compile_card(SentenceChunk.model_validate(example()))
        self.gateway.add(card, None)
        before = json.dumps(self.state.notes, sort_keys=True)
        self.state.model["cardTemplates"][0].update(Name="My existing card", Front="<p>{{cloze:Text}}</p>")
        self.state.model["css"] = "old CSS"
        backup = self.gateway.initialize(update_style=True, backup_dir=Path(self.temp.name))
        self.assertIsNotNone(backup)
        saved = json.loads(backup.read_text())
        self.assertEqual(saved["css"], "old CSS")
        self.assertEqual(saved["templates"]["My existing card"]["Front"], "<p>{{cloze:Text}}</p>")
        self.assertEqual(self.state.model["cardTemplates"][0]["Name"], "My existing card")
        self.assertEqual(json.dumps(self.state.notes, sort_keys=True), before)
        self.gateway.verify()
        self.state.calls.clear()
        self.assertIsNone(self.gateway.initialize(update_style=True, backup_dir=Path(self.temp.name)))
        self.assertFalse(any(c["action"].startswith("update") for c in self.state.calls))

    def test_style_update_rejects_incompatible_fields_before_mutation(self):
        self.gateway.initialize()
        self.state.model["inOrderFields"] = ["Front", "Back"]
        self.state.calls.clear()
        with self.assertRaises(AnkiError):
            self.gateway.initialize(update_style=True, backup_dir=Path(self.temp.name))
        self.assertFalse(any(c["action"].startswith("update") for c in self.state.calls))

    def test_style_failure_keeps_original_backup_and_retry_finishes(self):
        self.gateway.initialize()
        self.state.model["css"] = "original CSS"
        self.state.model["cardTemplates"][0]["Front"] = "<p>{{cloze:Text}}</p>"
        self.state.fail_style = True
        with self.assertRaisesRegex(AnkiError, "Previous design saved"):
            self.gateway.initialize(update_style=True, backup_dir=Path(self.temp.name))
        backups = list(Path(self.temp.name).glob("style-*.json"))
        self.assertEqual(len(backups), 1)
        self.assertEqual(json.loads(backups[0].read_text())["css"], "original CSS")
        self.state.fail_style = False
        self.gateway.initialize(update_style=True, backup_dir=Path(self.temp.name))
        self.gateway.verify()

    def test_style_backup_failure_prevents_writes(self):
        self.gateway.initialize()
        self.state.model["css"] = "original CSS"
        self.state.calls.clear()
        with patch("anki_english.anki.tempfile.NamedTemporaryFile", side_effect=OSError("disk full")):
            with self.assertRaises(OSError):
                self.gateway.initialize(update_style=True, backup_dir=Path(self.temp.name))
        self.assertFalse(any(c["action"].startswith("update") for c in self.state.calls))

    def test_init_cli_passes_explicit_update_style_flag(self):
        with patch("anki_english.cli.AnkiConnect") as client:
            client.return_value.initialize.return_value = None
            self.assertEqual(self.cli("init", "--update-style")[0], 0)
            client.return_value.initialize.assert_called_once_with(update_style=True)


if __name__ == "__main__":
    unittest.main()
