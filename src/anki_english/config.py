import os
from pathlib import Path
import tomllib
from typing import Annotated, Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .spec import CardKind


class AnkiConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    endpoint: str = "http://127.0.0.1:8765"
    deck: str = "English::02 Sentences & Chunks"
    model: str = "English – Sentence & Chunk"
    errors_deck: str = "English::03 My Errors"
    errors_model: str = "English – My Error"
    timeout: Annotated[float, Field(gt=0, le=120)] = 15.0

    @field_validator("endpoint")
    @classmethod
    def loopback_only(cls, value: str) -> str:
        parsed = urlsplit(value)
        if (parsed.scheme != "http" or parsed.hostname not in {"localhost", "127.0.0.1", "::1"}
                or parsed.username or parsed.password or parsed.query or parsed.fragment
                or parsed.path not in {"", "/"}):
            raise ValueError("V1 only connects to local AnkiConnect over HTTP")
        _ = parsed.port  # Reject invalid ports while parsing configuration.
        return value

    @field_validator("deck", "model", "errors_deck", "errors_model")
    @classmethod
    def valid_name(cls, value: str) -> str:
        if not value.strip() or any(ord(c) < 32 for c in value):
            raise ValueError("deck/model name cannot be blank or contain control characters")
        return value

    @model_validator(mode="after")
    def separate_destinations(self):
        if self.deck.strip().casefold() == self.errors_deck.strip().casefold():
            raise ValueError("02 and 03 must use different decks")
        if self.model.strip().casefold() == self.errors_model.strip().casefold():
            raise ValueError("02 and 03 must use different note types")
        return self

    def destination(self, kind: CardKind) -> tuple[str, str]:
        if kind == "my_error":
            return self.errors_deck, self.errors_model
        return self.deck, self.model


class TTSConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    provider: Literal["kokoro"] = "kokoro"
    voice: str = "af_heart"
    lang_code: Literal["a", "b"] = "a"
    speed: Annotated[float, Field(ge=0.5, le=2.0)] = 1.0
    cache_dir: str = "~/.cache/anki-english/audio"

    @field_validator("voice")
    @classmethod
    def valid_voice(cls, value: str) -> str:
        import re
        if not re.fullmatch(r"[ab][fm]_[a-z0-9_]+", value):
            raise ValueError("use an English Kokoro voice name, e.g. af_heart")
        return value

    @model_validator(mode="after")
    def matching_dialect(self):
        if self.voice[0] != self.lang_code:
            raise ValueError("voice and lang_code must use the same English dialect")
        return self


class Config(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    anki: AnkiConfig = Field(default_factory=AnkiConfig)
    tts: TTSConfig = Field(default_factory=TTSConfig)


def load_config(path: Path | None) -> Config:
    if path is None:
        return Config()
    with path.open("rb") as stream:
        return Config.model_validate(tomllib.load(stream))


def api_key() -> str | None:
    return os.environ.get("ANKI_CONNECT_API_KEY")
