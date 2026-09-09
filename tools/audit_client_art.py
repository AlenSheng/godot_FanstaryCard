"""Audit delivered UI requests, alpha channels, and current Godot bindings.

This reads imported assets without changing them. Contact sheets composite RGBA
onto real colored backgrounds; raw PNG previews can expose invisible RGB data.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parents[1]
ART = ROOT / "client/assets/imported"
OUTPUT = ROOT / "outputs"
OLD_MONSTERS = {
    "CLEAN-MON-FIRE-BAT": "UI/Monsters/fire_bat.png",
    "CLEAN-MON-RUST-RAT": "UI/Monsters/rustblade_rat.png",
    "CLEAN-MON-STONE-GUARD": "UI/Monsters/stone_guardian.png",
    "PENDING-FROST-WRAITH": "UI/Monsters/frost_wraith.png",
}


def inspect_image(path: Path, manifest: dict) -> dict:
    key = path.relative_to(ART).as_posix()
    result = {"key": key, "path": path.relative_to(ROOT).as_posix(), "exists": path.is_file()}
    if not path.is_file():
        return result
    with Image.open(path) as source:
        image = source.convert("RGBA")
        histogram = image.getchannel("A").histogram()
        area = image.width * image.height
        sha = hashlib.sha256(path.read_bytes()).hexdigest()
        record = manifest.get("files", {}).get(key, {})
        result.update({
            "size_px": list(image.size),
            "mode": source.mode,
            "sha256": sha,
            "alpha_extrema": list(image.getchannel("A").getextrema()),
            "alpha_zero_percent": round(100 * histogram[0] / area, 4),
            "alpha_opaque_percent": round(100 * histogram[255] / area, 4),
            "alpha_partial_percent": round(100 * sum(histogram[1:255]) / area, 4),
            "registered": bool(record),
            "matches_recorded_source_sha256": sha == record.get("source_sha256") if record else None,
            "matches_recorded_imported_sha256": sha == record.get("imported_sha256") if record else None,
        })
        if key == "UI/Cards/card_frame_monster_clean.png":
            result["diagnostics"] = {
                "top_40px_alpha_extrema": list(image.crop((0, 0, image.width, 40)).getchannel("A").getextrema()),
                "illustration_window_alpha_extrema": list(image.crop((70, 80, 365, 445)).getchannel("A").getextrema()),
                "note": "RGB checker colors mostly have alpha zero; top ornament is erased. See composited contact sheet and manual review.",
            }
    return result


def contact_sheet(paths: list[Path], destination: Path, dark: bool = False) -> None:
    columns, cell_width, cell_height = 4, 320, 365
    sheet = Image.new("RGB", (columns * cell_width, ((len(paths) + columns - 1) // columns) * cell_height), (20, 39, 41) if dark else (218, 218, 210))
    draw = ImageDraw.Draw(sheet)
    font_path = Path("C:/Windows/Fonts/arial.ttf")
    font = ImageFont.truetype(str(font_path), 16) if font_path.is_file() else ImageFont.load_default()
    for index, path in enumerate(paths):
        x, y = (index % columns) * cell_width, (index // columns) * cell_height
        if not dark:
            for dx in range(0, cell_width, 20):
                for dy in range(0, 320, 20):
                    shade = (185, 190, 183) if (dx // 20 + dy // 20) % 2 else (223, 222, 212)
                    draw.rectangle((x + dx, y + dy, x + dx + 19, y + dy + 19), fill=shade)
        with Image.open(path) as source:
            image = source.convert("RGBA")
            image.thumbnail((308, 315), Image.Resampling.LANCZOS)
            sheet.paste(image, (x + (cell_width - image.width) // 2, y + (320 - image.height) // 2), image)
        draw.text((x + 5, y + 327), path.stem, font=font, fill=(234, 235, 220) if dark else (24, 28, 26))
    sheet.save(destination, quality=94)


def native_monster_contact(prefix: str = "current") -> dict | None:
    preview = ROOT / "client/evidence/art"
    paths = [preview / f"monsters_{index}_1920.png" for index in range(1, 7)]
    if not all(path.is_file() for path in paths) or not (preview / "report.json").is_file():
        return None
    sheet = Image.new("RGB", (1440, 2520), (14, 24, 25))
    draw = ImageDraw.Draw(sheet)
    font = ImageFont.truetype("C:/Windows/Fonts/arial.ttf", 18)
    for index, path in enumerate(paths):
        with Image.open(path) as source:
            battle = source.crop((1000, 120, 1810, 610))
            battle.thumbnail((820, 390), Image.Resampling.LANCZOS)
            sheet.paste(battle, (0, index * 420 + 25))
            cards = source.crop((450, 620, 910, 1002))
            cards.thumbnail((610, 390), Image.Resampling.LANCZOS)
            sheet.paste(cards, (845, index * 420 + 25))
        draw.text((8, index * 420 + 2), path.name, font=font, fill=(238, 230, 215))
    sheet.save(OUTPUT / f"{prefix}_native_monster_review.jpg", quality=94)
    return {
        "report": "client/evidence/art/report.json",
        "report_result": json.loads((preview / "report.json").read_text(encoding="utf-8")),
        "contact_sheet": f"outputs/{prefix}_native_monster_review.jpg",
        "visual_review_scope": "Six pairs of monster subjects and cards, earth intent icon, and boss phase previews. Other screens are covered by layout assertions, not asserted as individually visually reviewed here.",
    }


def native_p2_contact() -> dict | None:
    preview = ROOT / "client/evidence/art"
    names = [
        "shop", "shop_tail", "hall_priest", "hall_guardian", "prep_priest", "gear_guardian",
        "action", "map", "choose", "pvp", "passive_priest_pvp", "passive_guardian_pvp",
    ]
    paths = [preview / f"{name}_1920.png" for name in names]
    paths = [path for path in paths if path.is_file()]
    if not paths:
        return None
    cell_width, cell_height = 960, 568
    sheet = Image.new("RGB", (1920, ((len(paths) + 1) // 2) * cell_height), (14, 24, 25))
    draw = ImageDraw.Draw(sheet)
    font = ImageFont.truetype("C:/Windows/Fonts/arial.ttf", 18)
    for index, path in enumerate(paths):
        x, y = (index % 2) * cell_width, (index // 2) * cell_height
        with Image.open(path) as source:
            image = source.convert("RGB")
            image.thumbnail((cell_width, 540), Image.Resampling.LANCZOS)
            sheet.paste(image, (x, y + 28))
        draw.text((x + 6, y + 4), path.name, font=font, fill=(238, 230, 215))
    destination = OUTPUT / "p2_native_ui_review.jpg"
    sheet.save(destination, quality=94)
    return {
        "contact_sheet": destination.relative_to(ROOT).as_posix(),
        "screenshots": [path.relative_to(ROOT).as_posix() for path in paths],
        "note": "Contact sheet for manual review; image generation does not itself certify visual quality.",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase", choices=("p1", "p2"), default="p1", help="Select contact-sheet coverage; all requests are always audited.")
    args = parser.parse_args()
    prefix = "p2" if args.phase == "p2" else "current"
    requests = json.loads((ROOT / "docs/ui_missing_assets.json").read_text(encoding="utf-8"))
    manifest = json.loads((ART / "manifest.json").read_text(encoding="utf-8"))
    records = []
    for request in requests["requests"]:
        delivered = []
        for expected in request["deliverables"]:
            inspected = inspect_image(ART / expected["filename"], manifest)
            inspected["expected_size_px"] = expected["size_px"]
            inspected["matches_expected_size"] = inspected.get("size_px") == expected["size_px"]
            inspected["has_real_transparent_background"] = inspected.get("alpha_zero_percent", 0) > 0 if expected.get("transparent") else None
            delivered.append(inspected)
        record = {"id": request["id"], "name": request["name"], "priority": request["priority"], "review_status": request["status"], "deliverables": delivered}
        record["all_delivered"] = all(value["exists"] for value in delivered)
        record["all_registered"] = record["all_delivered"] and all(value.get("registered") for value in delivered)
        if request["id"] in OLD_MONSTERS:
            record["existing_original"] = inspect_image(ART / OLD_MONSTERS[request["id"]], manifest)
        records.append(record)

    all_images = sorted(path for path in ART.rglob("*") if path.suffix.lower() in {".png", ".jpg", ".jpeg"})
    catalog = json.loads((ROOT / "client/data/catalog.json").read_text(encoding="utf-8"))["tables"]["Cards"]
    missing_cards = [card["id"] for card in catalog if card["id"] not in manifest.get("cards", {}) or not (ART / manifest["cards"][card["id"]]).is_file()]
    invalid_resources = [key for key, value in manifest.get("files", {}).items() if not (ROOT / "client" / value["path"].removeprefix("res://")).is_file()]
    unregistered = [path.relative_to(ART).as_posix() for path in all_images if path.relative_to(ART).as_posix() not in manifest.get("files", {})]
    report = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "asset_root": ART.relative_to(ROOT).as_posix(),
        "read_only_source_audit": True,
        "legacy_source_paths_present": {path: (ROOT / path).exists() for path in ["UI", "Cards/Art", "ui_mockups_v058"]},
        "counts": {
            "bitmap_files": len(all_images),
            "ui_bitmaps": sum(path.is_relative_to(ART / "UI") for path in all_images),
            "card_illustrations": sum(path.is_relative_to(ART / "Cards/Art") for path in all_images),
            "registered_files": len(manifest.get("files", {})),
            "card_bindings": len(manifest.get("cards", {})),
            "monster_species_bound": len(manifest.get("monsters", {})),
            "requests_by_status": dict(Counter(value["review_status"] for value in records)),
            "fully_delivered_requests": sum(value["all_delivered"] for value in records),
            "delivered_request_pngs": sum(value["exists"] for record in records for value in record["deliverables"]),
        },
        "unregistered_bitmaps": unregistered,
        "invalid_manifest_resources": invalid_resources,
        "missing_catalog_card_bindings": missing_cards,
        "missing_request_files": [value["key"] for record in records for value in record["deliverables"] if not value["exists"]],
        "dimension_mismatches": [value["key"] for record in records for value in record["deliverables"] if value["exists"] and not value["matches_expected_size"]],
        "missing_alpha_background": [value["key"] for record in records for value in record["deliverables"] if value["exists"] and value["has_real_transparent_background"] is False],
        "requests": records,
        "evidence": [f"outputs/{prefix}_asset_contact.jpg", f"outputs/{prefix}_asset_dark_contact.jpg"],
        "limitations": ["Pixel statistics establish presence, dimensions, transparency and registration; style, silhouette and unintended background need manual review.", "This script does not certify Godot interaction or server protocol behavior."],
    }
    OUTPUT.mkdir(exist_ok=True)
    if args.phase == "p2":
        contact_paths = [ART / value["filename"] for request in requests["requests"] if request["priority"] != "P1" for value in request["deliverables"] if (ART / value["filename"]).is_file()]
    else:
        contact_paths = sorted((ART / "UI/Monsters").glob("*.png"))
        contact_paths.extend(path for path in [ART / "UI/Cards/card_frame_monster_clean.png", ART / "UI/Battle/element_earth_clean.png"] if path.is_file())
    contact_sheet(contact_paths, OUTPUT / f"{prefix}_asset_contact.jpg")
    contact_sheet(contact_paths, OUTPUT / f"{prefix}_asset_dark_contact.jpg", dark=True)
    report["native_preview"] = native_monster_contact(prefix)
    if args.phase == "p2":
        report["native_ui_preview"] = native_p2_contact()
    (OUTPUT / f"{prefix}_asset_audit.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"counts": report["counts"], "unregistered_bitmaps": unregistered, "invalid_manifest_resources": invalid_resources, "missing_catalog_card_bindings": missing_cards}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
