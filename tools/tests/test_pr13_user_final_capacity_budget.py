"""Exact new human-directed final-round budget;never rewrites prior counts."""
import tempfile
import unittest
from tools.pr13_distributed_capacity import USER_FINAL_ACCEPTANCE_POLICY
from tools.tests.test_pr13_distributed_capacity import SyntheticStudy


class UserFinalCapacityBudgetTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='pr13-user-final-budget-')
        self.addCleanup(self.temp.cleanup)
        self.study=SyntheticStudy(self.temp.name,aggregate=True)
        self.study.spec.update(prior_capacity_worlds=284,combined_capacity_world_cap=324,
            world_budget=40,user_final_acceptance_policy=USER_FINAL_ACCEPTANCE_POLICY)
        self.study.bind_spec()

    def test_exact_registered_final_round_keeps_technical_gates(self):
        r=self.study.assess();self.assertTrue(r['capacity_accepted'],r)
        self.assertFalse(r['user_over300_condition_reached'])
        self.assertEqual(299,r['cumulative_actual_worlds'])

    def test_actual_count_not_cap_controls_over300_condition(self):
        self.study.after['matches']=17
        r=self.study.assess();self.assertTrue(r['capacity_accepted'],r)
        self.assertTrue(r['user_over300_condition_reached'])
        self.assertEqual(301,r['cumulative_actual_worlds'])

    def test_300_exactly_is_not_over300(self):
        self.study.after['matches']=16
        r=self.study.assess();self.assertTrue(r['capacity_accepted'],r)
        self.assertFalse(r['user_over300_condition_reached'])

    def test_missing_marker_cannot_increase_old_budget(self):
        del self.study.spec['user_final_acceptance_policy'];self.study.bind_spec()
        self.assertFalse(self.study.assess()['capacity_accepted'])

    def test_new_marker_cannot_be_attached_to_a_different_old_budget(self):
        self.study.spec.update(prior_capacity_worlds=253,combined_capacity_world_cap=300,world_budget=47)
        self.study.bind_spec();self.assertFalse(self.study.assess()['capacity_accepted'])

    def test_unknown_marker_changed_prior_or_larger_cap_fails(self):
        for key,value in [('user_final_acceptance_policy','anything'),('prior_capacity_worlds',0),
                          ('combined_capacity_world_cap',325),('world_budget',41)]:
            before=self.study.spec[key];self.study.spec[key]=value;self.study.bind_spec()
            with self.subTest(key=key):self.assertFalse(self.study.assess()['capacity_accepted'])
            self.study.spec[key]=before;self.study.bind_spec()

    def test_user_waiver_does_not_turn49_into_technical100_or50(self):
        for host,count in [('windows',30),('cloud',19)]:
            r=self.study.report(host)
            for row in r['samples']:
                if row['active_in_room']:row.update(online=count,active_in_room=count)
            self.study.put_report(host,r)
        self.study.after['matches']=17
        self.assertFalse(self.study.assess()['capacity_accepted'])


if __name__=='__main__':unittest.main()
