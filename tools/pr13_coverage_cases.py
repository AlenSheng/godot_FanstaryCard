"""Controlled subsets of actual native receipts, plus actual workflow boundary checks."""
import argparse
import copy
import fnmatch
import hashlib
import json
from pathlib import Path
import subprocess
import xml.etree.ElementTree as ET
from pr13_suite_coverage import assess_trx,assess_gate

ROOT=Path(__file__).resolve().parents[1]
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def write(path,value):path.write_bytes((json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)+'\n').encode())
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);p.add_argument('--native',type=Path,required=True);args=p.parse_args();out=args.output.resolve();out.mkdir(parents=True,exist_ok=False)
    native=args.native.resolve();original=native/'lifecycle.trx';metadata=json.loads((native/'report.json').read_text(encoding='utf8'));required={'Real_Godot_ACK_response_loss_preserves_one_receipt_and_retryable_truth':3,'Real_load_runner_counts_three_games_once_and_STOP_during_ACK_never_completes':4,'Launch_failure_retries_without_duplicate_room_or_asset_reservation':2}
    actual=assess_trx(original,required)
    if actual['state']!='CoveredForMainReview' or metadata['exit_code']!=0:raise ValueError('Native parent is not the observed unskipped matrix')
    plan_path=ROOT/'docs/plans/PR13_ACCEPTANCE_DETAILS_20260930.json';contracts={c['id']:c for pkg in json.loads(plan_path.read_text(encoding='utf8'))['packages'] for task in pkg['subtasks'] for c in task['test_cases']};records=[]
    def record(cid,value,passed):records.append({'case_id':cid,'executed':True,'status':'Passed' if passed else 'Failed','setup':contracts[cid]['setup_and_injection'],'expected':contracts[cid]['expected'],'actual':value,'profiles_executed':['OFFLINE'],'scope':'Actual validation/workflow code with an explicitly derived controlled native subset or gate fault. Original TRX remains immutable; no new PG or remote CI pass claim.'})
    tree=ET.parse(original);ns=tree.getroot().tag.split('}')[0]+'}';results=tree.find('.//'+ns+'Results');first=list(results)[0]
    for child in list(results):
        if child is not first:results.remove(child)
    counters=tree.find('.//'+ns+'Counters');counters.attrib.update(total='1',executed='1',passed='1',failed='0',notExecuted='0')
    subset=out/'controlled-one-row.trx';tree.write(subset,encoding='utf-8',xml_declaration=True);partial=assess_trx(subset,required)
    record('PR13-A07.2-T01',partial,partial['state']=='Blocked' and bool(partial['missing_assertion_rows']))
    record('PR13-A07.3-T03',dict(partial,job_exit_code=0,parent_trx_sha256=sha(original)),partial['state']=='Blocked')
    head=metadata['source_sha'];suites={'load':dict(actual,source_sha=head),'numerical':{'state':'Failed','source_sha':head}}
    gate=assess_gate(suites,['load','numerical'],expected_source_sha=head)
    record('PR13-A07.4-T01',gate,gate['state']=='Failed' and gate['failed_suites']==['numerical'])
    baseline=assess_gate({'load':dict(actual,source_sha=head)},['load','numerical'],expected_source_sha=head,baseline_compile_exit=1)
    record('PR13-A07.4-T02',baseline,baseline['state']=='Blocked' and 'numerical' in baseline['missing_suites'])
    workflow=ROOT/'.github/workflows/gameplay-load.yml';text=workflow.read_text(encoding='utf8');paths={};section=None
    for line in text.splitlines():
        if line in ('  pull_request:','  push:'):section=line.strip(': ');paths[section]=[]
        elif line=='  workflow_dispatch:':section=None
        elif section and line.startswith("      - '"):paths[section].append(line.split("'")[1])
    changed='client/tests/run_ready_stop_faults.gd';matches={key:any(fnmatch.fnmatchcase(changed,pattern) for pattern in values) for key,values in paths.items()}
    record('PR13-A07.3-T01',{'workflow_sha256':sha(workflow),'changed_file':changed,'event_matches':matches,'remote_ci_pass_claim':False},matches.get('pull_request') and matches.get('push'))
    # This workflow has read-only permissions, no credential persistence,
    # production secrets, deployment dispatch, or upload/merge/publish commands.
    forbidden=['secrets.','contents: write','packages: write','pull-requests: write','workflow_dispatch --','gh pr merge','docker push','persist-credentials: true']
    observed=[word for word in forbidden if word in text]
    record('PR13-A07.3-T02',{'workflow_sha256':sha(workflow),'contents_permission':'read','forbidden_write_or_credential_patterns':observed,'fork_event':'pull_request','production_actions':False},'contents: read' in text and not observed and 'pull_request_target:' not in text)
    (out/'cases.jsonl').write_bytes(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in records).encode())
    write(out/'report.json',{'source_sha':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),'plan_sha256':sha(plan_path),'source':{'scope':'controlled native subset/gate validator and actual workflow paths/permissions','input_hashes':{p:sha(ROOT/p) for p in ('tools/pr13_suite_coverage.py','tools/pr13_coverage_cases.py','.github/workflows/gameplay-load.yml')}},'executed':len(records),'passed':sum(r['status']=='Passed' for r in records),'native_parent_sha256':sha(original),'accepted':False})
    print(json.dumps({'executed':len(records),'passed':sum(r['status']=='Passed' for r in records)}));return 0 if all(r['status']=='Passed' for r in records) else 1
if __name__=='__main__':raise SystemExit(main())
