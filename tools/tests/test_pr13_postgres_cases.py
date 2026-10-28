import hashlib
import tempfile
from pathlib import Path
import unittest
from tools.pr13_postgres_cases import require_unskipped
from tools.pr13_acceptance_register import apply_main_decisions

class CanonicalIntegrationGuardTests(unittest.TestCase):
    def test_skipped_database_case_cannot_be_exported_as_passed(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'result.trx'
            path.write_text('<TestRun><Counters total="2" executed="1" passed="1" notExecuted="1" failed="0"/></TestRun>',encoding='utf8')
            with self.assertRaises(ValueError): require_unskipped({'exit_code':0,'owned_databases_removed':True},path)
            path.write_text('<TestRun><Counters total="2" executed="2" passed="2" notExecuted="0" failed="0"/></TestRun>',encoding='utf8')
            self.assertEqual(require_unskipped({'exit_code':0,'owned_databases_removed':True},path)['passed'],2)

    def test_main_verdict_cannot_promote_missing_runtime_profile(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);evidence=root/'proof.json';evidence.write_bytes(b'{}')
            task=dict(task_id='case',state='Partial',missing_cases=[],missing_case_profiles={'case':['LIVE']},case_source_shas={'case':'a'*40})
            item={'path':evidence.name,'bytes':2,'sha256':hashlib.sha256(evidence.read_bytes()).hexdigest()}
            decision=dict(authority='MAIN',stage='S6',integration_source_sha='current',task_decisions=[dict(task_id='case',state='Accepted',reason='review',evidence=[item],rollback='revert',runtime_review_sha='a'*40)])
            with self.assertRaises(ValueError): apply_main_decisions([task],decision,'current',root)
            self.assertEqual(task['state'],'Partial')
            task.update(state='ReadyForAcceptance',missing_case_profiles={})
            with self.assertRaises(ValueError): apply_main_decisions([task],decision,'different',root)
            self.assertNotIn('accepted_by',task)
            evidence.write_bytes(b'{"changed":true}')
            with self.assertRaises(ValueError): apply_main_decisions([task],decision,'current',root)
            evidence.write_bytes(b'{}')
            apply_main_decisions([task],decision,'current',root)
            self.assertEqual(task['accepted_by'],'MAIN')

if __name__=='__main__':unittest.main()
