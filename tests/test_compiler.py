import copy
import json
from pathlib import Path
import unittest

from pydantic import ValidationError

from anki_english.compiler import compile_card, uid_for
from anki_english.spec import CardBatch, SentenceChunk, schema

ROOT = Path(__file__).resolve().parents[1]


def example(**changes):
    value = copy.deepcopy(json.loads((ROOT / "examples/cards.json").read_text())["cards"][0])
    value.update(changes)
    return value


class CompilerTests(unittest.TestCase):
    def test_inflected_answer_and_canonical_target(self):
        card = compile_card(SentenceChunk.model_validate(example()))
        self.assertIn("{{c1::looking forward to}}", card.fields["Text"])
        self.assertEqual(card.fields["Target"], "look forward to")
        self.assertEqual(card.fields["Audio"], "")
        self.assertIn("island::social", card.tags)

    def test_repeated_answer_selects_only_second_occurrence(self):
        one = SentenceChunk.model_validate(example(sentence="I know that you know.", answer="know", target="know"))
        two = SentenceChunk.model_validate(example(sentence="I know that you know.", answer="know", target="know", answer_occurrence=2))
        self.assertEqual(compile_card(two).fields["Text"], "I know that you {{c1::know}}.")
        self.assertNotEqual(uid_for(one), uid_for(two))

    def test_identity_ignores_metadata_but_normalizes_spaces_and_case(self):
        one = SentenceChunk.model_validate(example())
        two = SentenceChunk.model_validate(example(sentence="I'M  really looking forward to seeing you again.", meaning_es="otra glosa"))
        self.assertEqual(uid_for(one), uid_for(two))

    def test_untrusted_html_is_plain_text(self):
        card = compile_card(SentenceChunk.model_validate(example(
            sentence='I say <script>alert("hi")</script>.', answer="say", target="say",
            meaning_es='<img src=x onerror="alert(1)">')))
        self.assertNotIn("<script>", card.fields["Text"])
        self.assertIn("&lt;script&gt;", card.fields["Text"])
        self.assertNotIn("<img", card.fields["MeaningES"])

    def test_invalid_inputs_are_rejected(self):
        invalid = [
            {"answer": "look forward to"}, {"answer_occurrence": 2},
            {"answer_occurrence": True}, {"answer_occurrence": "1"},
            {"sentence": " "}, {"meaning_es": ""}, {"kind": "basic"},
            {"pattern": "two\nlines"}, {"example": "{{c2::injected}}"},
            {"tts_text": "[sound:secret.mp3]"}, {"sentence": "bad\x1b[31mtext"},
            {"source": {"type": "manual", "label": None, "url": "javascript:alert(1)"}},
            {"tags": ["two words"]}, {"tags": ["source::fake"]},
            {"tags": ["chunk", "chunk"]}, {"islands": ["work", "work"]},
            {"sentence": "I know.", "answer": "no", "target": "no"},
            {"sentence": "I say a::b.", "answer": "a::b"},
            {"sentence": "I say }.", "answer": "}"},
            {"deckName": "Injected deck"},
        ]
        for changes in invalid:
            with self.subTest(changes=changes), self.assertRaises(ValidationError):
                SentenceChunk.model_validate(example(**changes))

    def test_lint_warns_without_claiming_to_judge_learning_quality(self):
        card = compile_card(SentenceChunk.model_validate(example(
            example=example()["sentence"], tts_text="A different sentence.")))
        self.assertEqual(len(card.warnings), 2)

    def test_batch_size_version_and_extra_fields(self):
        for batch in [{"schema_version": "2.0", "cards": [example()]},
                      {"schema_version": "1.0", "cards": []},
                      {"schema_version": "1.0", "cards": [example()] * 51},
                      {"schema_version": "1.0", "cards": [example()], "extra": 1}]:
            with self.subTest(batch_size=len(batch["cards"])), self.assertRaises(ValidationError):
                CardBatch.model_validate(batch)

    def test_exported_schema_matches_runtime_contract(self):
        self.assertEqual(schema(), json.loads((ROOT / "schemas/card-spec-v1.schema.json").read_text()))


if __name__ == "__main__":
    unittest.main()
