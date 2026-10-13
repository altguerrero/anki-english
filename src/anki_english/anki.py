"""Small AnkiConnect adapter. No deletion, scheduling or automatic retries."""

import base64
from importlib.resources import files
import json
from pathlib import Path
import tempfile
from typing import Protocol
from urllib.error import URLError
from urllib.request import ProxyHandler, Request, build_opener

from .compiler import CompiledCard, fields_for, LEGACY_FIELDS, LEGACY_ERROR_FIELDS
from .config import AnkiConfig
from .spec import CardKind


class AnkiError(RuntimeError):
    pass


class AnkiGateway(Protocol):
    def verify(self) -> None: ...
    def exists(self, uid: str) -> bool: ...
    def add(self, card: CompiledCard, audio: Path | None) -> int: ...


def templates(kind: CardKind = "sentence_chunk") -> dict[str, str]:
    root = files("anki_english").joinpath("templates")
    prefix = "error-" if kind == "my_error" else ""
    return {name: root.joinpath(prefix + name if name != "style.css" else name).read_text(encoding="utf-8")
            for name in ("front.html", "back.html", "style.css")}


class AnkiConnect:
    def __init__(self, config: AnkiConfig, key: str | None = None, kind: CardKind = "sentence_chunk"):
        self.config = config
        self.kind = kind
        self.deck, self.model = config.destination(kind)
        self.fields = fields_for(kind)
        self.key = key
        self._opener = build_opener(ProxyHandler({}))  # Local traffic bypasses proxies.

    def call(self, action: str, **params):
        payload = {"action": action, "version": 6, "params": params}
        if self.key:
            payload["key"] = self.key
        request = Request(self.config.endpoint, data=json.dumps(payload).encode(),
                          headers={"Content-Type": "application/json"}, method="POST")
        try:
            with self._opener.open(request, timeout=self.config.timeout) as response:
                result = json.load(response)
        except (URLError, TimeoutError, OSError, ValueError) as error:
            raise AnkiError(f"{action}: cannot get a valid AnkiConnect response. "
                            "Open Anki with AnkiConnect enabled; check endpoint/API key. "
                            "If this was a write, its outcome may be unknown; rerun to check UID.") from error
        if not isinstance(result, dict) or "error" not in result or "result" not in result:
            raise AnkiError(f"{action}: malformed AnkiConnect response")
        if result["error"] is not None:
            raise AnkiError(f"{action}: {result['error']}")
        return result["result"]

    def _check_version(self) -> None:
        version = self.call("version")
        if type(version) is not int or version < 6:
            raise AnkiError("AnkiConnect API v6 or newer is required")

    def _read_model_templates(self, allow_legacy: bool = False) -> dict[str, dict[str, str]]:
        actual = self.call("modelFieldNames", modelName=self.model)
        legacy = LEGACY_ERROR_FIELDS if self.kind == "my_error" else LEGACY_FIELDS
        if actual != self.fields and not (allow_legacy and actual == legacy):
            raise AnkiError("Existing note type has different fields/order. Nothing was overwritten. "
                            "Run anki-en init --update-style for the supported migration; otherwise reconcile manually.")
        actual_templates = self.call("modelTemplates", modelName=self.model)
        if not isinstance(actual_templates, dict) or len(actual_templates) != 1:
            raise AnkiError("Expected exactly one cloze template")
        template = next(iter(actual_templates.values()))
        if not isinstance(template, dict) or any(
            not isinstance(template.get(side), str) or "{{cloze:Text}}" not in template[side]
            for side in ("Front", "Back")
        ):
            raise AnkiError("Expected the Text cloze filter on both sides; cannot update this model")
        return actual_templates

    def _verify_model(self) -> None:
        actual_templates = self._read_model_templates()
        expected = templates(self.kind)
        template = next(iter(actual_templates.values()))
        if not isinstance(template, dict) or any(
            template.get(side, "").strip() != expected[file].strip()
            for side, file in (("Front", "front.html"), ("Back", "back.html"))
        ):
            raise AnkiError("Existing template differs from this version. Nothing was overwritten. "
                            "Run anki-en init --update-style to apply this version's design.")

    def _update_style(self, backup_dir: Path | None = None) -> Path | None:
        current = self._read_model_templates(allow_legacy=True)
        old_fields = self.call("modelFieldNames", modelName=self.model)
        needs_field = old_fields != self.fields
        styling = self.call("modelStyling", modelName=self.model)
        if not isinstance(styling, dict) or not isinstance(styling.get("css"), str):
            raise AnkiError("modelStyling: malformed response; nothing was changed")
        resource = templates(self.kind)
        name = next(iter(current))  # Preserve the existing template name and card ordinal.
        replacement = {"Front": resource["front.html"], "Back": resource["back.html"]}
        if not needs_field and current[name] == replacement and styling["css"] == resource["style.css"]:
            return None

        directory = backup_dir if backup_dir is not None else Path.home() / ".local/share/anki-english/backups"
        directory.mkdir(parents=True, exist_ok=True)
        # Save before any field or template mutation. Unique file, restrictive default permissions.
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", prefix="style-", suffix=".json",
                                         dir=directory, delete=False) as stream:
            backup = Path(stream.name)
            json.dump({"model": self.model, "fields": old_fields, "templates": current, "css": styling["css"]},
                      stream, ensure_ascii=False, indent=2)
        try:
            if needs_field:
                self.call("modelFieldAdd", modelName=self.model, fieldName="SentenceES")
                if self.call("modelFieldNames", modelName=self.model) != self.fields:
                    raise AnkiError("SentenceES field migration verification failed")
            self.call("updateModelTemplates", model={"name": self.model, "templates": {name: replacement}})
            self.call("updateModelStyling", model={"name": self.model, "css": resource["style.css"]})
            self._verify_model()
            if self.call("modelStyling", modelName=self.model) != {"css": resource["style.css"]}:
                raise AnkiError("CSS verification failed")
        except AnkiError as error:
            raise AnkiError(f"Style update incomplete: {error}. Previous design saved at {backup}. "
                            "Rerun init --update-style to finish; note content was not changed.") from error
        return backup

    def initialize(self, update_style: bool = False, backup_dir: Path | None = None) -> Path | None:
        self._check_version()
        backup = None
        if self.model in self.call("modelNames"):
            if update_style:
                backup = self._update_style(backup_dir)
            else:
                self._verify_model()  # Verify compatibility before creating any deck.
        else:
            resource = templates(self.kind)
            self.call("createModel", modelName=self.model, inOrderFields=self.fields,
                      css=resource["style.css"], isCloze=True,
                      cardTemplates=[{"Name": "My Error" if self.kind == "my_error" else "Sentence & Chunk",
                                      "Front": resource["front.html"],
                                      "Back": resource["back.html"]}])
            self._verify_model()
        self.call("createDeck", deck=self.deck)
        return backup

    def verify(self) -> None:
        self._check_version()
        if self.model not in self.call("modelNames") or self.deck not in self.call("deckNames"):
            raise AnkiError("Deck/note type missing. Run anki-en init first.")
        self._verify_model()

    def exists(self, uid: str) -> bool:
        # UID is compiler-generated hex, so it cannot inject Anki search syntax.
        result = self.call("findNotes", query=f"UID:{uid}")
        if not isinstance(result, list) or any(type(note) is not int for note in result):
            raise AnkiError("findNotes: malformed response")
        return bool(result)

    def _translation_note(self, card: CompiledCard, note_id: int) -> dict:
        result = self.call("notesInfo", notes=[note_id])
        if not isinstance(result, list) or len(result) != 1 or not isinstance(result[0], dict):
            raise AnkiError("notesInfo: malformed response")
        note = result[0]
        if note.get("noteId") != note_id or note.get("modelName") != self.model:
            raise AnkiError(f"{card.uid}: note ID/model differs; no translation written")
        fields = note.get("fields")
        if not isinstance(fields, dict) or any(
            not isinstance(fields.get(name), dict) or not isinstance(fields[name].get("value"), str)
            for name in self.fields
        ):
            raise AnkiError("notesInfo: missing fields; run init --update-style first")
        identity_fields = ["UID", "Sentence", "Text"]
        if self.kind == "my_error":
            identity_fields.append("Original")
        if any(fields[name]["value"] != card.fields[name] for name in identity_fields):
            raise AnkiError(f"{card.uid}: sentence/identity changed in Anki; review it manually")
        return note

    def translation_target(self, card: CompiledCard) -> int | None:
        """Only fill empty translations on an unambiguous, unchanged existing note."""
        if card.spec.kind != self.kind or not card.spec.sentence_es:
            raise AnkiError("Translation requires matching card kind and sentence_es")
        ids = self.call("findNotes", query=f"UID:{card.uid}")
        if not isinstance(ids, list) or any(type(n) is not int or n <= 0 for n in ids):
            raise AnkiError("findNotes: malformed response")
        if not ids:
            return None
        if len(ids) != 1:
            raise AnkiError(f"{card.uid}: multiple matching notes; review duplicates manually")
        note = self._translation_note(card, ids[0])
        return None if note["fields"]["SentenceES"]["value"].strip() else ids[0]

    def fill_translation(self, card: CompiledCard, note_id: int) -> bool:
        # Recheck after confirmation; preserve any translation added in the meantime.
        target = self.translation_target(card)
        if target is None:
            return False
        if target != note_id:
            raise AnkiError(f"{card.uid}: note changed after preview; rerun to review")
        self.call("updateNoteFields", note={"id": note_id, "fields": {"SentenceES": card.fields["SentenceES"]}})
        actual = self._translation_note(card, note_id)["fields"]["SentenceES"]["value"]
        if actual != card.fields["SentenceES"]:
            raise AnkiError(f"{card.uid}: translation was not saved. Close Anki's Browser/editor and retry.")
        return True

    def add(self, card: CompiledCard, audio: Path | None) -> int:
        if card.spec.kind != self.kind or list(card.fields) != self.fields:
            raise AnkiError("Card kind/fields do not match this note type; nothing was written")
        fields = dict(card.fields)
        if audio is not None:
            stored = self.call("storeMediaFile", filename=audio.name,
                               data=base64.b64encode(audio.read_bytes()).decode("ascii"))
            if not isinstance(stored, str) or stored != audio.name:
                raise AnkiError("storeMediaFile returned an unexpected filename; note was not added")
            fields["Audio"] = f"[sound:{stored}]"
        note_id = self.call("addNote", note={
            "deckName": self.deck, "modelName": self.model,
            "fields": fields, "tags": list(card.tags),
            "options": {"allowDuplicate": False, "duplicateScope": "collection"},
        })
        if type(note_id) is not int or note_id <= 0:
            raise AnkiError("addNote did not return a valid note ID; rerun to check UID")
        return note_id


class AnkiRouter:
    """Route an already classified batch; verify every destination before writing."""

    def __init__(self, config: AnkiConfig, kinds: set[CardKind], key: str | None = None):
        self.clients = {kind: AnkiConnect(config, key, kind=kind) for kind in sorted(kinds)}

    def verify(self) -> None:
        for client in self.clients.values():
            client.verify()

    def exists(self, uid: str) -> bool:
        # UID lookup covers the collection, regardless of a note's current deck.
        return next(iter(self.clients.values())).exists(uid)

    def add(self, card: CompiledCard, audio: Path | None) -> int:
        return self.clients[card.spec.kind].add(card, audio)
