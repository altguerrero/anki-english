"""Small AnkiConnect adapter. No deletion, scheduling or automatic retries."""

import base64
from importlib.resources import files
import json
from pathlib import Path
from typing import Protocol
from urllib.error import URLError
from urllib.request import ProxyHandler, Request, build_opener

from .compiler import CompiledCard, FIELDS
from .config import AnkiConfig


class AnkiError(RuntimeError):
    pass


class AnkiGateway(Protocol):
    def verify(self) -> None: ...
    def exists(self, uid: str) -> bool: ...
    def add(self, card: CompiledCard, audio: Path | None) -> int: ...


def templates() -> dict[str, str]:
    root = files("anki_english").joinpath("templates")
    return {name: root.joinpath(name).read_text(encoding="utf-8")
            for name in ("front.html", "back.html", "style.css")}


class AnkiConnect:
    def __init__(self, config: AnkiConfig, key: str | None = None):
        self.config = config
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

    def _verify_model(self) -> None:
        actual = self.call("modelFieldNames", modelName=self.config.model)
        if actual != FIELDS:
            raise AnkiError("Existing note type has different fields/order. Nothing was overwritten. "
                            "Choose a new model name or reconcile it manually.")
        actual_templates = self.call("modelTemplates", modelName=self.config.model)
        expected = templates()
        if not isinstance(actual_templates, dict) or len(actual_templates) != 1:
            raise AnkiError("Expected exactly one sentence/chunk template")
        template = next(iter(actual_templates.values()))
        if not isinstance(template, dict) or any(
            template.get(side, "").strip() != expected[file].strip()
            for side, file in (("Front", "front.html"), ("Back", "back.html"))
        ):
            raise AnkiError("Existing template differs from this version. Nothing was overwritten. "
                            "Use a new model name or reconcile it manually.")

    def initialize(self) -> None:
        self._check_version()
        if self.config.model in self.call("modelNames"):
            self._verify_model()  # Verify compatibility before creating any deck.
        else:
            resource = templates()
            self.call("createModel", modelName=self.config.model, inOrderFields=FIELDS,
                      css=resource["style.css"], isCloze=True,
                      cardTemplates=[{"Name": "Sentence & Chunk", "Front": resource["front.html"],
                                      "Back": resource["back.html"]}])
            self._verify_model()
        self.call("createDeck", deck=self.config.deck)

    def verify(self) -> None:
        self._check_version()
        if self.config.model not in self.call("modelNames") or self.config.deck not in self.call("deckNames"):
            raise AnkiError("Deck/note type missing. Run anki-en init first.")
        self._verify_model()

    def exists(self, uid: str) -> bool:
        # UID is compiler-generated hex, so it cannot inject Anki search syntax.
        result = self.call("findNotes", query=f"UID:{uid}")
        if not isinstance(result, list) or any(type(note) is not int for note in result):
            raise AnkiError("findNotes: malformed response")
        return bool(result)

    def add(self, card: CompiledCard, audio: Path | None) -> int:
        fields = dict(card.fields)
        if audio is not None:
            stored = self.call("storeMediaFile", filename=audio.name,
                               data=base64.b64encode(audio.read_bytes()).decode("ascii"))
            if not isinstance(stored, str) or stored != audio.name:
                raise AnkiError("storeMediaFile returned an unexpected filename; note was not added")
            fields["Audio"] = f"[sound:{stored}]"
        note_id = self.call("addNote", note={
            "deckName": self.config.deck, "modelName": self.config.model,
            "fields": fields, "tags": list(card.tags),
            "options": {"allowDuplicate": False, "duplicateScope": "collection"},
        })
        if type(note_id) is not int or note_id <= 0:
            raise AnkiError("addNote did not return a valid note ID; rerun to check UID")
        return note_id
