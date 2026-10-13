#!/usr/bin/env python3
"""Offline CardSpec validation using the real project runtime; no network/writes."""
import argparse
from collections import Counter
from datetime import date
import hashlib
import json
from pathlib import Path
import re
import sys


def load_json(path):
    def unique_keys(pairs):
        value = {}
        for key, item in pairs:
            if key in value:
                raise ValueError(f"Repeated JSON key: {key}")
            value[key] = item
        return value
    return json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=unique_keys)


def inspect(args):
    session_date = date.fromisoformat(args.date)
    if session_date.isoformat() != args.date:
        raise ValueError("Use a real date in YYYY-MM-DD format")
    if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", args.topic) or len(args.topic) > 60:
        raise ValueError("Topic must be a lowercase kebab-case slug, at most 60 characters")
    runtime = args.repo.resolve() / "src" if args.repo else Path(__file__).resolve().parent / "runtime"
    for name in ("spec.py", "compiler.py"):
        if not (runtime / "anki_english" / name).is_file():
            raise ValueError(f"Missing project runtime file: {name}")
    sys.path.insert(0, str(runtime))
    from anki_english.spec import CardBatch
    from anki_english.compiler import compile_card

    raw = load_json(args.file)
    # model_validate_json preserves the real CLI's strict JSON/date semantics.
    batch = CardBatch.model_validate_json(json.dumps(raw, ensure_ascii=False))
    known = {}
    file_count = 0
    if args.existing_dir:
        if not args.existing_dir.is_dir():
            raise ValueError("Existing sessions directory is missing; do not assume history is empty")
        for path in sorted(args.existing_dir.rglob("*.json")):
            previous = CardBatch.model_validate_json(json.dumps(load_json(path), ensure_ascii=False))
            file_count += 1
            for spec in previous.cards:
                uid = compile_card(spec).uid
                known.setdefault(uid, []).append(str(path.relative_to(args.existing_dir)))
    seen = set()
    duplicates = []
    preview = []
    counts = Counter()
    for index, spec in enumerate(batch.cards, 1):
        card = compile_card(spec)
        counts[spec.kind] += 1
        reasons = []
        if card.uid in seen:
            reasons.append("inside batch")
        if card.uid in known:
            reasons.extend(known[card.uid])
        if reasons:
            duplicates.append({"index": index, "uid": card.uid, "matches": reasons})
        seen.add(card.uid)
        warnings = list(card.warnings)
        if spec.sentence_es is None:
            warnings.append("Missing full Spanish translation; review whether it can be supplied.")
        preview.append({"index": index, "uid": card.uid, "kind": spec.kind,
                        "target": spec.target, "cloze": card.fields["Text"], "warnings": warnings})
    canonical = json.dumps(batch.model_dump(mode="json"), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(canonical.encode()).hexdigest()[:12]
    return {
        "valid": True, "ready_to_save": not duplicates and args.existing_dir is not None,
        "runtime": "live-checkout" if args.repo else "bundled-snapshot",
        "runtime_hashes": {name: hashlib.sha256((runtime / "anki_english" / name).read_bytes()).hexdigest()
                           for name in ("spec.py", "compiler.py")},
        "history_checked": args.existing_dir is not None, "history_files": file_count,
        "counts": dict(counts), "duplicates": duplicates, "cards": preview,
        "suggested_path": f"card-specs/sessions/{args.date}/{args.topic}-{digest}.json",
        "checks_not_automated": ["current GitHub contract freshness", "history download completeness",
                                 "personal-error evidence", "linguistic accuracy", "near-duplicate learning goals"],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("file", type=Path)
    parser.add_argument("--date", required=True)
    parser.add_argument("--topic", required=True)
    parser.add_argument("--existing-dir", type=Path, help="Complete snapshot of session JSON files; may be empty")
    parser.add_argument("--repo", type=Path, help="Verified checkout containing the current project runtime")
    args = parser.parse_args()
    try:
        result = inspect(args)
    except (OSError, ValueError, ImportError) as error:
        print(json.dumps({"valid": False, "ready_to_save": False, "error": str(error)}, ensure_ascii=False))
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 2 if result["duplicates"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
