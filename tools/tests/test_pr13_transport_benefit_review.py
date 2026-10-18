"""Policy contracts;all counts include failures/pending and never activate runtime."""
import unittest
from tools.pr13_candidate_review import transport_review,transport_three_round_review
class TransportReviewTests(unittest.TestCase):
 def base(self):return {'launched':20,'success':16,'failure':4,'pending_final':0,'unexpected_failures':0,'source_config_hash':'same-source','request_mix_hash':'same-mix','response_byte_profile_hash':'same-bytes','schedule_profile':'same-closed-loop','all_terminal_mean_ms':80}
 def test_faster_success_with_more_failures_rejected(self):
  base=self.base();bad=dict(base,success=15,failure=5,unexpected_failures=1,all_terminal_mean_ms=10);r=transport_review(base,bad);self.assertEqual(r['state'],'Failed');self.assertFalse(r['performance_acceptance']);self.assertFalse(r['production_activation'])
 def test_response_bytes_mismatch_diagnostic(self):
  base=self.base();self.assertEqual(transport_review(base,dict(base,response_byte_profile_hash='different'))['state'],'DiagnosticOnly')
 def test_request_mix_mismatch_diagnostic(self):
  base=self.base();self.assertEqual(transport_review(base,dict(base,request_mix_hash='different'))['state'],'DiagnosticOnly')
 def test_pending_not_dropped(self):
  base=self.base();pending=dict(base,success=15,pending_final=1,all_terminal_mean_ms=None);self.assertEqual(transport_review(base,pending)['state'],'Inconclusive')
 def test_outcome_accounting_invalid(self):
  base=self.base()
  with self.assertRaises(ValueError):transport_review(base,dict(base,success=15))
 def test_small_budget_not_qualified(self):
  base=dict(self.base(),launched=19,success=15);self.assertEqual(transport_review(base,base)['state'],'Unknown')
 def test_exact_three_round_uncertainty_recomputable(self):
  base=self.base();fast=dict(base,all_terminal_mean_ms=50);a=transport_three_round_review([(base,fast)]*3);self.assertEqual(a,transport_three_round_review([(base,fast)]*3));self.assertEqual(a['state'],'Inconclusive');self.assertEqual(a['exact_round_bootstrap_resamples'],27);self.assertEqual(a['exact_signflip_states'],8);self.assertEqual(a['two_sided_signflip_p'],.25);self.assertFalse(a['production_activation']);self.assertFalse(a['capacity_acceptance'])
 def test_missing_round_rejected(self):
  base=self.base()
  with self.assertRaises(ValueError):transport_three_round_review([(base,base)]*2)
if __name__=='__main__':unittest.main()
