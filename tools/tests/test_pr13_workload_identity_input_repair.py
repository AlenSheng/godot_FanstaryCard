"""Regression for actual producer shape and a narrowly versioned review repair."""
import copy
import hashlib
import subprocess
import tempfile
import unittest
from unittest import mock
from pathlib import Path

from tools import pr13_distributed_capacity as c
from tools.gameplay_load_validation import workload_profile_identity
from tools.tests.test_pr13_distributed_capacity import SyntheticStudy

COLLECTOR='7b0f6008f4527c5c1536e9090d7d21820e72551a'
REPAIR='34f1d55dd022a806edb642339872292616a29b34'
ROOT=Path(__file__).resolve().parents[2]


class WorkloadIdentityInputRepairTests(unittest.TestCase):
    def test_actual_producer_definition_includes_complete_active_input_map(self):
        source={'sha256':{'tools/driver.py':'1'*64,'client/main.gd':'2'*64},
                'active_client_project':{'input_hashes':{'client/main.gd':'2'*64,'client/font.ttf':'3'*64}}}
        original=copy.deepcopy(source);combined=dict(source['sha256']);combined.update(source['active_client_project']['input_hashes'])
        contract={'profile':'active-hold','target_online':30}
        expected=workload_profile_identity(contract,combined)
        self.assertEqual(expected,workload_profile_identity(contract,c._profile_identity_source_hashes(source)))
        self.assertNotEqual(expected['workload_profile_id'],workload_profile_identity(contract,source['sha256'])['workload_profile_id'])
        self.assertEqual(original,source)

    def test_control_and_active_client_dependencies_both_change_identity(self):
        base={'sha256':{'tools/driver.py':'1'*64},'active_client_project':{'input_hashes':{'client/main.gd':'2'*64}}}
        contract={'profile':'active-hold'}
        first=workload_profile_identity(contract,c._profile_identity_source_hashes(base))['workload_profile_id']
        for layer in ('control','client'):
            source=copy.deepcopy(base)
            if layer=='control':source['sha256']['tools/driver.py']='3'*64
            else:source['active_client_project']['input_hashes']['client/main.gd']='3'*64
            with self.subTest(layer=layer):self.assertNotEqual(first,workload_profile_identity(contract,c._profile_identity_source_hashes(source))['workload_profile_id'])

    def test_original_criteria_equal_only_after_named_identity_repair(self):
        flags=getattr(subprocess,'CREATE_NO_WINDOW',0)
        old=subprocess.check_output(['git','show',COLLECTOR+':tools/pr13_distributed_capacity.py'],cwd=ROOT,creationflags=flags)
        current=subprocess.check_output(['git','show',REPAIR+':tools/pr13_distributed_capacity.py'],cwd=ROOT,creationflags=flags)
        projection=c._identity_criteria_projection(current)
        self.assertEqual(c._identity_criteria_projection(old),projection)
        for before,after in [('minimum_coverage=.95','minimum_coverage=.1'),
                             ("required_transition_policy = CAPACITY_RECOVERY_POLICY_V2 if aggregate else AUTHORITY_TRANSITION_POLICY", "required_transition_policy = 'anything'"),
                             ("policy['command_p95_limit_ms']",'999999')]:
            text=current.decode()
            self.assertIn(before,text)
            with self.subTest(change=before):self.assertNotEqual(projection,c._identity_criteria_projection(text.replace(before,after)))

    def test_identity_repair_is_explicit_not_an_implicit_runtime_override(self):
        ref=c.load_git_reference(ROOT,COLLECTOR,workload_profile='full-native60-global50-aggregate-v2')
        self.assertFalse(c._runtime_policy_source_matches('tools/pr13_distributed_capacity.py',ref))
        ref['_identity_source_repair_repository']=str(ROOT)
        # Later user-directed budget changes must not silently enter the old
        # identity-only review. The exact frozen repair revision still works.
        self.assertFalse(c._runtime_policy_source_matches('tools/pr13_distributed_capacity.py',ref))
        repair=subprocess.check_output(['git','show',REPAIR+':tools/pr13_distributed_capacity.py'],cwd=ROOT,
            creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        target=(ROOT/'tools/pr13_distributed_capacity.py').resolve();read_bytes=Path.read_bytes
        with mock.patch.object(Path,'read_bytes',lambda p:repair if p.resolve()==target else read_bytes(p)):
            self.assertTrue(c._runtime_policy_source_matches('tools/pr13_distributed_capacity.py',ref))
        ref['controls']['tools/pr13_authority_transitions.py']='0'*64
        self.assertFalse(c._runtime_policy_source_matches('tools/pr13_authority_transitions.py',ref))

    def test_producer_shaped_definition_is_replayed_for_both_synthetic_hosts(self):
        with tempfile.TemporaryDirectory(prefix='pr13-identity-merge-') as directory:
            study=SyntheticStudy(directory,aggregate=True)
            for host in ('windows','cloud'):
                report=study.report(host);contract={k:v for k,v in report['load_contract'].items() if k not in
                    ('workload_profile_id','workload_profile_qualified','workload_profile_missing_reason')}
                sources=dict(report['source']['sha256']);sources.update(report['source']['active_client_project']['input_hashes'])
                self.assertEqual(workload_profile_identity(contract,sources)['workload_profile_id'],report['load_contract']['workload_profile_id'])
            self.assertTrue(study.assess()['capacity_accepted'])

    def test_control_only_identity_cannot_replace_the_complete_definition(self):
        with tempfile.TemporaryDirectory(prefix='pr13-identity-omission-') as directory:
            study=SyntheticStudy(directory,aggregate=True);report=study.report('windows')
            contract={k:v for k,v in report['load_contract'].items() if k not in
                ('workload_profile_id','workload_profile_qualified','workload_profile_missing_reason')}
            report['load_contract']['workload_profile_id']=workload_profile_identity(contract,report['source']['sha256'])['workload_profile_id']
            study.put_report('windows',report)
            result=study.assess();self.assertFalse(result['capacity_accepted'])
            self.assertIn('workload_identity_mismatch',result['evidence_errors'])


if __name__=='__main__':unittest.main()
