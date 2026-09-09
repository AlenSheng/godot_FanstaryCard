"""Regression coverage for importing into a user-populated asset directory."""
import json
from pathlib import Path
import shutil
import tempfile
import unittest

from PIL import Image

import import_client_art as importer


class ImportArtTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.destination = self.root / "client/assets/imported"
        self.manifest = self.destination / "manifest.json"
        self.catalog_path = self.root / "client/data/catalog.json"
        self.catalog_path.parent.mkdir(parents=True)
        shutil.copyfile(importer.ROOT / "client/data/catalog.json", self.catalog_path)
        self.catalog = json.loads(self.catalog_path.read_text(encoding="utf-8"))
        self.mapping = importer.card_mapping(self.catalog)
        paths = set(self.mapping.values())
        paths.update(path for variants in importer.MONSTER_VARIANTS.values() for path in variants.values())
        card_image = self.root / "sample-card.png"
        Image.new("RGBA", (512, 768), (20, 30, 40, 255)).save(card_image)
        for relative in paths:
            target = self.destination / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            if relative.startswith("Cards/"):
                shutil.copyfile(card_image, target)
            else:
                Image.new("RGBA", (16, 16), (50, 70, 90, 0)).save(target)
        self.legacy_key = self.mapping["C01"]
        self.previous = {
            "version": 1, "custom_metadata": "retain me", "files": {
                self.legacy_key: {"source_sha256": "historical-original-hash", "source_size": [1024, 1536],
                                  "border_lbrt": [1, 2, 3, 4], "license_note": "user supplied"}
            }
        }
        self.manifest.write_text(json.dumps(self.previous), encoding="utf-8")

    def test_in_place_preserves_images_provenance_and_complete_bindings(self):
        unknown = self.destination / "UI/Monsters/frost_wraith.png"
        Image.new("RGBA", (16, 16)).save(unknown)
        before = {p: importer.sha256(p) for p in importer.image_files(self.destination)}
        result = importer.import_art(self.root)
        self.assertEqual(before, {p: importer.sha256(p) for p in importer.image_files(self.destination)})
        entry = result["files"][self.legacy_key]
        self.assertEqual(entry["source_sha256"], "historical-original-hash")
        self.assertEqual(entry["source_size"], [1024, 1536])
        self.assertEqual(entry["imported_size"], [512, 768])
        self.assertEqual(entry["imported_sha256"], before[self.destination / self.legacy_key])
        self.assertEqual(entry["border_lbrt"], [1, 2, 3, 4])
        self.assertEqual(entry["license_note"], "user supplied")
        self.assertEqual(result["custom_metadata"], "retain me")
        self.assertEqual(len(result["cards"]), 212)
        self.assertEqual(len(result["monsters"]), 12)
        self.assertEqual(result["cards"]["M-MUDHYDRA"], result["monsters"]["murk-snail"])
        self.assertEqual(result["cards"]["M-VOIDCORE"], result["monster_variants"]["annihilation-core"]["phase_1"])
        self.assertEqual(result["monster_aliases"]["murk-snail-b"], "murk-snail")
        self.assertEqual(result["unassigned_monsters"], ["UI/Monsters/frost_wraith.png"])
        first_manifest = self.manifest.read_bytes()
        importer.import_art(self.root)
        self.assertEqual(self.manifest.read_bytes(), first_manifest)

    def test_incomplete_set_leaves_manifest_and_other_files_unchanged(self):
        (self.destination / self.mapping["M-BOXSPIRIT"]).unlink()
        old_manifest = self.manifest.read_bytes()
        with self.assertRaisesRegex(ValueError, "Incomplete art set"):
            importer.import_art(self.root)
        self.assertEqual(self.manifest.read_bytes(), old_manifest)

    def test_external_overrides_normalize_separate_source_and_keep_history(self):
        supplied = self.root / "new-delivery"
        card_source = supplied / self.legacy_key
        card_source.parent.mkdir(parents=True)
        Image.new("RGBA", (64, 96), (25, 50, 75, 255)).save(card_source)
        ui_source = supplied / "UI/Custom/new_icon.png"
        ui_source.parent.mkdir(parents=True)
        Image.new("RGBA", (20, 30), (15, 30, 45, 255)).save(ui_source)
        (ui_source.parent / "sprite_manifest.json").write_text(json.dumps({"sprites": [
            {"file": "new_icon.png", "border": [2, 3, 4, 5]}
        ]}), encoding="utf-8")
        original_bytes = card_source.read_bytes()
        result = importer.import_art(self.root, source_root=supplied)
        self.assertEqual(card_source.read_bytes(), original_bytes)
        with Image.open(self.destination / self.legacy_key) as image:
            self.assertEqual(image.size, (512, 768))
        entry = result["files"][self.legacy_key]
        self.assertEqual(entry["source_size"], [64, 96])
        self.assertEqual(entry["source_history"][0]["source_sha256"], "historical-original-hash")
        self.assertEqual(result["files"]["UI/Custom/new_icon.png"]["border_lbrt"], [2, 3, 4, 5])
        self.assertEqual(ui_source.read_bytes(), (self.destination / "UI/Custom/new_icon.png").read_bytes())

    def test_bad_override_and_unnormalized_in_place_card_do_not_write(self):
        before = self.manifest.read_bytes()
        with self.assertRaisesRegex(ValueError, "Source directory does not exist"):
            importer.import_art(self.root, cards_root=self.root / "typo")
        Image.new("RGBA", (64, 96)).save(self.destination / self.legacy_key)
        with self.assertRaisesRegex(ValueError, "In-place card must already be 512x768"):
            importer.import_art(self.root)
        self.assertEqual(self.manifest.read_bytes(), before)

    def test_p2_delivery_switches_bindings_without_changing_legacy_art(self):
        legacy_paths = {self.destination / path for path in importer.monster_mapping().values()}
        legacy_bytes = {path: path.read_bytes() for path in legacy_paths}
        for path in importer.OPTIONAL_ASSETS:
            target = self.destination / path
            target.parent.mkdir(parents=True, exist_ok=True)
            Image.new("RGBA", (24, 32), (40, 80, 120, 128)).save(target)
        clean_path = importer.MONSTER_REPLACEMENTS["fire-bat"]
        metadata = {"generator": "user tool", "prompt": "retain exact prompt", "seed": 42}
        self.previous["files"][clean_path] = {"generation_metadata": metadata}
        self.manifest.write_text(json.dumps(self.previous), encoding="utf-8")
        before = {path: importer.sha256(path) for path in importer.image_files(self.destination)}
        result = importer.import_art(self.root)
        for monster, path in importer.MONSTER_REPLACEMENTS.items():
            self.assertEqual(result["monsters"][monster], path)
            self.assertEqual(result["cards"][importer.MONSTERS[monster][0]], path)
        self.assertEqual(result["files"][clean_path]["generation_metadata"], metadata)
        self.assertEqual(result["portraits"], importer.PORTRAIT_REPLACEMENTS)
        self.assertEqual(result["passives"], importer.PASSIVES)
        self.assertEqual(result["products"], importer.PRODUCTS)
        self.assertEqual(result["action_icons"], importer.ACTION_ICONS)
        self.assertEqual(result["unassigned_monsters"], ["UI/Monsters/frost_wraith_clean.png"])
        self.assertEqual(before, {path: importer.sha256(path) for path in importer.image_files(self.destination)})
        self.assertEqual(legacy_bytes, {path: path.read_bytes() for path in legacy_paths})
        first_manifest = self.manifest.read_bytes()
        importer.import_art(self.root)
        self.assertEqual(self.manifest.read_bytes(), first_manifest)

    def test_optional_removal_falls_back_and_restoration_recovers_metadata(self):
        clean_key = importer.MONSTER_REPLACEMENTS["fire-bat"]
        clean_target = self.destination / clean_key
        Image.new("RGBA", (24, 32), (40, 80, 120, 128)).save(clean_target)
        portrait_key = "UI/Prep/exploration_prep_hero_portrait_priest.png"
        portrait_target = self.destination / portrait_key
        portrait_target.parent.mkdir(parents=True, exist_ok=True)
        Image.new("RGBA", (24, 32)).save(portrait_target)
        consistent_key = importer.PORTRAIT_REPLACEMENTS["Priest"]
        consistent_target = self.destination / consistent_key
        consistent_target.parent.mkdir(parents=True, exist_ok=True)
        Image.new("RGBA", (24, 32)).save(consistent_target)
        self.previous["files"][clean_key] = {"generation_metadata": {"seed": 99}}
        self.manifest.write_text(json.dumps(self.previous), encoding="utf-8")
        original_bytes = clean_target.read_bytes()
        first = importer.import_art(self.root)
        self.assertEqual(first["portraits"]["Priest"], consistent_key)
        clean_target.unlink()
        consistent_target.unlink()
        fallback = importer.import_art(self.root)
        self.assertEqual(fallback["monsters"]["fire-bat"], "UI/Monsters/fire_bat.png")
        self.assertEqual(fallback["cards"]["M-FIREBAT"], "UI/Monsters/fire_bat.png")
        self.assertEqual(fallback["portraits"]["Priest"], portrait_key)
        self.assertNotIn(clean_key, fallback["files"])
        self.assertEqual(fallback["unavailable_optional_assets"][clean_key], first["files"][clean_key])
        fallback_manifest = self.manifest.read_bytes()
        importer.import_art(self.root)
        self.assertEqual(self.manifest.read_bytes(), fallback_manifest)
        clean_target.write_bytes(original_bytes)
        restored = importer.import_art(self.root)
        self.assertEqual(restored["monsters"]["fire-bat"], clean_key)
        self.assertEqual(restored["files"][clean_key]["generation_metadata"], {"seed": 99})
        self.assertNotIn(clean_key, restored["unavailable_optional_assets"])

    def test_corrupt_optional_image_does_not_modify_manifest(self):
        target = self.destination / importer.MONSTER_REPLACEMENTS["fire-bat"]
        target.write_bytes(b"invalid PNG")
        before = self.manifest.read_bytes()
        with self.assertRaises(OSError):
            importer.import_art(self.root)
        self.assertEqual(self.manifest.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
