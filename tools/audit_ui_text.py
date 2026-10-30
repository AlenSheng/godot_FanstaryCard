"""Find fixed human-language literals in production GDScript and scene text."""
import argparse
import ast
from collections import Counter
import io
import json
from pathlib import Path
import re
import tokenize

ROOT = Path(__file__).resolve().parents[1]
HAN = re.compile(r"[\u3400-\u9fff]")
ENGLISH_PROSE = re.compile(r"[A-Za-z]{2}(?:\s|[.:!?]\s)")
UI_ASSIGNMENT = re.compile(r"\.(?:text|tooltip_text|placeholder_text|title|dialog_text)\s*=\s*$")
UI_CALL = re.compile(r"\b(?:_?label|_?button|_?text|_?toast)\(\s*$")
SECTION_LOOKUP = re.compile(r'(?:\b(?:MonsterPool|NumericalDetails)\.text|preload\("res://ui/(?:numerical_details|monster_pool_view)\.gd"\)\.text)\(\s*$')


def human_literal(value, prefix=""):
    if HAN.search(value):
        return True
    if value.startswith(("res://", "user://", "http://", "https://", "(?", "application/")):
        return False
    prose = re.sub(r"%(?:[-+0#]*\d*(?:\.\d+)?[sdf]|%)|\{[A-Za-z_]\w*\}", "", value)
    return bool(ENGLISH_PROSE.search(prose) or
                (re.search(r"[A-Za-z]", prose) and (UI_ASSIGNMENT.search(prefix) or UI_CALL.search(prefix))))


def literals(path):
    source = path.read_text(encoding="utf-8-sig")
    for token in tokenize.generate_tokens(io.StringIO(source).readline):
        if token.type != tokenize.STRING:
            continue
        try:
            value = ast.literal_eval(token.string)
        except (SyntaxError, ValueError):
            continue
        if isinstance(value, str):
            yield token, value


def scan():
    rows, errors = [], []
    source_path = ROOT / "client/data/locales/en.json"
    known_keys = set(json.loads(source_path.read_text(encoding="utf-8"))["strings"]) if source_path.exists() else set()
    nested_keys = set()
    if source_path.exists():
        source_pack = json.loads(source_path.read_text(encoding="utf-8"))
        nested_keys.update(source_pack.get("monster_pool", {}))
        for section in source_pack.get("numerical", {}).values():
            if isinstance(section, dict): nested_keys.update(section)
    missing_keys = []
    exceptions_path = ROOT / "config/localization_literal_exceptions.json"
    exceptions = json.loads(exceptions_path.read_text(encoding="utf-8"))["exceptions"] if exceptions_path.exists() else []
    allowed = {(entry["path"], entry["text"]): entry["reason"] for entry in exceptions}
    classified = []
    for path in sorted((ROOT / "client").rglob("*.gd")):
        if "tests" in path.parts or ".godot" in path.parts:
            continue
        try:
            lines = path.read_text(encoding="utf-8-sig").splitlines()
            relative = str(path.relative_to(ROOT)).replace("\\", "/")
            for token, value in literals(path):
                prefix = lines[token.start[0] - 1][:token.start[1]]
                suffix = lines[token.end[0] - 1][token.end[1]:].lstrip()
                if re.search(r"\bP\.localized\(\s*$", prefix) and suffix.startswith(")") and value not in known_keys:
                    missing_keys.append({"path": relative, "line": token.start[0], "key": value})
                if human_literal(value, prefix):
                    if UI_CALL.search(prefix) and value in known_keys:
                        continue  # These helpers resolve stable catalog keys.
                    if path.name in ["numerical_details.gd", "monster_pool_view.gd"] and UI_CALL.search(prefix) and value in nested_keys:
                        continue
                    if SECTION_LOOKUP.search(prefix) and value in nested_keys:
                        continue
                    if (relative, value) in allowed:
                        classified.append({"path": relative, "line": token.start[0], "reason": allowed[(relative, value)]})
                        continue
                    rows.append({"path": relative,
                                 "line": token.start[0], "column": token.start[1], "text": value})
        except (tokenize.TokenError, IndentationError) as error:
            errors.append({"path": str(path), "error": str(error)})
    # Serialized controls can otherwise reintroduce language-specific defaults
    # even when their scripts use stable keys correctly.
    for pattern in ("*.tscn", "*.tres"):
        for path in sorted((ROOT / "client").rglob(pattern)):
            if "tests" in path.parts or ".godot" in path.parts:
                continue
            for line_number, line in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), 1):
                match = re.match(r'\s*(?:text|placeholder_text|tooltip_text|title|dialog_text)\s*=\s*(".*")\s*$', line)
                if not match:
                    continue
                value = ast.literal_eval(match.group(1))
                if human_literal(value, "label.text = "):
                    rows.append({"path": path.relative_to(ROOT).as_posix(), "line": line_number,
                                 "column": 0, "text": value})
    return {"ok": not rows and not errors and not missing_keys, "hardcoded_literals": rows, "parse_errors": errors, "missing_keys": missing_keys, "classified_technical_literals": classified,
            "counts": dict(Counter(row["path"] for row in rows))}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = scan()
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"ok": report["ok"], "hardcoded_literals": len(report["hardcoded_literals"]),
                      "counts": report["counts"], "parse_errors": report["parse_errors"], "missing_keys": report["missing_keys"]}, ensure_ascii=True))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
