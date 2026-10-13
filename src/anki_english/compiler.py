"""Pure compilation: no network, media generation or collection writes."""

from dataclasses import dataclass
from hashlib import sha256
from html import escape
import json
import unicodedata

from .spec import CardKind, CardSpec, MyError, answer_spans

FIELDS = ["UID", "Text", "Sentence", "Target", "MeaningES", "Pattern", "Example", "Audio", "Source", "SourceURL"]
ERROR_FIELDS = FIELDS + ["Original", "ExplanationES", "ErrorType", "CorrectionSource", "ObservedOn"]


def fields_for(kind: CardKind) -> list[str]:
    return ERROR_FIELDS if kind == "my_error" else FIELDS


def normalized(text: str) -> str:
    return " ".join(unicodedata.normalize("NFC", text).casefold().split())


def uid_for(card: CardSpec) -> str:
    identity = ["sc-v1", card.kind, normalized(card.sentence), normalized(card.answer), card.answer_occurrence]
    prefix = "sc_"
    if isinstance(card, MyError):
        identity = ["error-v1", card.kind, normalized(card.original), normalized(card.sentence),
                    normalized(card.answer), card.answer_occurrence]
        prefix = "err_"
    return prefix + sha256(json.dumps(identity, ensure_ascii=False).encode()).hexdigest()


def lint(card: CardSpec) -> tuple[str, ...]:
    warnings = []
    if len(card.sentence.split()) > 25:
        warnings.append("Long sentence: more than 25 words.")
    if len(card.answer.split()) > 8:
        warnings.append("Long answer: check that it is one reusable learning target.")
    if len(card.meaning_es.split()) > 15:
        warnings.append("MeaningES looks longer than a short gloss.")
    if card.pattern and len(card.pattern) > 90:
        warnings.append("Pattern is unusually long.")
    if card.example and normalized(card.example) == normalized(card.sentence):
        warnings.append("Example repeats Sentence; use a different context.")
    if card.tts_text and card.tts_text != card.sentence:
        warnings.append("Audio text differs from Sentence; check that pronunciation still matches.")
    if normalized(card.answer) == normalized(card.sentence):
        warnings.append("The entire sentence is hidden; there is no remaining context.")
    if len(card.answer.split()) == 1 and len(card.target.split()) > 1:
        warnings.append("Answer is one word but Target is a phrase; check the learning target.")
    if any(answer_spans(normalized(card.meaning_es), normalized(value))
           for value in (card.answer, card.target)):
        warnings.append("MeaningES may reveal the English answer on the front; use a Spanish-only meaning cue.")
    if len(answer_spans(normalized(card.sentence), normalized(card.answer))) > 1:
        warnings.append("The answer also appears outside the selected blank; rephrase to avoid revealing it.")
    return tuple(warnings)


@dataclass(frozen=True)
class CompiledCard:
    spec: CardSpec
    uid: str
    fields: dict[str, str]
    tags: tuple[str, ...]
    warnings: tuple[str, ...]


def compile_card(card: CardSpec) -> CompiledCard:
    start, end = answer_spans(card.sentence, card.answer)[card.answer_occurrence - 1]
    text = (escape(card.sentence[:start]) + "{{c1::" + escape(card.answer)
            + "}}" + escape(card.sentence[end:]))
    uid = uid_for(card)
    fields = dict(zip(FIELDS, [
        uid, text, escape(card.sentence), escape(card.target), escape(card.meaning_es),
        escape(card.pattern or ""), escape(card.example or ""), "",
        escape(card.source.label or card.source.type), escape(card.source.url or ""),
    ], strict=True))
    type_tag = "type::sentence-chunk"
    extra_tags = set()
    if isinstance(card, MyError):
        fields.update({"Original": escape(card.original), "ExplanationES": escape(card.explanation_es),
                       "ErrorType": escape(card.error_type.replace("_", " ")),
                       "CorrectionSource": escape(card.correction_source),
                       "ObservedOn": escape(card.observed_on or "")})
        type_tag = "type::my-error"
        extra_tags.add(f"error::{card.error_type.replace('_', '-')}")
    tags = sorted({type_tag, *extra_tags, f"source::{card.source.type}",
                   *(f"island::{island}" for island in card.islands), *card.tags})
    return CompiledCard(card, uid, fields, tuple(tags), lint(card))
