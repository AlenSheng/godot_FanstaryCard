import tempfile
import unittest
from pathlib import Path

from run_validation import ValidationError, validate_simulation, validate_trx


class EvidenceTests(unittest.TestCase):
    def trx(self, counters):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "result.trx"
            path.write_text('<TestRun xmlns="urn:test"><ResultSummary><Counters ' + counters + '/></ResultSummary></TestRun>', encoding="utf-8")
            return validate_trx(path)

    def test_real_counters(self):
        self.assertEqual(3, self.trx('total="4" executed="3" passed="3" notExecuted="1"')["passed"])

    def test_zero_tests_rejected(self):
        with self.assertRaises(ValidationError):
            self.trx('total="0" executed="0" passed="0"')

    def test_failed_test_rejected(self):
        with self.assertRaises(ValidationError):
            self.trx('total="4" executed="4" passed="3" failed="1"')

    def test_inconsistent_counters_rejected(self):
        with self.assertRaises(ValidationError):
            self.trx('total="4" executed="4" passed="3"')

    def test_missing_report_rejected(self):
        with self.assertRaises(ValidationError):
            validate_trx(Path("does-not-exist.trx"))

    def sample(self):
        result = dict(Samples=10000, PlayerCount=1, ConfigVersion="fixture", MinimumEliteClearsForThreeMiddleCorners=4)
        for key in ("ClearedCells", "MiddleEliteCells", "Gold", "WarriorSoul", "ClassSoul", "Fragments"):
            result[key] = dict(P10=1, P50=2, P90=3, Mean=2)
        return result

    def test_simulator_shape(self):
        validate_simulation(self.sample(), 10000, 1)

    def test_wrong_simulation_counts_rejected(self):
        with self.assertRaises(ValidationError):
            validate_simulation(self.sample(), 9999, 1)

    def test_nan_and_bad_quantiles_rejected(self):
        sample = self.sample()
        sample["Gold"]["Mean"] = float("nan")
        with self.assertRaises(ValidationError):
            validate_simulation(sample, 10000, 1)
        sample = self.sample()
        sample["Gold"]["P10"] = 9
        with self.assertRaises(ValidationError):
            validate_simulation(sample, 10000, 1)


if __name__ == "__main__":
    unittest.main()
