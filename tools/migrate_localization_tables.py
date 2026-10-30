"""One-time consolidation of legacy language dictionaries into locale packs.

Retains the old JSON files for historical tooling; production code reads the
registry and locale packs. Refuses to overwrite already consolidated packs.
"""
import ast
import io
import json
from pathlib import Path
import re
import tokenize

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "client/data"


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def literal(text, name):
    match = re.search(r"^const " + re.escape(name) + r"\s*:?=\s*", text, re.M)
    if not match:
        raise ValueError(name)
    value, length = json.JSONDecoder().raw_decode(text[match.end():])
    return value, (match.start(), match.end() + length)


def main():
    if (DATA / "locales/en.json").exists() or (DATA / "locales/zh-CN.json").exists():
        raise SystemExit("Already consolidated; edit the locale packs directly")
    palette_path = ROOT / "client/ui/palette.gd"
    palette = palette_path.read_text(encoding="utf-8")
    legacy = {}
    edits = []
    for constant in ["WORDS", "CLASSES", "TEXT_KEYS", "EXTRA_TEXT_KEYS"]:
        value, (start, end) = literal(palette, constant)
        legacy[constant.lower()] = value
        edits.append((start, end, f'static var {constant}: Dictionary = LEGACY_DATA.data.{constant.lower()}'))
    extra = re.search(r"aliases\.merge\((\{[^\n]+\})\)", palette)
    legacy["inline_aliases"] = json.loads(extra.group(1))
    edits.append((extra.start(), extra.end(), "aliases.merge(LEGACY_DATA.data.inline_aliases)"))
    for start, end, replacement in sorted(edits, reverse=True):
        palette = palette[:start] + replacement + palette[end:]
    palette = palette.replace("extends RefCounted\n", 'extends RefCounted\n\nconst LEGACY_DATA = preload("res://data/localization_legacy.json")\n', 1)
    palette_path.write_text(palette, encoding="utf-8")
    sources = ["localization_config.json", "localization_modules.json", "localization_templates.json",
               "localization_brand.json", "login_localization.json", "localization_battle.json", "localization_ui_gaps.json"]
    config = read(DATA / "localization_config.json")
    names = read(DATA / "card_names.json")
    descriptions = read(DATA / "card_descriptions.json")
    compare = read(DATA / "equipment_compare_text.json")
    numerical_path = ROOT / "client/ui/numerical_details.gd"
    numerical_text = numerical_path.read_text(encoding="utf-8")
    numerical_keys = {"text":"TEXT", "cap_text":"CAP_TEXT", "stat_text":"STAT_TEXT",
                      "guardian_rules":"GUARDIAN_REMAINDER_RULES", "guardian_impact":"GUARDIAN_IMPACT"}
    numerical = {key: literal(numerical_text, value)[0] for key, value in numerical_keys.items()}
    pool_path = ROOT / "client/ui/monster_pool_view.gd"
    pool_text = pool_path.read_text(encoding="utf-8")
    pool, pool_span = literal(pool_text, "TEXT")
    pool_text = pool_text[:pool_span[0]] + pool_text[pool_span[1]:]
    pool_text = pool_text.replace('var dictionary: Dictionary = TEXT.get(lang, TEXT.get(lang.get_slice("-", 0), TEXT.en))', 'var dictionary: Dictionary = P.language_pack_section("monster_pool")')
    pool_path.write_text(pool_text, encoding="utf-8")
    catalog = read(DATA / "catalog.json")
    chinese_names = {card["id"]: card["name"] for card in catalog["tables"]["Cards"]}
    card_source = (ROOT / "client/ui/card_details.gd").read_text(encoding="utf-8")
    literals = [ast.literal_eval(t.string) for t in tokenize.generate_tokens(io.StringIO(card_source).readline)
                if t.type == tokenize.STRING]
    registry = read(DATA / "localization_registry.json")
    entries = {}
    for code in ["zh-CN", "en"]:
        strings = {}
        for filename in sources:
            strings.update(read(DATA / filename)["languages"][code].get("strings", {}))
        strings["codex_base_effect"] = "基础：" if code == "zh-CN" else "Base: "
        strings["card_tuning_contract"] = next(value for value in literals if value.startswith("首张元素牌定核" if code == "zh-CN" else "The first elemental card sets"))
        pack = {"strings": strings, "card_names": chinese_names if code == "zh-CN" else names["en"],
                "card_descriptions": descriptions.get("zh" if code == "zh-CN" else "en", {}),
                "equipment_compare": compare[code], "numerical": {key: value[code] for key, value in numerical.items()},
                "monster_pool": pool[code]}
        write(DATA / "locales" / (code + ".json"), pack)
        entries[code] = {"name": config["languages"][code]["name"], "fonts": config["languages"][code]["fonts"],
                         "direction": "ltr", "path": "res://data/locales/" + code + ".json", "status": "baseline"}
    entries.update(registry["languages"])
    for code, entry in entries.items():
        entry.setdefault("fonts", config["languages"]["en"]["fonts"])
    registry.update({"default_language": "zh-CN", "languages": entries})
    write(DATA / "localization_registry.json", registry)
    for path, name, key in [(ROOT / "client/ui/card_view.gd", "CLASS_NAMES", "card_class_names"),
                            (ROOT / "client/ui/codex_view.gd", "SOUL_NAMES", "soul_names")]:
        text = path.read_text(encoding="utf-8")
        value, (start, end) = literal(text, name)
        legacy[key] = value
        text = text[:start] + f'static var {name}: Dictionary = preload("res://data/localization_legacy.json").data.{key}' + text[end:]
        path.write_text(text, encoding="utf-8")
    write(DATA / "localization_legacy.json", legacy)
    partial = {code: {"numerical": {key: value[code] for key, value in numerical.items()}, "monster_pool": pool[code]}
               for code in ["zh-TW", "ja", "ko"]}
    write(ROOT / "config/localization_partial_packs.json", partial)
    # Preserve all existing translations; these partial packs are not enabled.
    numeric_end = numerical_text.index("static func stat_name")
    numerical_text = numerical_text[:numerical_text.index("const GUARDIAN_REMAINDER_RULES")] + numerical_text[numeric_end:]
    numerical_text = re.sub(r"var words: Dictionary = STAT_TEXT[^\n]+\n\s*words = P.language_pack_section\(\"numerical\"\)\.get\(\"stat_text\", words\)", 'var words: Dictionary = P.language_pack_section("numerical").get("stat_text", {})', numerical_text)
    numerical_text = re.sub(r'var words: Dictionary = TEXT[^\n]+\n\s*var cap_words: Dictionary = CAP_TEXT[^\n]+\n\s*var pack := P.language_pack_section\("numerical"\)\n\s*words = pack.get\("text", words\)\n\s*cap_words = pack.get\("cap_text", cap_words\)', 'var pack := P.language_pack_section("numerical")\n\tvar words: Dictionary = pack.get("text", {})\n\tvar cap_words: Dictionary = pack.get("cap_text", {})', numerical_text)
    numerical_text = numerical_text.replace('pack.get("guardian_impact", GUARDIAN_IMPACT.get(P.language(), GUARDIAN_IMPACT.en))', 'pack.get("guardian_impact", {})')
    numerical_text = numerical_text.replace('pack.get("guardian_rules", GUARDIAN_REMAINDER_RULES.get(P.language(), GUARDIAN_REMAINDER_RULES.en))', 'pack.get("guardian_rules", [])')
    numerical_path.write_text(numerical_text, encoding="utf-8")
    print(json.dumps({"consolidated": ["zh-CN", "en"], "preserved_partial": list(partial)}))


if __name__ == "__main__":
    main()
