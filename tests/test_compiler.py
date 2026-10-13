import copy
import json
from pathlib import Path
import unittest

from pydantic import ValidationError

from anki_english.compiler import compile_card, uid_for, ERROR_FIELDS
from anki_english.spec import CardBatch, SentenceChunk, MyError, schema

ROOT = Path(__file__).resolve().parents[1]


def example(**changes):
    value = copy.deepcopy(json.loads((ROOT / "examples/cards.json").read_text())["cards"][0])
    value.update(changes)
    return value


def error_example(**changes):
    value = copy.deepcopy(json.loads((ROOT / "examples/errors.json").read_text())["cards"][0])
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

    def test_front_cue_warns_on_answer_or_canonical_target_leaks(self):
        for meaning in ("LOOKING FORWARD TO: tener ganas", "Usa look forward to"):
            with self.subTest(meaning=meaning):
                card = compile_card(SentenceChunk.model_validate(example(meaning_es=meaning)))
                self.assertTrue(any("MeaningES may reveal" in warning for warning in card.warnings))
        safe = compile_card(SentenceChunk.model_validate(example(
            sentence="I need a pan.", answer="pan", target="pan", meaning_es="sartén para panqueques")))
        self.assertFalse(any("MeaningES may reveal" in warning for warning in safe.warnings))

    def test_visible_repeated_answer_warns_without_changing_identity(self):
        spec = SentenceChunk.model_validate(example(
            sentence="I know that you KNOW.", answer="know", target="know", meaning_es="saber"))
        card = compile_card(spec)
        self.assertTrue(any("outside the selected blank" in warning for warning in card.warnings))
        self.assertEqual(card.fields["Text"], "I {{c1::know}} that you KNOW.")
        self.assertEqual(card.uid, uid_for(spec))

    def test_exported_schema_matches_runtime_contract(self):
        self.assertEqual(schema(), json.loads((ROOT / "schemas/card-spec-v1.schema.json").read_text()))

    def test_existing_02_uids_are_unchanged(self):
        # Captured from the published v0.3.2 compiler, before adding MyError.
        expected = ["sc_ca7ce43c3af0aafc61b72dbd623d98eb0776085c3b418ede326d14a5553a436b",
                    "sc_dc359bebc025ef6e10e8c1b1566186a1ef00abda4e692a0a3636e46aaf3e67f1"]
        batch = CardBatch.model_validate_json((ROOT / "examples/cards.json").read_text())
        self.assertEqual([uid_for(card) for card in batch.cards], expected)

    def test_mixed_batch_selects_types_and_compiles_corrected_error(self):
        batch = CardBatch.model_validate_json((ROOT / "examples/mixed.json").read_text())
        self.assertIsInstance(batch.cards[0], SentenceChunk)
        self.assertIsInstance(batch.cards[1], MyError)
        card = compile_card(batch.cards[1])
        self.assertEqual(list(card.fields), ERROR_FIELDS)
        self.assertEqual(card.fields["Text"], "She {{c1::goes}} to work every day.")
        self.assertEqual(card.fields["Original"], "She go to work every day.")
        self.assertEqual(card.fields["ObservedOn"], "")
        self.assertIn("type::my-error", card.tags)
        self.assertIn("error::grammar", card.tags)

    def test_errors_need_original_correction_and_feedback(self):
        for missing in ("original", "explanation_es", "correction_source", "error_type"):
            data = error_example()
            del data[missing]
            with self.subTest(missing=missing), self.assertRaises(ValidationError):
                MyError.model_validate(data)
        for changes in (
            {"original": error_example()["sentence"]}, {"original": " "},
            {"correction_source": ""}, {"error_type": "pronunciation"},
            {"observed_on": "2026-02-30"}, {"observed_on": "20261012"},
            {"tts_text": error_example()["original"]}, {"tags": ["error::fake"]},
            {"original": "{{c1::injected}}"}, {"explanation_es": "[sound:bad.mp3]"},
        ):
            with self.subTest(changes=changes), self.assertRaises(ValidationError):
                MyError.model_validate(error_example(**changes))

    def test_error_identity_ignores_feedback_date_but_tracks_attempt(self):
        one = MyError.model_validate(error_example())
        metadata = MyError.model_validate(error_example(observed_on="2026-10-12", explanation_es="Otra explicación."))
        different = MyError.model_validate(error_example(original="She going to work every day."))
        self.assertEqual(uid_for(one), uid_for(metadata))
        self.assertNotEqual(uid_for(one), uid_for(different))
        as_chunk = {key: value for key, value in error_example().items() if key in SentenceChunk.model_fields}
        as_chunk["kind"] = "sentence_chunk"
        self.assertNotEqual(uid_for(one), uid_for(SentenceChunk.model_validate(as_chunk)))

    def test_error_feedback_and_original_are_escaped(self):
        card = compile_card(MyError.model_validate(error_example(
            original='<img src=x onerror="bad()">', explanation_es='<script>bad()</script>',
            correction_source='<b>Teacher</b>')))
        for field in ("Original", "ExplanationES", "CorrectionSource"):
            self.assertNotIn("<", card.fields[field])
            self.assertIn("&lt;", card.fields[field])

    def test_translation_is_optional_escaped_and_not_part_of_identity(self):
        for model, factory in ((SentenceChunk, example), (MyError, error_example)):
            data = factory()
            data.pop("sentence_es")
            old = compile_card(model.model_validate(data))
            new = compile_card(model.model_validate({**data, "sentence_es": '<script>hola</script>'}))
            self.assertEqual(old.uid, new.uid)
            self.assertEqual(old.fields["SentenceES"], "")
            self.assertEqual(new.fields["SentenceES"], "&lt;script&gt;hola&lt;/script&gt;")
            self.assertEqual(list(new.fields)[-1], "SentenceES")
            with self.assertRaises(ValidationError): model.model_validate({**data, "sentence_es": " "})


if __name__ == "__main__":
    unittest.main()
