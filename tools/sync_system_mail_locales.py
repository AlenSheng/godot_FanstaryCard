"""Export system mail copy from the runtime locale packs; --check never writes.

The sole authoring source is client/data/locales/*.json (the strings section).
Generated server/config/system_mail_locales.json must not be edited manually.
This exporter does not render templates. Runtime substitution must visit source
tokens once and preserve inserted administrator text, including braces, verbatim.
"""

from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import re
import sys


ROOT = Path(__file__).resolve().parents[1]
SOURCE_DIR = ROOT / "client/data/locales"
DEFAULT_OUTPUT = ROOT / "server/config/system_mail_locales.json"
SEED_IDS = (
    "seed_gold", "seed_souls", "seed_white_fire", "seed_green_water",
    "seed_blue_earth", "seed_purple_wood", "seed_orange_metal",
    "seed2_mixed_set", "seed2_fragments",
)
FIXED_KEYS = frozenset({
    "mail_item_reclamation_title", "mail_item_reclamation_body",
    "system_sender", "admin_sender", "traveler_default_name",
})
SEED_KEY = re.compile(r"mail_seed2?_[a-z0-9_]+_(?:title|body)\Z")
PARAMETER = re.compile(r"\{([a-z][a-z0-9_]*)\}")
REQUIRED_KEYS = FIXED_KEYS | {
    f"mail_{seed_id}_{field}"
    for seed_id in SEED_IDS
    for field in ("title", "body")
}


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate JSON key: {key}")
        result[key] = value
    return result


def _parameters(value: str) -> Counter:
    remainder = PARAMETER.sub("", value)
    if "{" in remainder or "}" in remainder:
        raise ValueError("Unsupported or unmatched template braces")
    return Counter(PARAMETER.findall(value))


def build_document(locale_dir: Path) -> dict:
    """Read complete packs and validate selected keys before any output write."""
    paths = sorted(locale_dir.glob("*.json"))
    if not paths:
        raise ValueError(f"No runtime locale packs found in {locale_dir}")
    locales = {}
    reference_keys = None
    reference_locale = None
    for path in paths:
        try:
            pack = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_unique_object)
        except (ValueError, UnicodeError) as error:
            raise ValueError(f"Invalid locale pack {path}: {error}") from error
        if not isinstance(pack, dict) or not isinstance(pack.get("strings"), dict):
            raise ValueError(f"{path}: strings must be a JSON object")
        selected = {
            key: value for key, value in pack["strings"].items()
            if key in FIXED_KEYS or SEED_KEY.fullmatch(key)
        }
        missing = REQUIRED_KEYS - selected.keys()
        if missing:
            raise ValueError(f"{path}: missing system mail keys: {', '.join(sorted(missing))}")
        for key, value in selected.items():
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{path}: {key} must be a nonempty string")
            try:
                parameters = _parameters(value)
            except ValueError as error:
                raise ValueError(f"{path}: {key}: {error}") from error
            expected = Counter({"kind": 1, "amount": 1, "reason": 1}) if key == "mail_item_reclamation_body" else Counter()
            if parameters != expected:
                raise ValueError(f"{path}: {key}: expected parameters {dict(expected)}, got {dict(parameters)}")
            if SEED_KEY.fullmatch(key):
                prefix = key.rsplit("_", 1)[0]
                for field in ("title", "body"):
                    if f"{prefix}_{field}" not in selected:
                        raise ValueError(f"{path}: incomplete system mail pair: {prefix}")
        if reference_keys is not None and set(selected) != reference_keys:
            missing_reference = reference_keys - selected.keys()
            extra = selected.keys() - reference_keys
            raise ValueError(
                f"{path}: system mail keys differ from {reference_locale}; "
                f"missing={sorted(missing_reference)}, extra={sorted(extra)}"
            )
        reference_keys = set(selected)
        reference_locale = path.stem
        locales[path.stem] = dict(sorted(selected.items()))
    return {"schema_version": 1, "locales": locales}


def render_document(document: dict) -> str:
    return json.dumps(document, ensure_ascii=False, indent=2) + "\n"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Fail if the generated file is missing or out of date; never write")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help="Generated destination (default: server/config/system_mail_locales.json)")
    args = parser.parse_args(argv)
    try:
        document = build_document(SOURCE_DIR)
        expected = render_document(document)
        current = args.output.read_text(encoding="utf-8") if args.output.exists() else None
        matches = current == expected
        summary = {
            "ok": matches if args.check else True,
            "check": args.check,
            "output": str(args.output),
            "locales": {code: len(values) for code, values in document["locales"].items()},
        }
        if args.check:
            if not matches:
                summary["reason"] = "missing_generated_file" if current is None else "outdated_generated_file"
            print(json.dumps(summary, ensure_ascii=True))
            return 0 if matches else 1
        if not matches:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            with args.output.open("w", encoding="utf-8", newline="\n") as output:
                output.write(expected)
        summary["changed"] = not matches
        print(json.dumps(summary, ensure_ascii=True))
        return 0
    except (OSError, ValueError) as error:
        print(json.dumps({"ok": False, "error": str(error)}, ensure_ascii=True), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
