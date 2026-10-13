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

from anki_english.anki import AnkiConnect, AnkiError, AnkiRouter, templates
from anki_english.audio import AudioError
from anki_english.cli import main
from anki_english.compiler import compile_card, FIELDS, ERROR_FIELDS
from anki_english.config import AnkiConfig
from anki_english.service import publish
from anki_english.spec import SentenceChunk, CardBatch, MyError
from test_compiler import example, error_example, ROOT


class State:
    def __init__(self):
        self.models = {}
        self.decks = []
        self.notes = {}
        self.calls = []
        self.fail_add = None
        self.fail_style = False
        self.ignore_translation = False
        self.mode = "normal"

    @property
    def model(self):
        # Existing 02 tests continue to inspect the original model.
        return self.models.get(AnkiConfig().model)

    def invoke(self, action, params):
        model_name = params.get("modelName") or params.get("model", {}).get("name")
        model = self.models.get(model_name)
        if action == "version": return 6
        if action == "modelNames": return list(self.models)
        if action == "deckNames": return self.decks
        if action == "createModel":
            if model_name in self.models: raise ValueError("model already exists")
            self.models[model_name] = params
            return {"id": 1, "type": 1}
        if action == "modelFieldNames": return model["inOrderFields"]
        if action == "modelFieldAdd":
            field = params["fieldName"]
            if field in model["inOrderFields"]: raise ValueError("duplicate field")
            model["inOrderFields"].append(field)
            for _, note in self.notes.values():
                if note["modelName"] == model_name: note["fields"][field] = ""
            return None
        if action == "notesInfo":
            return [{"noteId": nid, "modelName": note["modelName"],
                     "fields": {k: {"value": v, "order": i} for i, (k, v) in enumerate(note["fields"].items())}}
                    for nid, note in self.notes.values() if nid in params["notes"]]
        if action == "updateNoteFields":
            if not self.ignore_translation:
                for nid, note in self.notes.values():
                    if nid == params["note"]["id"]: note["fields"].update(params["note"]["fields"])
            return None
        if action == "modelTemplates":
            return {t["Name"]: {"Front": t["Front"], "Back": t["Back"]} for t in model["cardTemplates"]}
        if action == "modelStyling": return {"css": model["css"]}
        if action == "updateModelTemplates":
            for template in model["cardTemplates"]:
                template.update(params["model"]["templates"].get(template["Name"], {}))
            return None
        if action == "updateModelStyling":
            if self.fail_style: raise ValueError("simulated styling failure")
            model["css"] = params["model"]["css"]
            return None
        if action == "createDeck":
            if params["deck"] not in self.decks: self.decks.append(params["deck"])
            return 1
        if action == "findNotes":
            uid = params["query"].removeprefix("UID:")
            return [self.notes[uid][0]] if uid in self.notes else []
        if action == "storeMediaFile": return params["filename"]
        if action == "addNote":
            note = params["note"]
            if note["deckName"] not in self.decks: raise ValueError("deck missing")
            if list(note["fields"]) != self.models[note["modelName"]]["inOrderFields"]:
                raise ValueError("note fields do not match model")
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
            self.assertEqual(self.cli("init", "--kind", "sentence_chunk", "--update-style")[0], 0)
            client.return_value.initialize.assert_called_once_with(update_style=True)

    def test_init_creates_both_models_idempotently_and_mixed_import_routes(self):
        self.assertEqual(self.cli("init")[0], 0)
        self.assertEqual(self.cli("init")[0], 0)
        self.assertEqual(len(self.state.models), 2)
        self.assertEqual(set(self.state.decks), {self.config.deck, self.config.errors_deck})
        self.assertEqual(self.state.models[self.config.errors_model]["inOrderFields"], ERROR_FIELDS)
        code, output = self.cli("add", str(ROOT / "examples/mixed.json"), "--no-audio", "--yes")
        self.assertEqual(code, 0, output)
        self.assertIn(f"1 -> {self.config.errors_deck}", output)
        self.assertIn("Original: She go", output)
        notes = [note for _, note in self.state.notes.values()]
        self.assertEqual([n["deckName"] for n in notes], [self.config.deck, self.config.errors_deck])
        self.assertEqual([n["modelName"] for n in notes], [self.config.model, self.config.errors_model])
        self.assertEqual(self.cli("add", str(ROOT / "examples/mixed.json"), "--no-audio", "--yes")[0], 0)
        self.assertEqual(len(self.state.notes), 2)

    def test_incompatible_03_blocks_entire_mixed_import_before_writes(self):
        self.cli("init")
        self.state.models[self.config.errors_model]["inOrderFields"] = ["Front", "Back"]
        self.state.calls.clear()
        code, output = self.cli("add", str(ROOT / "examples/mixed.json"), "--no-audio", "--yes")
        self.assertEqual(code, 1, output)
        self.assertFalse(any(c["action"] in {"addNote", "storeMediaFile"} for c in self.state.calls))

    def test_invalid_error_in_mixed_batch_makes_no_network_requests(self):
        data = error_example()
        del data["original"]
        path = Path(self.temp.name) / "invalid-mixed.json"
        path.write_text(json.dumps({"schema_version": "1.0", "cards": [example(), data]}))
        self.assertEqual(self.cli("add", str(path), "--yes")[0], 1)
        self.assertEqual(self.state.calls, [])

    def test_mixed_partial_failure_retry_and_corrected_audio(self):
        self.cli("init")
        batch = CardBatch.model_validate_json((ROOT / "examples/mixed.json").read_text())
        cards = [compile_card(spec) for spec in batch.cards]
        router = AnkiRouter(self.config, {"sentence_chunk", "my_error"})
        audio = Path(self.temp.name) / "eng_test.mp3"
        audio.write_bytes(b"test audio")
        spoken = []
        class RecordingTTS:
            def synthesize(self, text):
                spoken.append(text)
                return audio
        self.state.fail_add = cards[1].uid
        self.assertEqual([r.status for r in publish(cards, router, RecordingTTS())], ["added", "failed"])
        self.state.fail_add = None
        self.assertEqual([r.status for r in publish(cards, router, RecordingTTS())], ["skipped", "added"])
        self.assertEqual(spoken, [batch.cards[0].sentence, batch.cards[1].sentence, batch.cards[1].sentence])
        self.assertNotIn(batch.cards[1].original, spoken)
        self.assertEqual(len(self.state.notes), 2)

    def test_error_style_update_preserves_02_and_error_notes(self):
        self.cli("init")
        client = AnkiConnect(self.config, kind="my_error")
        client.add(compile_card(MyError.model_validate(error_example())), None)
        before_notes = json.dumps(self.state.notes, sort_keys=True)
        before_02 = json.dumps(self.state.model, sort_keys=True)
        self.state.models[self.config.errors_model]["css"] = "old error css"
        backup = client.initialize(update_style=True, backup_dir=Path(self.temp.name))
        self.assertEqual(json.loads(backup.read_text())["model"], self.config.errors_model)
        self.assertEqual(json.dumps(self.state.notes, sort_keys=True), before_notes)
        self.assertEqual(json.dumps(self.state.model, sort_keys=True), before_02)
        self.assertIsNone(client.initialize(update_style=True, backup_dir=Path(self.temp.name)))

    def test_error_cannot_be_written_through_02_client(self):
        self.gateway.initialize()
        self.state.calls.clear()
        with self.assertRaises(AnkiError):
            self.gateway.add(compile_card(MyError.model_validate(error_example())), None)
        self.assertEqual(self.state.calls, [])

    def test_error_only_init_and_custom_destinations(self):
        self.config_path.write_text(f'[anki]\nendpoint = "{self.config.endpoint}"\n'
                                    'errors_deck = "Study::My Errors"\nerrors_model = "My Corrections"\n')
        self.assertEqual(self.cli("init", "--kind", "my_error")[0], 0)
        self.assertEqual(list(self.state.models), ["My Corrections"])
        self.assertEqual(self.cli("add", str(ROOT / "examples/errors.json"), "--no-audio", "--yes")[0], 0)
        note = next(iter(self.state.notes.values()))[1]
        self.assertEqual(note["deckName"], "Study::My Errors")
        self.assertEqual(note["modelName"], "My Corrections")

    def test_error_template_keeps_feedback_and_original_off_front(self):
        import re
        front = templates("my_error")["front.html"]
        referenced = set(re.findall(r"\{\{([^#/].*?)\}\}", front))
        self.assertEqual(referenced, {"cloze:Text", "MeaningES"})
        back = templates("my_error")["back.html"]
        self.assertIn('{{ExplanationES}}', back)
        self.assertIn('<details class="sc-original">', back)
        self.assertNotIn('<details class="sc-original" open', back)

    def make_legacy(self, kind):
        client = AnkiConnect(self.config, kind=kind)
        client.initialize()
        card = compile_card(MyError.model_validate(error_example()) if kind == "my_error"
                            else SentenceChunk.model_validate(example()))
        client.add(card, None)
        model = self.state.models[client.model]
        model["inOrderFields"].remove("SentenceES")
        self.state.notes[card.uid][1]["fields"].pop("SentenceES")
        self.state.notes[card.uid][1]["fields"]["Audio"] = "[sound:existing.mp3]"
        model["cardTemplates"][0]["Back"] = "<p>{{cloze:Text}}</p>"
        return client, card

    def test_legacy_migration_both_kinds_preserves_existing_fields_and_notes(self):
        for kind in ("sentence_chunk", "my_error"):
            with self.subTest(kind=kind):
                client, card = self.make_legacy(kind)
                nid, note = self.state.notes[card.uid]
                old_fields = dict(note["fields"])
                backup = client.initialize(update_style=True, backup_dir=Path(self.temp.name))
                saved = json.loads(backup.read_text())
                self.assertEqual(saved["fields"], list(old_fields))
                self.assertEqual(self.state.notes[card.uid][0], nid)
                self.assertEqual(note["fields"], {**old_fields, "SentenceES": ""})
                client.verify()
                self.assertIsNone(client.initialize(update_style=True, backup_dir=Path(self.temp.name)))

    def test_legacy_migration_backup_failure_and_partial_retry(self):
        client, card = self.make_legacy("my_error")
        self.state.calls.clear()
        with patch("anki_english.anki.tempfile.NamedTemporaryFile", side_effect=OSError("disk full")):
            with self.assertRaises(OSError): client.initialize(update_style=True, backup_dir=Path(self.temp.name))
        self.assertNotIn("modelFieldAdd", [c["action"] for c in self.state.calls])
        self.state.fail_style = True
        with self.assertRaises(AnkiError): client.initialize(update_style=True, backup_dir=Path(self.temp.name))
        self.state.fail_style = False
        client.initialize(update_style=True, backup_dir=Path(self.temp.name))
        self.assertEqual(sum(c["action"] == "modelFieldAdd" for c in self.state.calls), 1)
        client.verify()

    def test_fill_existing_translations_only_and_idempotent(self):
        for kind in ("sentence_chunk", "my_error"):
            client, _ = self.make_legacy(kind)
            client.initialize(update_style=True, backup_dir=Path(self.temp.name))
        before = json.loads(json.dumps(self.state.notes))
        self.state.calls.clear()
        code, output = self.cli("update-translations", str(ROOT / "examples/mixed.json"), "--yes")
        self.assertEqual(code, 0, output)
        self.assertIn("Translations updated: 2", output)
        for uid, (nid, note) in self.state.notes.items():
            self.assertEqual(nid, before[uid][0])
            self.assertTrue(note["fields"]["SentenceES"])
            expected = before[uid][1]
            expected["fields"]["SentenceES"] = note["fields"]["SentenceES"]
            self.assertEqual(note, expected)
        writes = [c for c in self.state.calls if c["action"] == "updateNoteFields"]
        self.assertEqual(len(writes), 2)
        self.assertTrue(all(list(c["params"]["note"]["fields"]) == ["SentenceES"] for c in writes))
        self.assertFalse(any(c["action"] in {"addNote", "storeMediaFile"} for c in self.state.calls))
        self.state.calls.clear()
        self.assertEqual(self.cli("update-translations", str(ROOT / "examples/mixed.json"), "--yes")[0], 0)
        self.assertNotIn("updateNoteFields", [c["action"] for c in self.state.calls])

    def test_translation_preflight_blocks_changed_sentence_or_model(self):
        for kind in ("sentence_chunk", "my_error"):
            client, card = self.make_legacy(kind)
            client.initialize(update_style=True, backup_dir=Path(self.temp.name))
        note = self.state.notes[card.uid][1]
        for field in ("Sentence", "Text", "Original"):
            with self.subTest(field=field):
                original = note["fields"][field]
                note["fields"][field] = "Edited in Anki"
                self.state.calls.clear()
                self.assertEqual(self.cli("update-translations", str(ROOT / "examples/mixed.json"), "--yes")[0], 1)
                self.assertNotIn("updateNoteFields", [c["action"] for c in self.state.calls])
                note["fields"][field] = original
        note["modelName"] = "Another model"
        with self.assertRaises(AnkiError): client.translation_target(card)

    def test_translation_write_is_verified_and_retryable(self):
        client, card = self.make_legacy("my_error")
        client.initialize(update_style=True, backup_dir=Path(self.temp.name))
        self.state.ignore_translation = True
        code, output = self.cli("update-translations", str(ROOT / "examples/errors.json"), "--yes")
        self.assertEqual(code, 1)
        self.assertIn("translation was not saved", output)
        self.state.ignore_translation = False
        self.assertEqual(self.cli("update-translations", str(ROOT / "examples/errors.json"), "--yes")[0], 0)
        self.assertEqual(len(self.state.notes), 1)

    def test_translation_offline_cancel_missing_and_duplicate_notes(self):
        path = str(ROOT / "examples/cards.json")
        self.assertEqual(self.cli("update-translations", path, "--dry-run")[0], 0)
        self.assertEqual(self.state.calls, [])
        self.gateway.initialize()
        self.assertEqual(self.cli("update-translations", path, "--yes")[0], 0)
        card = compile_card(SentenceChunk.model_validate(example(sentence_es=None)))
        self.gateway.add(card, None)
        with patch("sys.stdin.isatty", return_value=True), patch("builtins.input", return_value="n"):
            self.assertEqual(self.cli("update-translations", path)[0], 0)
        self.assertNotIn("updateNoteFields", [c["action"] for c in self.state.calls])
        translated = compile_card(SentenceChunk.model_validate(example()))
        with patch.object(self.gateway, "call", return_value=[100, 101]):
            with self.assertRaisesRegex(AnkiError, "multiple matching"): self.gateway.translation_target(translated)

    def test_translation_disclosure_is_conditional_back_only_and_closed(self):
        for kind in ("sentence_chunk", "my_error"):
            resource = templates(kind)
            self.assertNotIn("SentenceES", resource["front.html"])
            self.assertIn('{{#SentenceES}}', resource["back.html"])
            self.assertIn('{{/SentenceES}}', resource["back.html"])
            self.assertIn('<details class="sc-cue sc-translation">', resource["back.html"])
            self.assertIn('Show Spanish translation', resource["back.html"])
            self.assertIn('lang="es">{{SentenceES}}', resource["back.html"])


if __name__ == "__main__":
    unittest.main()
