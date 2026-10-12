"""Run from the repository root after installing the package."""

import json
from pathlib import Path
from anki_english.spec import schema

Path("schemas/card-spec-v1.schema.json").write_text(
    json.dumps(schema(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
)
