"""Build renamed OFL webfont subsets from the game's existing font families.

Rebuild with: python -m pip install 'fonttools[woff]'; python tools/build_site_fonts.py
Latin/extended Latin remains available for new locales; CJK copy is drawn from
the site's HTML and registered language packs. No source font is changed.
"""
from pathlib import Path
import hashlib
import json
import shutil

ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "server/site"


def main():
    from fontTools import subset
    from fontTools.ttLib import TTFont
    characters = set(range(0x20, 0x250)) | set(range(0x2000, 0x2070)) | set(range(0x2190, 0x2200))
    inputs = list(SITE.glob("*.html")) + list((ROOT / "config/site_locales").glob("*.json"))
    for path in inputs:
        characters.update(map(ord, path.read_text(encoding="utf-8")))
    output = SITE / "assets/fonts"
    output.mkdir(parents=True, exist_ok=True)
    result = {}
    for role, original, family, weight in [
        ("sans", "SourceHanSansSC-Regular.otf", "Relicbound Sans", 400),
        ("serif", "SourceHanSerifSC-SemiBold.otf", "Relicbound Serif", 600),
        ("arabic", "NotoSansArabicUI-Regular.ttf", "Relicbound Arabic", 400),
        ("arabic-title", "NotoSansArabicUI-SemiBold.ttf", "Relicbound Arabic Display", 600),
        ("devanagari", "NotoSansDevanagariUI-Regular.ttf", "Relicbound Devanagari", 400),
        ("devanagari-title", "NotoSansDevanagariUI-SemiBold.ttf", "Relicbound Devanagari Display", 600),
    ]:
        source = ROOT / "client/assets/fonts" / original
        font = TTFont(source, recalcTimestamp=False)
        covered = sorted(characters & set(font.getBestCmap()))
        options = subset.Options()
        options.flavor = "woff2"
        # Arabic joining and Indic reordering/conjuncts require the shaping tables.
        options.layout_features = ["*"]
        options.name_IDs = [0, 1, 2, 3, 4, 5, 6, 13, 14, 16, 17]
        options.name_legacy = True
        options.name_languages = [0x409]
        engine = subset.Subsetter(options=options)
        engine.populate(unicodes=covered)
        engine.subset(font)
        # Reserved Source Han family names cannot name a modified font.
        postscript = family.replace(" ", "")
        for entry in font["name"].names:
            if entry.nameID in [1, 3, 4, 6, 16]:
                value = postscript if entry.nameID in [3, 6] else family
                entry.string = value.encode(entry.getEncoding())
        if "CFF " in font:
            font["CFF "].cff.fontNames = [postscript]
            top = font["CFF "].cff.topDictIndex[0]
            top.FamilyName = family
            top.FullName = family
        target = output / f"relicbound-{role}.woff2"
        font.flavor = "woff2"
        font.save(target)
        result[role] = {"file": target.name, "family": family, "weight": weight,
                        "bytes": target.stat().st_size, "glyph_codepoints": covered,
                        "sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
                        "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest()}
        font.close()
    for license_name in ["LICENSE-SourceHanSans.txt", "LICENSE-SourceHanSerif.txt", "LICENSE-Noto.txt"]:
        shutil.copyfile(ROOT / "client/assets/fonts" / license_name, output / license_name)
    (output / "manifest.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({role: {k: v for k, v in value.items() if k != "glyph_codepoints"} for role, value in result.items()}))


if __name__ == "__main__":
    main()
