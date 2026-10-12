"""Publish sequentially with per-card outcomes and retry-safe UID checks."""

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from .anki import AnkiGateway, AnkiError
from .audio import TTSProvider, AudioError
from .compiler import CompiledCard


@dataclass(frozen=True)
class Outcome:
    uid: str
    status: str
    note_id: int | None = None
    message: str = ""


def publish(cards: list[CompiledCard], gateway: AnkiGateway, tts: TTSProvider | None,
            emit: Callable[[Outcome], None] = lambda result: None) -> list[Outcome]:
    results = []
    for card in cards:
        try:
            # Recheck after preview/confirmation in case another import added it.
            if gateway.exists(card.uid):
                result = Outcome(card.uid, "skipped", message="UID already exists")
            else:
                audio: Path | None = tts.synthesize(card.spec.tts_text or card.spec.sentence) if tts else None
                result = Outcome(card.uid, "added", note_id=gateway.add(card, audio))
        except (AnkiError, AudioError, OSError) as error:
            result = Outcome(card.uid, "failed", message=str(error))
            results.append(result)
            emit(result)
            # Stop at first failure. Earlier successes remain and will be skipped on retry.
            break
        results.append(result)
        emit(result)
    return results
