import unittest
from tools.pr13_review_policy import execution_state


class HumanProvenanceBoundaryTests(unittest.TestCase):
    def test_claimed_human_roster_without_existing_exact_source_files_cannot_pass(self):
        machine=[dict(executed=True,status='Passed',profiles_executed=['OFFLINE','RENDER'])]*3
        evidence=dict(authority='MAIN',verified_source_files=[dict(path='missing-human-proof.json',bytes=1,sha256='0'*64)],
                      participants=[dict(participant_id=str(i),participant_kind='human',hero_class=['Mage','Priest','Guardian'][i%3],skill_band='experienced',natural_cycle_ids=['1','2','3']) for i in range(6)])
        self.assertEqual('Partial',execution_state(machine,['OFFLINE','RENDER'],human_required=True,human_evidence=evidence))


if __name__=='__main__':unittest.main()
