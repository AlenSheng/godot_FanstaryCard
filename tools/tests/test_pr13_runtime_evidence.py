import unittest
from tools.pr13_runtime_evidence import coverage, reconcile_cycles, result_dimensions, sampling_integrity


class CoverageTests(unittest.TestCase):
    def test_sampling_blackout_in_stop_tail_is_invalid(self):
        rows=[dict(at=100+t,sample_monotonic_ms=t*1000) for t in range(10,61,10)]
        self.assertTrue(sampling_integrity(rows,0,70000)['passed'])
        result=sampling_integrity(rows,0,600000)
        self.assertFalse(result['passed'])
        self.assertIn('sampling_gap_over_contract',result['reasons'])
        self.assertEqual(result['tail_gap_seconds'],540)

    def test_wall_clock_jump_is_recorded_without_filling_time(self):
        rows=[dict(at=110,sample_monotonic_ms=10000),dict(at=800,sample_monotonic_ms=20000)]
        self.assertIn('wall_clock_discontinuity',sampling_integrity(rows,0,30000)['reasons'])

    def rows(self, count=100):
        return [dict(at=t, online=100, active_in_room=count, command_rate=2) for t in range(0, 611, 10)]

    def measure(self, rows):
        return coverage(rows, start=0, end=600, target_online=100, target_active=100)

    def test_continuous_population_passes(self):
        self.assertTrue(self.measure(self.rows())["passed"])

    def test_peak_or_group_size_cannot_prove_100_active(self):
        rows = self.rows(50)
        rows[10]["active_in_room"] = 100
        self.assertFalse(self.measure(rows)["passed"])

    def test_missing_observations_cannot_bridge_a_gap(self):
        rows = [r for r in self.rows() if not 50 <= r["at"] <= 550]
        self.assertLess(self.measure(rows)["coverage"], .2)

    def test_zero_request_rate_and_unknown_rate_fail(self):
        for rate in (0, None, float("nan")):
            rows = self.rows()
            for row in rows: row["command_rate"] = rate
            self.assertFalse(self.measure(rows)["passed"])

    def test_unobserved_tail_is_not_filled(self):
        result = self.measure(self.rows()[:20])
        self.assertLess(result["coverage"], .95)

    def test_invalid_contract_rejected(self):
        with self.assertRaises(ValueError):
            coverage([], start=0, end=600, target_online=True, target_active=100)


class CutoffTests(unittest.TestCase):
    def test_malformed_sequences_are_evidence_failures_without_crashing(self):
        for sequence in (True,0,-1,'1',[],{}):
            row=self.event(sequence,99,'cycle.completed')
            result=reconcile_cycles([row],100,120)
            self.assertEqual(result['final']['completed_cycles'],0)
            self.assertIn('missing_context',result['evidence_errors'])

    def test_completion_requires_nonempty_business_match(self):
        row=self.event(1,99,'cycle.completed');row['match_id']=''
        result=reconcile_cycles([row],100,120)
        self.assertEqual(result['final']['completed_cycles'],0)
        self.assertIn('missing_business_context',result['evidence_errors'])

    def event(self, seq, at, kind, cycle="c:1"):
        return dict(run_id="run", client_id="c", process_epoch="epoch", event_seq=seq,
                    at_unix_ms=at, event_type=kind, cycle_id=cycle, match_id="m")

    def test_ack_drain_and_cycle_completion_stay_distinct(self):
        rows = [self.event(1, 99, "settlement.acknowledged"),
                self.event(2, 101, "cycle.completed")]
        r = reconcile_cycles(rows + [rows[0]], 100, 120)
        self.assertEqual(r["running"]["acknowledgements"], 1)
        self.assertEqual(r["running"]["completed_cycles"], 0)
        self.assertEqual(r["drain"]["completed_cycles"], 1)
        self.assertEqual(r["final"]["completed_cycles"], 1)
        self.assertEqual(r["evidence_errors"], [])

    def test_duplicate_business_completion_is_evidence_failure(self):
        rows = [self.event(1, 99, "cycle.completed"), self.event(2, 101, "cycle.completed")]
        self.assertIn("duplicate_business_completion", reconcile_cycles(rows, 100, 120)["evidence_errors"])

    def test_completion_requires_prior_acknowledgement_for_same_match(self):
        for ack in (None, self.event(1, 98, 'settlement.acknowledged', cycle='other'),
                    self.event(3, 101, 'settlement.acknowledged')):
            with self.subTest(ack=ack):
                rows = [self.event(2, 99, 'cycle.completed')]
                if ack is not None: rows.append(ack)
                errors = reconcile_cycles(rows, 100, 120)['evidence_errors']
                self.assertIn('completion_without_prior_matching_acknowledgement', errors)

    def test_fallback_is_not_normal_completion(self):
        r = reconcile_cycles([self.event(1, 99, "battle.abandon.fallback")], 100, 120)
        self.assertEqual(r["final"]["fallback_cycles"], 1)
        self.assertEqual(r["final"]["completed_cycles"], 0)

    def test_unknown_dimension_prevents_acceptance(self):
        r = result_dimensions(execution=True, evidence=True, load=True, gameplay=True,
                              performance=True, cleanup=None)
        self.assertFalse(r["all_applicable_passed"])
        self.assertEqual(r["dimensions"]["cleanup"], "Unknown")

    def test_preregistered_smoke_scope_does_not_claim_performance(self):
        r = result_dimensions(execution=True, evidence=True, load=True, gameplay=True,
                              performance=None, cleanup=True,
                              applicable=['execution', 'evidence', 'load', 'gameplay', 'cleanup'])
        self.assertTrue(r['all_applicable_passed'])
        self.assertFalse(r['full_acceptance_passed'])
        self.assertEqual(r['dimensions']['performance'], 'NotApplicable')
