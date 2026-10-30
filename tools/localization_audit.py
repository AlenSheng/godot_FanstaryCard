"""Audit complete locale packs and compute a country-disjoint coverage bound.

Coverage uses CLDR functional-language populations: within each territory take
the largest supported language population, never add overlapping L1/L2 counts.
The resulting percentage is an estimate, not a count of unique surveyed users.
Draft or unreviewed locales do not count towards released coverage.
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "client/data"
TOKENS = re.compile(r"%(?:[-+0#]*\d*(?:\.\d+)?[sdf]|%)|\{[A-Za-z_]\w*\}")


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def source_strings(language="en"):
    return read(DATA / "locales" / (language + ".json"))["strings"]


def audit_pack(code, entry):
    path = ROOT / "client" / entry["path"].removeprefix("res://")
    pack = read(path)
    source = source_strings()
    strings = pack.get("strings", {})
    errors = []
    for key in ["codex_base_effect", "card_tuning_contract"]:
        if not strings.get(key, "").strip():
            errors.append({"kind": "missing_dynamic_copy", "key": key})
    for key, text in source.items():
        if key not in strings:
            errors.append({"kind": "missing", "key": key})
            continue
        translated = strings[key]
        if not isinstance(translated, str) or (text and not translated.strip()):
            errors.append({"kind": "empty", "key": key})
        elif Counter(TOKENS.findall(text)) != Counter(TOKENS.findall(translated)):
            errors.append({"kind": "format", "key": key,
                           "expected": TOKENS.findall(text), "actual": TOKENS.findall(translated)})
        if isinstance(translated, str) and "\ufffd" in translated:
            errors.append({"kind": "replacement_character", "key": key})
    names = {row["id"] for row in read(DATA / "catalog.json")["tables"]["Cards"]}
    for key in names:
        if not pack.get("card_names", {}).get(key, "").strip():
            errors.append({"kind": "card_name", "key": key})
    for key, value in pack.get("card_face_names", {}).items():
        if key not in names or not isinstance(value, str) or not value.strip():
            errors.append({"kind": "invalid_compact_card_name", "key": key})
    compare = read(DATA / "locales/en.json")["equipment_compare"]
    for key, text in compare.items():
        translated = pack.get("equipment_compare", {}).get(key, "")
        if not translated.strip():
            errors.append({"kind": "equipment_compare", "key": key})
        elif Counter(TOKENS.findall(text)) != Counter(TOKENS.findall(translated)):
            errors.append({"kind": "equipment_compare_format", "key": key})
    for key, text in read(DATA / "locales/en.json")["monster_pool"].items():
        translated = pack.get("monster_pool", {}).get(key, "")
        if not translated.strip():
            errors.append({"kind": "missing_monster_pool", "key": key})
        elif Counter(TOKENS.findall(text)) != Counter(TOKENS.findall(translated)):
            errors.append({"kind": "monster_pool_format", "key": key})
    numerical_source = read(DATA / "locales/en.json")["numerical"]
    for section, values in numerical_source.items():
        translated = pack.get("numerical", {}).get(section, {} if isinstance(values, dict) else [])
        rows = values.items() if isinstance(values, dict) else enumerate(values)
        for key, text in rows:
            value = translated.get(key, "") if isinstance(translated, dict) else (translated[key] if key < len(translated) else "")
            if not value or not str(value).strip():
                errors.append({"kind": "missing_numerical", "section": section, "key": key})
            elif Counter(TOKENS.findall(text)) != Counter(TOKENS.findall(value)):
                errors.append({"kind": "numerical_format", "section": section, "key": key})
    return {"code": code, "ok": not errors, "strings": len(strings),
            "source_strings": len(source), "card_names": len(pack.get("card_names", {})),
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "errors": errors}


def coverage(codes, dataset):
    # Script distinctions are explicit: zh-CN must not automatically count
    # zh_Hant, Cantonese, or other Chinese languages as covered.
    mapped = {"zh" if c == "zh-CN" else c.replace("-", "_") for c in codes}
    territories = dataset["supplemental"]["territoryInfo"]
    rows = []
    for country, info in sorted(territories.items()):
        population = float(info.get("_population", 0))
        matches = [(float(lang.get("_populationPercent", 0)), code)
                   for code, lang in info.get("languagePopulation", {}).items() if code in mapped]
        percentage, language = max(matches, default=(0, None))
        percentage = min(100, max(0, percentage))
        rows.append({"territory": country, "population": population,
                     "language": language, "covered_percent_lower_bound": percentage,
                     "covered_population_lower_bound": population * percentage / 100})
    total = sum(row["population"] for row in rows)
    covered = sum(row["covered_population_lower_bound"] for row in rows)
    return {"method": "sum_territory_population_times_max_supported_language_share",
            "language_codes": sorted(codes), "population_denominator": total,
            "covered_population_lower_bound": covered,
            "coverage_lower_bound_percent": 100 * covered / total if total else 0,
            "territories": rows}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--locale", action="append", help="Audit only these registered locales")
    args = parser.parse_args()
    registry = read(DATA / "localization_registry.json")
    packs = {c: e for c, e in registry["languages"].items() if not args.locale or c in args.locale}
    unknown = sorted(set(args.locale or []) - packs.keys())
    results = [audit_pack(code, entry) for code, entry in packs.items()]
    released = ["zh-CN", "en"] + [c for c, e in registry["languages"].items() if e.get("status") == "released"]
    candidate = ["zh-CN", "en"] + list(packs)
    dataset = read(ROOT / "config/localization_coverage_source.json")
    all_codes = {c for t in dataset["supplemental"]["territoryInfo"].values()
                 for c in t.get("languagePopulation", {})}
    report = {"ok": bool(results) and not unknown and all(r["ok"] for r in results),
              "unknown_locales": unknown, "packs": results,
              "released_coverage": coverage(released, dataset),
              "candidate_coverage": coverage(candidate, dataset),
              "dataset_maximum_coverage_percent": coverage(all_codes, dataset)["coverage_lower_bound_percent"],
              "coverage_target_percent": 80,
              "review_gate": "Independent UI and website review required before release"}
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"ok": report["ok"], "packs": results,
                      "released_coverage_percent": report["released_coverage"]["coverage_lower_bound_percent"],
                      "candidate_coverage_percent": report["candidate_coverage"]["coverage_lower_bound_percent"],
                      "dataset_maximum_coverage_percent": report["dataset_maximum_coverage_percent"]}, ensure_ascii=True))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
