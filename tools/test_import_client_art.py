"""Check every server monster against the shipped client art."""
import json
import re
import unittest

from PIL import Image

import import_client_art as importer


class RuntimeMonsterArtTests(unittest.TestCase):
    def test_every_server_monster_has_loadable_art(self):
        root = importer.ROOT
        factory = (root / "server/src/FantasyCard.Domain/Combat/PveBattleFactory.cs").read_text(encoding="utf-8")
        monster_ids = set(re.findall(r'Monster\("([a-z-]+)"', factory))
        manifest = json.loads((root / "client/assets/imported/manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(set(importer.MONSTERS), set(manifest["monsters"]))
        self.assertEqual(importer.MONSTER_ALIASES, manifest["monster_aliases"])
        for monster_id in sorted(monster_ids):
            with self.subTest(monster_id=monster_id):
                species = manifest["monster_aliases"].get(monster_id, monster_id)
                self.assertIn(species, manifest["monsters"])
                key = manifest["monsters"][species]
                self.assertEqual(manifest["cards"][importer.MONSTERS[species][0]], key)
                self.assertEqual(manifest["files"][key]["path"], "res://assets/imported/" + key)
                with Image.open(root / "client/assets/imported" / key) as image:
                    image.verify()
        for variants in manifest["monster_variants"].values():
            for key in variants.values():
                with Image.open(root / "client/assets/imported" / key) as image:
                    image.verify()


if __name__ == "__main__":
    unittest.main()
