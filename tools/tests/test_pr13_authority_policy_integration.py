"""Coordinator policy integration; all fixtures are offline and bounded."""
import copy
import sys
import unittest
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from tools import gameplay_load_test as coordinator
from tools.pr13_authority_transitions import AUTHORITY_TRANSITION_POLICY, STRICT_POLICY, CAPACITY_RECOVERY_POLICY_V2
from tools.tests.test_pr13_authority_transitions import fixture


class NativeBusinessReviewTests(unittest.TestCase):
    def test_strict_policy_does_not_read_or_excuse_audit(self):
        e,n=fixture()
        def unavailable():
            raise AssertionError('strict path must remain unchanged')
            yield None
        failed,review=coordinator.review_native_business_errors(unavailable(),n,copy.deepcopy(n),
            policy=STRICT_POLICY,clock_qualified=True)
        self.assertTrue(failed);self.assertIsNone(review)

    def test_explicit_policy_reviews_without_mutating_primary_or_status(self):
        e,n=fixture();status=copy.deepcopy(n);status[0].pop('user_id');original=copy.deepcopy(n);original_status=copy.deepcopy(status)
        failed,r=coordinator.review_native_business_errors(e,n,status,policy=AUTHORITY_TRANSITION_POLICY,clock_qualified=True)
        self.assertFalse(failed,r);self.assertTrue(r['original_errors_unchanged'])
        self.assertEqual(original,n);self.assertEqual(original_status,status)

    def test_healthy_status_cannot_hide_primary_error(self):
        e,n=fixture();status=copy.deepcopy(n);status[0]['errors']=[]
        failed,r=coordinator.review_native_business_errors(e,n,status,policy=AUTHORITY_TRANSITION_POLICY,clock_qualified=True)
        self.assertTrue(failed);self.assertIn({'reason':'primary_status_error_disagreement'},r['evidence_errors'])

    def test_missing_status_or_different_actor_cannot_qualify(self):
        e,n=fixture()
        for status in ([],[dict(n[0],client_id='other')]):
            with self.subTest(status=status):
                failed,r=coordinator.review_native_business_errors(e,n,status,policy=AUTHORITY_TRANSITION_POLICY,clock_qualified=True)
                self.assertTrue(failed)

    def test_policy_is_workload_metadata_not_a_coverage_override(self):
        self.assertIn('authority_transition_policy',coordinator.COVERAGE_METADATA)

    def test_registered_v2_preserves_primary_and_status_errors_and_inference_label(self):
        from tools.tests.test_pr13_capacity_recovery_v2 import short_control
        e,n=short_control();status=copy.deepcopy(n);status[0].pop('user_id')
        original=copy.deepcopy(n);original_status=copy.deepcopy(status)
        failed,r=coordinator.review_native_business_errors(e,n,status,
            policy=CAPACITY_RECOVERY_POLICY_V2,clock_qualified=True)
        self.assertFalse(failed,r);self.assertTrue(r['capacity_budget_only'])
        self.assertEqual(1,len(r['inferred_short_stun_requests']))
        self.assertEqual(original,n);self.assertEqual(original_status,status)
        self.assertFalse(r['capacity_acceptance'])

    def test_v2_cannot_hide_a_different_status_error_array(self):
        from tools.tests.test_pr13_capacity_recovery_v2 import short_control
        e,n=short_control();status=copy.deepcopy(n);status[0]['errors']=[]
        failed,r=coordinator.review_native_business_errors(e,n,status,
            policy=CAPACITY_RECOVERY_POLICY_V2,clock_qualified=True)
        self.assertTrue(failed)
        self.assertIn({'reason':'primary_status_error_disagreement'},r['evidence_errors'])


if __name__=='__main__':unittest.main()
