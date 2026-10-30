import unittest
from tools.localization_audit import coverage, TOKENS
from tools.audit_ui_text import human_literal


class CoverageTests(unittest.TestCase):
    def test_overlapping_languages_use_countrywise_maximum(self):
        dataset = {"supplemental": {"territoryInfo": {
            "AA": {"_population": "100", "languagePopulation": {
                "en": {"_populationPercent": "80"}, "es": {"_populationPercent": "70"}}},
            "BB": {"_population": "300", "languagePopulation": {
                "en": {"_populationPercent": "10"}, "es": {"_populationPercent": "90"}}}
        }}}
        result = coverage(["en", "es"], dataset)
        self.assertEqual(350, result["covered_population_lower_bound"])
        self.assertEqual(87.5, result["coverage_lower_bound_percent"])

    def test_simplified_chinese_does_not_count_other_scripts(self):
        dataset = {"supplemental": {"territoryInfo": {
            "AA": {"_population": "100", "languagePopulation": {
                "zh": {"_populationPercent": "30"}, "zh_Hant": {"_populationPercent": "90"}}}
        }}}
        self.assertEqual(30, coverage(["zh-CN"], dataset)["covered_population_lower_bound"])

    def test_percent_prose_is_not_a_printf_specifier(self):
        self.assertEqual([], TOKENS.findall("10% fee (minimum 1 Gold)"))
        self.assertEqual(["%s", "%%", "%.2f", "{count}"], TOKENS.findall("%s%% / %.2f / {count}"))

    def test_ui_literal_detection_catches_both_languages_and_direct_labels(self):
        self.assertTrue(human_literal("保存编组"))
        self.assertTrue(human_literal("Save Deck"))
        self.assertTrue(human_literal("Save", "label.text = "))
        self.assertTrue(human_literal("Save", "ui.button("))
        self.assertFalse(human_literal("res://assets/class_portrait.png"))
        self.assertFalse(human_literal("room.command_cancelled"))
        self.assertFalse(human_literal("%s %s%%", "label.text = "))


if __name__ == "__main__":
    unittest.main()
