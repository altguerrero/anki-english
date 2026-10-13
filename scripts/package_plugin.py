"""Validate and package the private ChatGPT plugin; no network calls."""
import argparse
import hashlib
import json
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / "plugins/anki-english-coach"


def package(destination):
    destination = destination.resolve()
    if destination.is_relative_to(PLUGIN):
        raise ValueError("Write the archive outside the plugin directory")
    manifest = json.loads((PLUGIN / "plugin.json").read_text())
    assert manifest["name"] == PLUGIN.name
    interface = manifest["extensions"]["com.openai"]["interface"]
    assert len(interface["shortDescription"]) <= 30
    for key in ("logo", "composerIcon"):
        asset = (PLUGIN / interface[key]).resolve()
        assert asset.is_relative_to(PLUGIN) and asset.is_file()
    skill = PLUGIN / "skills/create-english-cards"
    snapshot = json.loads((skill / "references/contract-snapshot.json").read_text())
    for name, expected in snapshot["sha256"].items():
        actual = hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
        if actual != expected:
            raise ValueError(f"Contract snapshot is stale: {name}; refresh the plugin before packaging")
    for name in ("spec.py", "compiler.py"):
        if (ROOT / "src/anki_english" / name).read_bytes() != (skill / "scripts/runtime/anki_english" / name).read_bytes():
            raise ValueError(f"Bundled runtime differs: {name}")
    if (ROOT / "schemas/card-spec-v1.schema.json").read_bytes() != (skill / "references/card-spec-v1.schema.json").read_bytes():
        raise ValueError("Bundled schema differs")
    files = [p for p in sorted(PLUGIN.rglob("*")) if p.is_file() and "__pycache__" not in p.parts and p.suffix != ".pyc"]
    if any(p.is_symlink() for p in PLUGIN.rglob("*")):
        raise ValueError("Plugin must not contain symlinks")
    with zipfile.ZipFile(destination, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in files:
            archive.write(path, path.relative_to(PLUGIN.parent))
    print(f"Packaged {len(files)} files: {destination}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("destination", type=Path)
    package(parser.parse_args().destination)
