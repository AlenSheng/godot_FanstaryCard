"""Versioned identity-input repair review of one already sealed capacity study.

The original verdict is never overwritten. The producer and its original
contract remain authoritative. No threshold or original criterion may change.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import subprocess

try:
    from . import pr13_distributed_capacity as capacity
except ImportError:
    import pr13_distributed_capacity as capacity


def review_identity_input_repair(input_path, repository, reviewer_revision, original_verdict, output):
    input_path=Path(input_path);repository=Path(repository);output=Path(output)
    capacity.require(not output.exists() and input_path.stat().st_size<=64*1024**2,'unsafe_review_output_or_input')
    flags=getattr(subprocess,'CREATE_NO_WINDOW',0)|getattr(subprocess,'BELOW_NORMAL_PRIORITY_CLASS',0)
    env=dict(os.environ,GIT_TERMINAL_PROMPT='0',GIT_NO_LAZY_FETCH='1')
    def git(*args):
        r=subprocess.run(['git',*args],cwd=repository,env=env,capture_output=True,timeout=30,creationflags=flags)
        capacity.require(r.returncode==0,'reviewer_Git_source_unavailable')
        return r.stdout
    capacity.require(len(reviewer_revision)==40 and git('rev-parse','--verify',reviewer_revision+'^{commit}').decode().strip()==reviewer_revision,
                     'invalid_reviewer_revision')
    raw=input_path.read_bytes();data=capacity.strict_json(raw);spec=data['spec']
    reference=capacity.load_git_reference(repository,spec['source_head'],workload_profile=spec.get('workload_profile'))
    prior_raw=Path(original_verdict).read_bytes();prior=capacity.strict_json(prior_raw)
    capacity.require(prior['capacity_accepted'] is False and prior['evidence_errors']==['workload_identity_mismatch'] and
        prior['captured_input_sha256']==hashlib.sha256(raw).hexdigest() and prior['source_head']==reference['head'] and
        prior['adjudicator_source_sha256']==reference['controls']['tools/pr13_distributed_capacity.py'],
        'original_verdict_not_the_same_identity_failure')
    reviewer_files={}
    for rel in ('tools/pr13_distributed_capacity.py','tools/pr13_workload_identity_review.py'):
        actual=(repository/rel).read_bytes();blob=git('show',reviewer_revision+':'+rel)
        capacity.require(actual==blob,'reviewer_worktree_differs_from_frozen_revision')
        reviewer_files[rel]=hashlib.sha256(actual).hexdigest()
    changed=git('diff','--name-only',reference['head'],reviewer_revision,'--','client','server','config','protocol','tools').decode().splitlines()
    capacity.require(all(name in reviewer_files or name.startswith('tools/tests/') for name in changed),
                     'repair_revision_changed_producer_or_other_runtime')
    reference['_identity_source_repair_repository']=str(repository.resolve())
    for path in reference['controls']:
        capacity.require(capacity._runtime_policy_source_matches(path,reference),
                         'repair_changed_other_frozen_control_or_original_criteria')
    original_auditor=git('show',reference['head']+':tools/pr13_distributed_capacity.py')
    current_auditor=(repository/'tools/pr13_distributed_capacity.py').read_bytes()
    old_projection=capacity._identity_criteria_projection(original_auditor)
    capacity.require(old_projection==capacity._identity_criteria_projection(current_auditor),
                     'acceptance_criteria_changed_beyond_identity_input_repair')
    captures={};identities=[]
    for item in data['captures']:
        capacity.require(item['host_id'] not in captures,'duplicate_review_host')
        root=Path(item['root']);root=root if root.is_absolute() else input_path.parent/root
        capture=capacity.Capture(root,item['files']);capture.verify_all()
        meta=capture.json('host-capture.original.json');report=capture.json(meta['report_file'])
        contract={k:v for k,v in report['load_contract'].items() if k not in
                  ('workload_profile_id','workload_profile_qualified','workload_profile_missing_reason')}
        identity=capacity.workload_profile_identity(contract,capacity._profile_identity_source_hashes(report['source']))
        original_profile=capture.json(str(PurePosixPath(meta['report_file']).parent/'workload-profile.json'))
        capacity.require(original_profile==identity and identity['workload_profile_id']==report['load_contract']['workload_profile_id'],
                         'original_producer_identity_definition_not_reproduced')
        captures[item['host_id']]=capture
        identities.append({'host':item['host_id'],'original_id':identity['workload_profile_id'],
            'complete_source_hash_count':len(identity['definition']['source_hashes']),'producer_definition_exactly_equal':True})
    result=capacity.assess_captures(spec,captures,reference,data['backend_before'],data['backend_after'])
    result.update(algorithm_version='distributed-capacity-v5-identity-input-repair-review',
        source_head=reference['head'],reviewer_revision=reviewer_revision,reviewer_files=reviewer_files,
        captured_input_sha256=hashlib.sha256(raw).hexdigest(),original_failed_verdict_sha256=hashlib.sha256(prior_raw).hexdigest(),
        original_failed_verdict_retained=True,identity_input_repair_only=True,
        all_original_acceptance_criteria_projection_sha256=hashlib.sha256(old_projection.encode()).hexdigest(),
        producer_identity_definitions=identities,new_live_worlds=0,whole_project_accepted=False)
    output.write_text(json.dumps(result,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--input',type=Path,required=True);p.add_argument('--source-repository',type=Path,required=True)
    p.add_argument('--reviewer-revision',required=True);p.add_argument('--original-verdict',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    result=review_identity_input_repair(a.input,a.source_repository,a.reviewer_revision,a.original_verdict,a.output)
    print(json.dumps({'capacity_accepted':result['capacity_accepted'],'evidence_errors':result['evidence_errors'],
                      'original_failure_retained':True,'new_live_worlds':0}))
    return 0 if result['capacity_accepted'] else 3

if __name__=='__main__':raise SystemExit(main())
