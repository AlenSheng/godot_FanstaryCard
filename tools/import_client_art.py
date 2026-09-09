"""Import supplied art without changing the source files or Unity metadata."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT / "client/assets/imported"
GROUPS = {
    "C": "fire_slash fire_spark fire_burn wood_spike wood_leaf tide_strike metal_blade metal_glint stone_fist earth_gravel strike heavy_hammer stone_split pierce bandage breath_regain ward hasten stun_flash seal fire_star sprout retreating_wave shield_load golden_wind stun_hammer vein_seal spring_surge swift_spell metal_rift",
    "PRI-": "holy_heal baptism water_smite judgment_beam twin_care punishment_bell gospel_light holy_domain silent_veil apocalypse_eye",
    "MAG-": "fireball flame_spear scorch_mark frost_arrow rock_bullet arcane_orb ember_wind frost_prison inferno_pit skyfire",
    "GUA-": "iron_wall block_shield bedrock shield_bash shield_charge stomp_guard blood_spring bastion_wall blood_rage immortal_guard",
    "GW": "blazing_cut scarlet_mark roast_blast vine_whip jade_edge leaf_blade hill_slam sandfall cracked_earth golden_cut silver_arc edge_chime water_dart frost_point precise_shot elbow_strike falling_blow piercing_thrust minor_heal herb_dressing wet_compress earth_cover recovery_breath quick_step flame_haste flash_dazzle golden_resonance lip_seal",
    "GG": "blazing_expansion molten_blade fire_tongue scorching_wind thorn_shot jade_slash vine_bind sprout_spike earth_rift sand_blade hill_press sinking_fist golden_arc blade_rain steel_spike wind_cleave wave_cut frost_cone tide_blade cold_shot ramming_strike heart_pierce sky_pierce sun_pierce bone_break charging_punch wound_cleanse wooden_heal spring_moisture mud_armor golden_guard breath_recovery branch_draw ember_breath swift_wind flame_haste golden_law dazzling_light earth_shake wood_sway breath_seal water_seal",
    "GB": "burning_flow flame_pillar fire_sea molten_burst forest_slaughter vine_dragon jade_fall thornfall earth_rift stone_prison sand_collapse gold_flash_slash steel_cleave blade_prison icefall raging_tide frost_abyss frost_burst crushing_punch piercing_beam sky_rift falling_impact straight_cleave grand_heal sweet_rain jade_canopy stone_armor spirit_tide drawing_branch haste_spell flame_law binding_still stone_still source_seal gold_seal",
    "GP": "flameburst city_burn molten_heart overgrowth thorn_crown mountain_collapse mountain_seal deep_abyss steel_shave rainbow_cleave golden_prison flood_peak ice_spire deep_frost annihilation_strike star_shatter world_piercer sacred_surge bulwark spirit_sea twin_contract swift_motion fated_bind flow_seal chaos_rhythm",
    "GO": "tide_bloom blazing_wind golden_split vein_seal life_breath mountain_guard rainbow_cut five_elements reverse_tide class_reveal",
}
QUALITY = dict(White="common", Green="uncommon", Blue="rare", Purple="epic", Orange="legendary")


MONSTERS = {
    "fire-bat": ("M-FIREBAT", "fire_bat"),
    "thorn-mite": ("M-THORNMITE", "thorn_mite"),
    "murk-snail": ("M-MUDHYDRA", "murk_polyp"),
    "sand-lizard": ("M-SANDLIZARD", "sand_lizard"),
    "rust-rat": ("M-RUSTRAT", "rustblade_rat"),
    "treasure-box-spirit": ("M-BOXSPIRIT", "treasure_box_spirit"),
    "metal-guard": ("M-GOLDGUARD", "metal_guard"),
    "fire-herald": ("M-FIREREAVER", "fire_herald"),
    "marsh-mother": ("M-SWAMPMOTHER", "marsh_mother"),
    "stone-guard": ("M-STONEGUARD", "stone_guardian"),
    "thorn-guard": ("M-THORNGUARD", "thorn_guard"),
    "annihilation-core": ("M-VOIDCORE", "annihilation_core_phase_1"),
}
MONSTER_VARIANTS = {
    "annihilation-core": {
        "phase_1": "UI/Monsters/annihilation_core_phase_1.png",
        "phase_2": "UI/Monsters/annihilation_core_phase_2.png",
    }
}
MONSTER_ALIASES = {
    "fire-bat-a": "fire-bat", "fire-bat-b": "fire-bat",
    "murk-snail-a": "murk-snail", "murk-snail-b": "murk-snail",
}
MONSTER_REPLACEMENTS = {
    "fire-bat": "UI/Monsters/fire_bat_clean.png",
    "rust-rat": "UI/Monsters/rustblade_rat_clean.png",
    "stone-guard": "UI/Monsters/stone_guardian_clean.png",
}
PORTRAIT_REPLACEMENTS = {
    "Priest": "UI/Characters/priest_consistent.png",
    "Guardian": "UI/Characters/guardian_consistent.png",
}
PASSIVES = {hero: f"UI/Encounter/passive_{hero.lower()}_clean.png" for hero in ("Mage", "Priest", "Guardian")}
PRODUCTS = {
    "Cards": "UI/Shop/card_pack.png",
    "EquipmentFragments": "UI/Shop/equipment_fragment_pack.png",
    "AdvancedBag": "UI/Shop/backpack_advanced.png",
    "TopBag": "UI/Shop/backpack_top.png",
}
ACTION_ICONS = {
    "Relic": "UI/Action/relic_pile_clean.png",
    "Spring": "UI/Action/spring_clean.png",
    "Extract": "UI/Action/extract_gate_clean.png",
}
OPTIONAL_ASSETS = set(MONSTER_REPLACEMENTS.values()) | set(PORTRAIT_REPLACEMENTS.values())
OPTIONAL_ASSETS.update(PASSIVES.values())
OPTIONAL_ASSETS.update(PRODUCTS.values())
OPTIONAL_ASSETS.update(ACTION_ICONS.values())
OPTIONAL_ASSETS.add("UI/Monsters/frost_wraith_clean.png")
REFERENCE_ONLY = [
    "UI/Battle/battle_background.png", "UI/Prep/background.jpg",
    "UI/Hall/background.jpg", "UI/Enhance/background.png",
]
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}


def image_files(directory):
    return sorted(p for p in directory.rglob("*") if p.is_file() and p.suffix.lower() in IMAGE_EXTENSIONS)


def read_manifest(path):
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(data, dict) or not isinstance(data.get("files", {}), dict):
        raise ValueError(f"Invalid existing manifest; refusing to replace it: {path}")
    return data


def same_file(source, target):
    return source.resolve() == target.resolve() or (target.exists() and source.samefile(target))


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def collect_sources(root, destination, source_root=None, ui_root=None, cards_root=None):
    common = Path(source_root).resolve() if source_root else root
    if source_root and not any((common / part).is_dir() for part in ("UI", "Cards/Art")):
        raise ValueError(f"Source root has neither UI nor Cards/Art: {common}")
    sources = {p.relative_to(destination).as_posix(): p for p in image_files(destination)}
    borders = {}
    warnings = []
    for prefix, override in (("UI", ui_root), ("Cards/Art", cards_root)):
        directory = Path(override).resolve() if override else common / prefix
        if override and not directory.is_dir():
            raise ValueError(f"Source directory does not exist: {directory}")
        if not directory.is_dir():
            directory = destination / prefix
        for source in image_files(directory):
            sources[f"{prefix}/{source.relative_to(directory).as_posix()}"] = source
        for manifest in directory.rglob("sprite_manifest.json"):
            try:
                data = json.loads(manifest.read_text(encoding="utf-8-sig"))
                for sprite in data.get("sprites", []):
                    key = (manifest.parent / sprite["file"]).relative_to(directory).as_posix()
                    border = sprite.get("border", [0, 0, 0, 0])
                    if len(border) != 4 or not all(isinstance(n, (int, float)) and n >= 0 for n in border):
                        raise ValueError(f"Invalid border for {key}")
                    borders[f"{prefix}/{key}"] = border
            except (json.JSONDecodeError, KeyError, TypeError, ValueError) as error:
                warnings.append(f"{manifest}: {error}; retained or default borders used")
    return sources, borders, warnings


def monster_mapping(available=None):
    mapping = {key: f"UI/Monsters/{filename}.png" for key, (_, filename) in MONSTERS.items()}
    if available is not None:
        mapping.update({key: path for key, path in MONSTER_REPLACEMENTS.items() if path in available})
    return mapping


def card_mapping(catalog, available=None):
    cards = {c["id"]: c for c in catalog["tables"]["Cards"]}
    mapping = {}
    for prefix, keys in GROUPS.items():
        for index, key in enumerate(keys.split(), 1):
            card_id = f"{prefix}{index:02d}"
            card = cards[card_id]
            mapping[card_id] = f"Cards/Art/{key}_{QUALITY[card['quality']]}.png"
    if set(mapping) != {c["id"] for c in cards.values() if c["is_codex"]}:
        raise ValueError("Codex mapping does not match the published catalog")
    if len(set(mapping.values())) != len(mapping):
        raise ValueError("Duplicate codex illustration assignment")
    for monster_id, path in monster_mapping(available).items():
        mapping[MONSTERS[monster_id][0]] = path
    if set(mapping) != set(cards):
        raise ValueError("Card mapping does not cover the complete published catalog")
    return mapping


def import_art(root=ROOT, *, source_root=None, ui_root=None, cards_root=None, destination=None):
    root = Path(root).resolve()
    destination = Path(destination).resolve() if destination else root / "client/assets/imported"
    manifest_path = destination / "manifest.json"
    previous = read_manifest(manifest_path)
    sources, borders, warnings = collect_sources(root, destination, source_root, ui_root, cards_root)
    mapping = card_mapping(json.loads((root / "client/data/catalog.json").read_text(encoding="utf-8")), sources)
    required = set(mapping.values()) | (set(previous.get("files", {})) - OPTIONAL_ASSETS)
    required.update(path for variants in MONSTER_VARIANTS.values() for path in variants.values())
    missing = sorted(required - sources.keys())
    if missing:
        raise ValueError("Incomplete art set; existing manifest left unchanged. Missing: " + ", ".join(missing))

    # Validate the complete batch before copying anything or replacing the manifest.
    sizes = {}
    for relative, source in sources.items():
        with Image.open(source) as original:
            sizes[relative] = list(original.size)
            original.verify()
        if relative.startswith("Cards/Art/"):
            width, height = sizes[relative]
            if width * 3 != height * 2:
                raise ValueError(f"Card art must be 2:3: {source}")
            if same_file(source, destination / relative) and (width, height) != (512, 768):
                raise ValueError(f"In-place card must already be 512x768; use --cards-root to normalize a separate source: {source}")

    # Optional deliveries may be temporarily absent; retain their provenance without
    # exposing unavailable paths to runtime consumers, and recover it if reintroduced.
    previous_files = dict(previous.get("unavailable_optional_assets", {}))
    previous_files.update(previous.get("files", {}))
    unavailable_optional = {path: entry for path, entry in previous_files.items()
                            if path in OPTIONAL_ASSETS and path not in sources}
    files = {}
    for relative, source in sorted(sources.items()):
        target = destination / relative
        entry = dict(previous_files.get(relative, {}))
        in_place = same_file(source, target)
        source_hash = sha256(source)
        if not in_place:
            target.parent.mkdir(parents=True, exist_ok=True)
            if relative.startswith("Cards/Art/"):
                with Image.open(source) as original:
                    original.convert("RGBA").resize((512, 768), Image.Resampling.LANCZOS).save(target)
            else:
                shutil.copyfile(source, target)
            if entry.get("source_sha256") and entry["source_sha256"] != source_hash:
                history = list(entry.get("source_history", []))
                history.append({k: entry[k] for k in ("source_sha256", "source_size", "source_path") if k in entry})
                entry["source_history"] = history
            entry.update(source_sha256=source_hash, source_size=sizes[relative], source_path=source.as_posix())
        else:
            # Legacy source hashes describe full-resolution originals, not resized imports.
            if "source_sha256" not in entry:
                entry["source_path"] = source.as_posix()
            entry.setdefault("source_sha256", source_hash)
            entry.setdefault("source_size", sizes[relative])
        entry.update(path="res://assets/imported/" + relative,
                     border_lbrt=borders.get(relative, entry.get("border_lbrt", [12, 12, 12, 12])),
                     imported_sha256=sha256(target),
                     imported_size=[512, 768] if relative.startswith("Cards/Art/") else sizes[relative])
        files[relative] = entry

    assigned_monster_images = {f"UI/Monsters/{filename}.png" for _, filename in MONSTERS.values()}
    assigned_monster_images.update(MONSTER_REPLACEMENTS.values())
    assigned_monster_images.update(path for variants in MONSTER_VARIANTS.values() for path in variants.values())
    unassigned_monsters = sorted(path for path in files if path.startswith("UI/Monsters/") and path not in assigned_monster_images)
    output = dict(previous)
    portraits = {hero: f"UI/Prep/exploration_prep_hero_portrait_{hero.lower()}.png"
                 for hero in ("Mage", "Priest", "Guardian")}
    portraits.update({hero: path for hero, path in PORTRAIT_REPLACEMENTS.items() if path in files})
    output.update(version=3,
                  source=previous.get("source", "User supplied Cards and UI assets; original files retained"),
                  license=previous.get("license", "User supplied; redistribution rights not declared in source manifests"),
                  import_policy="Existing in-place images are indexed without modification; source hashes retain historical original provenance; imported hashes describe current runtime bytes.",
                  warnings=list(dict.fromkeys(previous.get("warnings", []) + warnings)), cards=mapping,
                  monsters=monster_mapping(files),
                  monster_aliases=MONSTER_ALIASES, monster_variants=MONSTER_VARIANTS,
                  monster_variant_policy="Explicit phase variants only; select a variant only from authoritative phase data.",
                  catalog_only_monsters=["treasure-box-spirit"],
                  unassigned_monsters=unassigned_monsters,
                  portraits={hero: path for hero, path in portraits.items() if path in files},
                  passives={hero: path for hero, path in PASSIVES.items() if path in files},
                  products={product: path for product, path in PRODUCTS.items() if path in files},
                  action_icons={action: path for action, path in ACTION_ICONS.items() if path in files},
                  unavailable_optional_assets=unavailable_optional,
                  files=files, reference_only=list(dict.fromkeys(previous.get("reference_only", []) + REFERENCE_ONLY)))
    destination.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=destination, suffix=".tmp", delete=False) as temporary:
        temporary.write(json.dumps(output, ensure_ascii=False, indent=2) + "\n")
        temporary_path = Path(temporary.name)
    try:
        os.replace(temporary_path, manifest_path)
    finally:
        temporary_path.unlink(missing_ok=True)
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, help="Optional source directory containing UI and/or Cards/Art")
    parser.add_argument("--ui-root", type=Path, help="Optional directory containing UI module subdirectories")
    parser.add_argument("--cards-root", type=Path, help="Optional directory containing original card illustrations")
    args = parser.parse_args()
    try:
        output = import_art(source_root=args.source_root, ui_root=args.ui_root, cards_root=args.cards_root)
    except (OSError, ValueError, KeyError) as error:
        parser.exit(1, f"Import aborted: {error}\n")
    print(f"Indexed {len(output['files'])} images; mapped {len(output['cards'])} cards (200 codex + 12 monsters), 12 species and 2 explicit boss phase variants")


if __name__ == "__main__":
    main()
