import unittest
from tools.pr13_review_policy import execution_state
from tools.pr13_acceptance_register import review_scope
from pathlib import Path
import json
import tempfile


class HumanProvenanceBoundaryTests(unittest.TestCase):
    def test_claimed_human_roster_without_existing_exact_source_files_cannot_pass(self):
        machine=[dict(executed=True,status='Passed',profiles_executed=['OFFLINE','RENDER'])]*3
        evidence=dict(authority='MAIN',verified_source_files=[dict(path='missing-human-proof.json',bytes=1,sha256='0'*64)],
                      participants=[dict(participant_id=str(i),participant_kind='human',hero_class=['Mage','Priest','Guardian'][i%3],skill_band='experienced',natural_cycle_ids=['1','2','3']) for i in range(6)])
        self.assertEqual('Partial',execution_state(machine,['OFFLINE','RENDER'],human_required=True,human_evidence=evidence))

    def test_human_exclusion_retains_automatic_profiles_and_failures(self):
        machine=[dict(executed=True,status='Passed',profiles_executed=['OFFLINE','RENDER'])]*3
        self.assertEqual('ReadyForAcceptance',execution_state(machine,['OFFLINE','RENDER'],human_required=True,human_in_scope=False))
        self.assertEqual('Partial',execution_state(machine,['OFFLINE','RENDER','EXPERIMENT'],human_required=True,human_in_scope=False))
        self.assertEqual('Failed',execution_state([dict(executed=True,status='Failed',profiles_executed=['OFFLINE'])],['OFFLINE'],human_required=True,human_in_scope=False))

    def test_scope_requires_explicit_human_decision_and_retained_automation(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);source=root/'scope.json'
            value={'authority':'human','human_experience':{'in_scope':False,'automated_combat_render_and_metrics_remain_required':True,'do_not_claim_human_tests_passed':True}}
            source.write_text(json.dumps(value))
            self.assertFalse(review_scope(source,root)['in_scope'])
            value['human_experience']['automated_combat_render_and_metrics_remain_required']=False
            source.write_text(json.dumps(value))
            with self.assertRaises(ValueError):review_scope(source,root)


if __name__=='__main__':unittest.main()
