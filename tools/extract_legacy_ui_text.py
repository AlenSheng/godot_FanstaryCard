"""Move existing Chinese UI literals to reviewed, stable locale keys once."""
import json
from pathlib import Path
from audit_ui_text import ROOT, scan, literals


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main():
    data = ROOT / "client/data"
    packs = {code: read(data / "locales" / (code + ".json")) for code in ["zh-CN", "en", "es"]}
    for key, *values in read(ROOT / "config/localization_legacy_migration.json"):
        for code, text in zip(["zh-CN", "en", "es"], values):
            packs[code]["strings"][key] = text
    packs["es"]["monster_pool"] = {
        "title":"Cartas de monstruo del viaje", "capacity":"Absorbidas %d / %d", "accept":"Absorber",
        "skip":"Omitir", "replace":"Sustituir carta absorbida", "empty":"Sin cartas de monstruo pendientes",
        "hint":"Solo este viaje. Las cartas nuevas van al descarte y no dan robo extra.",
        "loot":"Botín registrable (aparte del equipo de combate)", "active_header":"Cartas de monstruo absorbidas",
        "empty_active":"Aún no has absorbido cartas de monstruo", "full_hint":"Reserva llena. Elige primero una carta absorbida que sustituir."}
    legacy = read(data / "localization_legacy.json")
    aliases = {text: key for key, text in packs["zh-CN"]["strings"].items()}
    for group in ["text_keys", "extra_text_keys", "inline_aliases"]:
        aliases.update(legacy[group])
    report = scan()
    missing = sorted({row["text"] for row in report["hardcoded_literals"] if row["text"] not in aliases})
    if missing:
        raise ValueError("Review missing literal translations first: " + repr(missing))
    touched = 0
    for relative in sorted(report["counts"]):
        path = ROOT / relative
        text = path.read_text(encoding="utf-8-sig")
        lines = text.splitlines(keepends=True)
        offsets, position = [], 0
        for line in lines:
            offsets.append(position)
            position += len(line)
        edits = []
        for token, value in literals(path):
            if value not in aliases:
                continue
            start = offsets[token.start[0] - 1] + token.start[1]
            end = offsets[token.end[0] - 1] + token.end[1]
            edits.append((start, end, 'P.localized(' + json.dumps(aliases[value]) + ')'))
        for start, end, replacement in reversed(edits):
            text = text[:start] + replacement + text[end:]
        if edits and 'const P = preload("res://ui/palette.gd")' not in text and path.name != "palette.gd":
            first_line = text.index("\n")
            text = text[:first_line+1] + '\nconst P = preload("res://ui/palette.gd")\n' + text[first_line+1:]
        path.write_text(text, encoding="utf-8")
        touched += len(edits)
    for code, pack in packs.items():
        write(data / "locales" / (code + ".json"), pack)
    print(json.dumps({"replaced_literals": touched, "files": len(report["counts"])}))


if __name__ == "__main__":
    main()
