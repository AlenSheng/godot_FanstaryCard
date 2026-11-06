import importlib.util
from pathlib import Path
import tempfile
import unittest


class BranchStaticDocumentsTests(unittest.TestCase):
    def setUp(self):
        spec = importlib.util.spec_from_file_location("branch_catalog_export", Path(__file__).parents[1] / "export_client_catalog.py")
        self.module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.module)
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        (self.root / "config").mkdir()
        (self.root / "client/data").mkdir(parents=True)
        self.module.ROOT = self.root

    def test_branch_localization_and_season_documents_keep_exact_bytes(self):
        names = ("ui_text.json", "season_templates.json", "season_transition_rules.json")
        for name in names:
            (self.root / "config" / name).write_bytes(b'{"branch":"retained"}\r\n')
        self.module.copy_branch_documents()
        for name in names:
            self.assertEqual((self.root / "client/data" / name).read_bytes(), (self.root / "config" / name).read_bytes())

    def test_absent_optional_documents_do_not_replace_the_catalog(self):
        target = self.root / "client/data/catalog.json"
        target.write_bytes(b'{"current":"typed-protobuf-export"}')
        self.module.copy_branch_documents()
        self.assertEqual(target.read_bytes(), b'{"current":"typed-protobuf-export"}')
        self.assertEqual(list((self.root / "client/data").iterdir()), [target])

    def test_typed_zero_and_false_values_keep_the_release_mapping(self):
        self.assertEqual(self.module.typed_value(b"", 2), 0)
        self.assertIs(self.module.typed_value(b"", 4), False)
        self.assertEqual(self.module.typed_value(b"", 1), "")


if __name__ == "__main__":
    unittest.main()
