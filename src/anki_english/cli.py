import argparse
from collections import Counter
from html import unescape
from pathlib import Path
import subprocess
import sys

from pydantic import ValidationError

from .anki import AnkiConnect, AnkiError
from .audio import KokoroTTS
from .compiler import compile_card
from .config import load_config, api_key
from .service import publish
from .spec import CardBatch


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(prog="anki-en", description="Compile English CardSpec JSON into Anki cloze notes.")
    root.add_argument("--config", type=Path, help="Optional TOML config (default: built-in settings)")
    commands = root.add_subparsers(dest="command", required=True)
    commands.add_parser("init", help="Create/verify deck and cloze note type")
    check = commands.add_parser("check", help="Offline validation, lint and preview")
    check.add_argument("file", type=Path)
    for name in ("add", "paste"):
        sub = commands.add_parser(name, help="Publish JSON file" if name == "add" else "Publish macOS clipboard JSON")
        if name == "add":
            sub.add_argument("file", type=Path)
        sub.add_argument("--dry-run", action="store_true", help="Offline preview; no Anki/audio access")
        sub.add_argument("--no-audio", action="store_true", help="Explicitly publish without audio")
        sub.add_argument("--yes", action="store_true", help="Confirm publishing non-interactively")
    return root


def read_input(args) -> str:
    if args.command == "paste":
        if sys.platform != "darwin":
            raise ValueError("paste requires macOS. Use anki-en add cards.json on other systems.")
        try:
            return subprocess.run(["pbpaste"], capture_output=True, text=True,
                                  check=True, timeout=5).stdout
        except (OSError, subprocess.SubprocessError) as error:
            raise ValueError("Could not read macOS clipboard") from error
    return args.file.read_text(encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        config = load_config(args.config)
        if args.command == "init":
            AnkiConnect(config.anki, api_key()).initialize()
            print(f"Ready: {config.anki.deck}\nNote type: {config.anki.model}")
            return 0
        # Validate the whole batch before any network request or write.
        batch = CardBatch.model_validate_json(read_input(args))
        cards, seen = [], set()
        for index, spec in enumerate(batch.cards, 1):
            card = compile_card(spec)
            if card.uid in seen:
                print(f"SKIP {index:02}: duplicate inside this batch")
                continue
            seen.add(card.uid)
            cards.append(card)
            print(f"\n{index:02}. {spec.target}\n    {unescape(card.fields['Text'])}\n    {spec.meaning_es}")
            if spec.pattern:
                print(f"    Pattern: {spec.pattern}")
            if spec.example:
                print(f"    Example: {spec.example}")
            for warning in card.warnings:
                print(f"    WARN: {warning}")
        print(f"\nValid unique cards: {len(cards)}; warnings: {sum(len(c.warnings) for c in cards)}")
        if args.command == "check" or args.dry_run:
            print("Offline check complete. Existing Anki duplicates were not checked.")
            return 0
        gateway = AnkiConnect(config.anki, api_key())
        gateway.verify()
        pending = []
        for card in cards:
            if gateway.exists(card.uid):
                print(f"SKIP: {card.spec.target} — UID already exists")
            else:
                pending.append(card)
        if not pending:
            print("Nothing to publish.")
            return 0
        mode = "WITHOUT audio" if args.no_audio else "with Kokoro MP3 audio"
        print(f"Publish {len(pending)} cards to {config.anki.deck}, {mode}.")
        if not args.yes:
            if not sys.stdin.isatty():
                raise ValueError("Non-interactive session: use --yes to explicitly confirm publishing")
            if input("Publish? [y/N] ").strip().casefold() not in {"y", "yes"}:
                print("Cancelled. No notes/media were written.")
                return 0

        def emit(result):
            print(f"{result.status.upper()} {result.uid}: {result.note_id or result.message}", flush=True)

        outcomes = publish(pending, gateway, None if args.no_audio else KokoroTTS(config.tts), emit)
        counts = Counter(result.status for result in outcomes)
        print(f"Added: {counts['added']}; skipped: {counts['skipped']}; failed: {counts['failed']}; "
              f"not attempted: {len(pending) - len(outcomes)}")
        return 1 if counts["failed"] else 0
    except (OSError, ValueError, ValidationError, AnkiError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1
    except (KeyboardInterrupt, EOFError):
        print("\nInterrupted. If publishing had begun, rerun the same batch to check UIDs.", file=sys.stderr)
        return 130
