"""Exact actual PostgreSQL launch, ACK and runner assertions, no natural-route claim."""
import argparse
import hashlib
import json
from pathlib import Path
import xml.etree.ElementTree as ET

ROOT=Path(__file__).resolve().parents[1]
MAPPING={
 'LOAD-10.2-T02':['Real_Godot_ACK_response_loss_preserves_one_receipt_and_retryable_truth','Real_load_runner_counts_three_games_once_and_STOP_during_ACK_never_completes'],
 'LOAD-09.2-T02':['Recovery_validates_durable_terminal_checkpoint_and_preserves_next_route'],
 'PR13-A09.3-T02':['Recovery_validates_durable_terminal_checkpoint_and_preserves_next_route'],
 'LOAD-04.4-T02':['Launch_failure_retries_without_duplicate_room_or_asset_reservation'],
 'LOAD-09.2-T01':['Launch_failure_retries_without_duplicate_room_or_asset_reservation'],
 'LOAD-09.2-T03':['Recovery_validates_durable_terminal_checkpoint_and_preserves_next_route'],
 'PR13-A04.3-T01':['Launch_failure_retries_without_duplicate_room_or_asset_reservation'],
 'PR13-A04.3-T02':['Launch_failure_retries_without_duplicate_room_or_asset_reservation'],
 'PR13-A04.3-T03':['Full_host_MarkRunning_committed_response_loss_recovers_one_room_and_actual_client_routes','MarkRunning_commit_response_loss_retries_same_room_and_restart_restores_it'],
 'LOAD-05.1-T01':['Real_Godot_ACK_response_loss_preserves_one_receipt_and_retryable_truth'],
 'LOAD-05.3-T02':['Real_load_runner_counts_three_games_once_and_STOP_during_ACK_never_completes'],
 'LOAD-05.4-T01':['Real_Godot_ACK_response_loss_preserves_one_receipt_and_retryable_truth','Settlement_commit_response_loss_recovers_same_receipt_and_credits_assets_once'],
 'LOAD-05.4-T03':['Real_load_runner_counts_three_games_once_and_STOP_during_ACK_never_completes'],
 'PR13-A03.3-T01':['Real_Godot_ACK_response_loss_preserves_one_receipt_and_retryable_truth','Settlement_commit_response_loss_recovers_same_receipt_and_credits_assets_once'],
 'PR13-A03.3-T02':['Real_Godot_ACK_response_loss_preserves_one_receipt_and_retryable_truth'],
 'PR13-A02.4-T03':['Real_Godot_ACK_response_loss_preserves_one_receipt_and_retryable_truth','Settlement_commit_response_loss_recovers_same_receipt_and_credits_assets_once'],
}
EXPECTED_ROWS={'Launch_failure_retries_without_duplicate_room_or_asset_reservation':2,
 'Recovery_validates_durable_terminal_checkpoint_and_preserves_next_route':2,
 'Real_Godot_ACK_response_loss_preserves_one_receipt_and_retryable_truth':3,
 'Real_load_runner_counts_three_games_once_and_STOP_during_ACK_never_completes':4}

def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def write(path,value):path.write_bytes((json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)+'\n').encode())
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--native',required=True,type=Path);p.add_argument('--output',required=True,type=Path);args=p.parse_args();native=args.native.resolve();out=args.output.resolve()
    report=json.loads((native/'report.json').read_text(encoding='utf8'));trx=native/'lifecycle.trx';tree=ET.parse(trx);counters={k:int(v) for k,v in tree.find('.//{*}Counters').attrib.items()}
    if report['exit_code']!=0 or report['owned_databases_removed'] is not True or counters['total']!=16 or counters['passed']!=16 or counters['executed']!=16 or counters.get('notExecuted',0):raise ValueError('The exact unskipped owned 16-case matrix is required')
    methods={n.attrib['id']:n.find('{*}TestMethod').attrib for n in tree.findall('.//{*}UnitTest')}
    actual=[]
    for n in tree.findall('.//{*}UnitTestResult'):
        definition=methods[n.attrib['testId']];actual.append({'method':definition['name'],'class':definition['className'].split(',')[0],'case':n.attrib['testName'],'outcome':n.attrib['outcome']})
    plan_path=ROOT/'docs/plans/PR13_ACCEPTANCE_DETAILS_20260930.json';contracts={c['id']:c for pkg in json.loads(plan_path.read_text(encoding='utf8'))['packages'] for task in pkg['subtasks'] for c in task['test_cases']}
    records=[]
    for cid,names in MAPPING.items():
        selected=[]
        for name in names:
            rows=[r for r in actual if r['method']==name]
            if len(rows)!=EXPECTED_ROWS.get(name,1) or any(r['outcome']!='Passed' for r in rows):raise ValueError('Expected exact assertion rows absent or failed: '+name)
            selected.extend(rows)
        records.append({'case_id':cid,'executed':True,'status':'Passed','setup':contracts[cid]['setup_and_injection'],'expected':contracts[cid]['expected'],'actual':{'native_assertions':selected,'trx_sha256':sha(trx)},'profiles_executed':['OFFLINE','POSTGRES'],
            'scope':'Actual owned PG repositories/coordinator and production GameStore/load-runner/full Program where named; explicit legal extract/abandon driver is functional lifecycle evidence. Natural combat routes, LIVE, capacity and human experience remain separate.'})
    receipts=native/'process-evidence/receipts.jsonl';public=[]
    for line in receipts.read_text(encoding='utf8').splitlines():
        row=json.loads(line);name=row['caseId'];e=row['evidence']
        if name.startswith(('ACK-CYCLE-','ACK-FAULT-','ACK-STOP-','LOAD-04.4-T02-')):
            keep=('mode','expectedGames','expectedCompletions','partition','equipmentLocation','durableStatus','responseDelivered','dropped')
            public.append({'receipt':name,'evidence_sha256':hashlib.sha256(line.encode()).hexdigest(),'observations':{k:e[k] for k in keep if k in e}})
    out.mkdir(parents=True,exist_ok=False)
    (out/'cases.jsonl').write_bytes(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in records).encode())
    write(out/'report.json',{'source_sha':report['source_sha'],'plan_sha256':sha(plan_path),'source':{'scope':'exact current native PG launch/ACK fault matrix','input_hashes':{'native_trx':sha(trx),'raw_native_receipts':sha(receipts)}},'executed':len(records),'passed':len(records),'native_counters':counters,'accepted':False})
    write(out/'native-receipt-summary.json',{'receipts':public,'asset_mutation_or_history_repair':False})
    write(out/'private-parent-index.json',{'files':[{'path':f.relative_to(ROOT).as_posix(),'bytes':f.stat().st_size,'sha256':sha(f)} for f in (trx,native/'report.json',receipts)]})
    print(json.dumps({'executed':len(records),'passed':len(records)}));return 0
if __name__=='__main__':raise SystemExit(main())
