"""Small AnkiConnect adapter. No deletion, scheduling or automatic retries."""

import base64
from importlib.resources import files
import json
from pathlib import Path
import tempfile
from typing import Protocol
from urllib.error import URLError
from urllib.request import ProxyHandler, Request, build_opener

from .compiler import CompiledCard, fields_for
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

    def _read_model_templates(self) -> dict[str, dict[str, str]]:
        actual = self.call("modelFieldNames", modelName=self.model)
        if actual != self.fields:
            raise AnkiError("Existing note type has different fields/order. Nothing was overwritten. "
                            "Choose a new model name or reconcile it manually.")
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
        current = self._read_model_templates()
        styling = self.call("modelStyling", modelName=self.model)
        if not isinstance(styling, dict) or not isinstance(styling.get("css"), str):
            raise AnkiError("modelStyling: malformed response; nothing was changed")
        resource = templates(self.kind)
        name = next(iter(current))  # Preserve the existing template name and card ordinal.
        replacement = {"Front": resource["front.html"], "Back": resource["back.html"]}
        if current[name] == replacement and styling["css"] == resource["style.css"]:
            return None

        directory = backup_dir if backup_dir is not None else Path.home() / ".local/share/anki-english/backups"
        directory.mkdir(parents=True, exist_ok=True)
        # Save before either mutation. Unique file, restrictive default permissions.
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", prefix="style-", suffix=".json",
                                         dir=directory, delete=False) as stream:
            backup = Path(stream.name)
            json.dump({"model": self.model, "templates": current, "css": styling["css"]},
                      stream, ensure_ascii=False, indent=2)
        try:
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
