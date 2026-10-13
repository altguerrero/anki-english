"""Exercise the plugin's offline validator as it is used in a new session."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "plugins/anki-english-coach/skills/create-english-cards/scripts/validate_cards.py"


class PluginValidationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.history = self.directory / "history"
        self.history.mkdir()
        self.draft = self.directory / "draft.json"
        self.data = json.loads((ROOT / "examples/mixed.json").read_text())

    def run_validator(self, data=None, *extra):
        self.draft.write_text(json.dumps(self.data if data is None else data))
        process = subprocess.run([sys.executable, str(SCRIPT), str(self.draft), "--date", "2026-10-13",
                                  "--topic", "daily-life", *extra], capture_output=True, text=True)
        return process.returncode, json.loads(process.stdout)

    def test_mixed_contract_and_deterministic_path(self):
        code, report = self.run_validator(None, "--existing-dir", str(self.history))
        self.assertEqual(code, 0)
        self.assertTrue(report["ready_to_save"])
        self.assertEqual(report["counts"], {"sentence_chunk": 1, "my_error": 1})
        self.assertRegex(report["suggested_path"], r"^card-specs/sessions/2026-10-13/daily-life-[a-f0-9]{12}\.json$")
        _, again = self.run_validator(None, "--existing-dir", str(self.history), "--repo", str(ROOT))
        self.assertEqual(report["suggested_path"], again["suggested_path"])
        self.assertEqual(report["runtime_hashes"], again["runtime_hashes"])

    def test_missing_history_is_not_claimed_ready(self):
        code, report = self.run_validator()
        self.assertEqual(code, 0)
        self.assertFalse(report["history_checked"])
        self.assertFalse(report["ready_to_save"])
        code, report = self.run_validator(None, "--existing-dir", str(self.directory / "missing"))
        self.assertEqual(code, 1)
        self.assertFalse(report["valid"])

    def test_existing_duplicates_and_internal_duplicates_block_save(self):
        (self.history / "previous.json").write_text(json.dumps(self.data))
        # Translation changes do not make a new learning item.
        self.data["cards"][0]["sentence_es"] = "Una traducción distinta."
        code, report = self.run_validator(None, "--existing-dir", str(self.history))
        self.assertEqual(code, 2)
        self.assertFalse(report["ready_to_save"])
        self.assertEqual(len(report["duplicates"]), 2)
        self.data["cards"].append(self.data["cards"][0])
        code, report = self.run_validator()
        self.assertEqual(code, 2)
        self.assertIn("inside batch", report["duplicates"][0]["matches"])

    def test_invalid_semantics_and_bad_history_block_validation(self):
        self.data["cards"][1]["answer"] = "not in sentence"
        code, report = self.run_validator()
        self.assertEqual(code, 1)
        self.assertFalse(report["valid"])
        (self.history / "bad.json").write_text('{"cards": []}')
        good = json.loads((ROOT / "examples/mixed.json").read_text())
        code, report = self.run_validator(good, "--existing-dir", str(self.history))
        self.assertEqual(code, 1)
        self.assertFalse(report["ready_to_save"])

    def test_repeated_json_keys_rejected(self):
        self.draft.write_text('{"schema_version":"1.0","schema_version":"2.0","cards":[]}')
        process = subprocess.run([sys.executable, str(SCRIPT), str(self.draft), "--date", "2026-10-13",
                                  "--topic", "daily-life"], capture_output=True, text=True)
        self.assertEqual(process.returncode, 1)
        self.assertIn("Repeated JSON key", json.loads(process.stdout)["error"])

    def test_invalid_date_and_path_slug_rejected(self):
        for extra in (("--date", "2026-02-30"), ("--topic", "../escape")):
            code, report = self.run_validator(None, *extra)
            self.assertEqual(code, 1)
            self.assertFalse(report["ready_to_save"])


if __name__ == "__main__":
    unittest.main()
