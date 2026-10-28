"""Coordinator UTC jumps must not create fake throughput or STOP attribution."""
import unittest
from tools.gameplay_load_validation import assess_cutoff_clock, request_cutoffs
from tools.pr13_runtime_evidence import reconcile_cycles


class CutoffClockTests(unittest.TestCase):
    def quality(self, jump=0, final_jump=None):
        if final_jump is None: final_jump = jump
        start = 1700000000000
        return assess_cutoff_clock(start, start+26000+jump, start+29000+final_jump,
            start_monotonic_ms=1000, stop_monotonic_ms=27000,
            final_monotonic_ms=30000)

    def request(self, seq, timestamp):
        return dict(type='http',event_type='http',run_id='r',client_id='a',
            process_epoch='e',cycle_id='a:1',event_seq=seq,at_unix_ms=timestamp,
            request_id='q'+str(seq),path='/api/v1/players/me',status=200,
            ok=True,result='success',duration_ms=5)

    def cycle_event(self, seq, timestamp, kind):
        return dict(event_type=kind,run_id='r',client_id='a',process_epoch='e',
            cycle_id='a:1',match_id='M',event_seq=seq,at_unix_ms=timestamp)

    def test_stable_capture_remains_qualified(self):
        result = self.quality()
        self.assertTrue(result['qualified'])
        self.assertEqual(result['wall_minus_monotonic_elapsed_ms'],
                         {'running':0,'final':0,'drain':0})
        self.assertFalse(result['clock_mapping_corrected'])

    def test_forward_jump_before_first_sample_is_not_a_long_run(self):
        result = self.quality(3600000)
        self.assertFalse(result['qualified'])
        self.assertIn('coordinator_wall_clock_discontinuity',result['evidence_errors'])
        self.assertEqual(result['wall_minus_monotonic_elapsed_ms']['running'],3600000)

    def test_jump_during_cleanup_and_reverse_order_are_unqualified(self):
        self.assertFalse(self.quality(0,3600000)['qualified'])
        self.assertFalse(self.quality(-3600000)['qualified'])
        result = assess_cutoff_clock(1000,2000,1999,start_monotonic_ms=0,
            stop_monotonic_ms=1000,final_monotonic_ms=1001)
        self.assertFalse(result['qualified'])
        self.assertIn('invalid_coordinator_unix_order',result['evidence_errors'])

    def test_missing_monotonic_bound_does_not_invent_a_mapping(self):
        result = assess_cutoff_clock(1000,2000,3000,start_monotonic_ms=0,
            stop_monotonic_ms=1000,final_monotonic_ms=None)
        self.assertFalse(result['qualified'])
        self.assertIn('missing_final_coordinator_monotonic_cutoff',result['evidence_errors'])

    def test_unqualified_request_windows_keep_counts_not_fake_rates(self):
        # UTC reversal could place the first owned event beyond the alleged final cutoff.
        events = [self.request(1,10000),self.request(2,20000)]
        result = request_cutoffs(events,500,1000,started_ms=0,
                                 cutoff_clock_qualified=False)
        self.assertIsNone(result['running'])
        self.assertIsNone(result['drain'])
        self.assertEqual(result['final']['logical_request_count'],2)
        self.assertEqual(result['final']['http']['count'],2)
        self.assertEqual(result['final']['http']['p95_ms'],5)
        self.assertIsNone(result['final']['observed_window_seconds'])
        self.assertIsNone(result['final']['logical_requests_per_second'])
        self.assertIsNone(result['final']['completed_requests_per_second'])
        self.assertEqual(result['final']['throughput_missing_reason'],
                         'coordinator_cutoff_clock_unqualified')
        self.assertIn('cutoff_clock_unqualified',result['evidence_errors'])

    def test_unqualified_cycle_windows_keep_final_ack_proof(self):
        events = [self.cycle_event(1,10000,'settlement.acknowledged'),
                  self.cycle_event(2,20000,'cycle.completed')]
        result = reconcile_cycles(events,500,1000,cutoff_clock_qualified=False)
        self.assertIsNone(result['running'])
        self.assertIsNone(result['drain'])
        self.assertEqual(result['final']['acknowledgements'],1)
        self.assertEqual(result['final']['completed_cycles'],1)
        self.assertIn('cutoff_clock_unqualified',result['evidence_errors'])

    def test_unqualified_clock_does_not_replace_matching_ack_requirement(self):
        result = reconcile_cycles([self.cycle_event(2,20000,'cycle.completed')],
            500,1000,cutoff_clock_qualified=False)
        self.assertIn('completion_without_prior_matching_acknowledgement',result['evidence_errors'])

    def test_healthy_cutoff_api_and_duplicate_rejection_still_work(self):
        a=self.request(1,100);b=self.request(2,600)
        result=request_cutoffs([a,b],500,1000,started_ms=0)
        self.assertEqual(result['running']['logical_request_count'],1)
        self.assertEqual(result['drain']['logical_request_count'],1)
        self.assertEqual(result['final']['logical_requests_per_second'],2)
        duplicate=request_cutoffs([a,a],500,1000,started_ms=0,
                                  cutoff_clock_qualified=False)
        self.assertEqual(duplicate['final']['logical_request_count'],1)
        self.assertIn('duplicate_request_event',duplicate['evidence_errors'])


if __name__ == '__main__': unittest.main()
