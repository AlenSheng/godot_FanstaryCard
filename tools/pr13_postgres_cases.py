"""Export canonical cases from completed, unskipped owned PostgreSQL executions."""
import argparse
from collections import defaultdict
import hashlib
import json
from pathlib import Path
import subprocess
import xml.etree.ElementTree as ET
try:
    from pr13_audit_replay import check_files
except ModuleNotFoundError:
    from tools.pr13_audit_replay import check_files
ROOT=Path(__file__).resolve().parents[1]
READY_GROUPS={
 'LOAD-04.4-T01':['required_lost_reconnect'],
 'LOAD-04.4-T03':['stop_prepare_await','stop_enqueue_await','stop_ticket_await','stop_queue_wait','stop_ready_enqueue_await','stop_ready_before_send','ready_send_all_lost_stop'],
 'PR13-A04.4-T01':['stop_ready_enqueue_await','stop_ready_before_send','ready_send_all_lost_stop'],
 'PR13-A04.4-T02':['ready_started_lost_reconnect','ready_replies_lost_reconnect','ready_send_lost_reconnect']}
A05_EXPECTED={f'PR13-A05.{n}-T0{c}' for n in (1,2,3) for c in (1,2,3)}
LOAD02_EXPECTED={f'LOAD-02.2-T0{c}' for c in (1,2,3)}


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def read(path):return json.loads(path.read_text(encoding='utf8'))
def write(path,data):path.write_bytes((json.dumps(data,ensure_ascii=False,indent=2,allow_nan=False)+'\n').encode())


def require_unskipped(report,trx):
    counters=ET.parse(trx).find('.//{*}Counters')
    if counters is None:raise ValueError('Actual TRX counters required')
    c={k:int(v) for k,v in counters.attrib.items()}
    if report.get('exit_code')!=0 or report.get('owned_databases_removed') is not True or c.get('executed',0)<1 or c.get('passed')!=c.get('total') or c.get('notExecuted',0) or c.get('failed',0):
        raise ValueError('Incomplete/failed/skipped integration cannot export passed canonical cases')
    return c


def public_assets(data):
    if not isinstance(data,dict):return None
    allowed={'Gold','Potions','Location','GoldLedger','Movements','PendingHolds','LockedEquipment'}
    return {k:v for k,v in data.items() if k in allowed}


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--ready',type=Path,required=True);parser.add_argument('--lifecycle',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();output=args.output.resolve()
    if output.exists():raise ValueError('Immutable canonical export already exists')
    ready=args.ready.resolve();lifecycle=args.lifecycle.resolve();rr=read(ready/'report.json');lr=read(lifecycle/'report.json')
    validated=check_files(ready,{'files':read(ready/'manifest.json')})
    if any(r['state']!='Matching' for r in validated):raise ValueError('Immutable READY evidence changed')
    if not rr.get('ok') or rr.get('case_count')!=15 or rr.get('passed_case_count')!=15 or rr.get('owned_fixture_databases_removed') is not True or rr.get('owned_server_stopped') is not True:
        raise ValueError('Full READY matrix and owned cleanup required')
    counters=require_unskipped(lr,lifecycle/'lifecycle.trx')
    if rr['source_sha']!=lr['source_sha']:raise ValueError('Mixed runtime source SHA')
    plan_path=ROOT/'docs/plans/PR13_ACCEPTANCE_DETAILS_20260930.json';plan=read(plan_path)
    contracts={c['id']:c for p in plan['packages'] for s in p['subtasks'] for c in s['test_cases']}
    native={r['case']:r for r in rr['cases']};records=[]
    def record(case_id,actual,profiles):
        contract=contracts[case_id];records.append({'case_id':case_id,'executed':True,'status':'Passed','setup':contract['setup_and_injection'],'expected':contract['expected'],'actual':actual,'profiles_executed':profiles})
    for case_id,names in READY_GROUPS.items():
        results=[]
        for name in names:
            r=native[name];client=r['actual']
            if not r['passed'] or not r['postgres_passed'] or not r['transport_passed'] or not client['local_terminal'] or not client['route_probe_clear']:raise ValueError('READY subcase lacks postconditions')
            results.append({'case':name,'passed':True,'cleanup':client['cleanup']['state'],'route_clear':client['route_probe_clear'],'local_terminal':client['local_terminal'],'ready_send_count':client['ready_send_count'],'ready_send_after_stop':client['ready_send_after_stop'],'matches':r['postgres']['matches'],'pending_holds':r['postgres']['pending_settlement_holds'],'locked_equipment':r['postgres']['locked_equipment'],'source_case_sha256':sha(ready/name/'case.raw.json')})
        record(case_id,{'native_subcases':results,'synthetic_old_packet_excluded':True},['OFFLINE','POSTGRES'])
    collected=defaultdict(list)
    with (lifecycle/'process-evidence/receipts.jsonl').open(encoding='utf8') as stream:
        for line in stream:
            if len(line)>8*1024**2:raise ValueError('Receipt line exceeds bound')
            row=json.loads(line);e=row['evidence'];ids=[]
            if row['caseId'] in ('A05-transaction-fault-passed','A05-healthy-passed','A05-runtime-passed'):
                ids=e['canonical'] if isinstance(e['canonical'],list) else [e['canonical']]
                if e.get('also'):ids+=[e['also']]
            elif row['caseId'] in LOAD02_EXPECTED:
                if e.get('status')!='Passed':raise ValueError('LOAD02 receipt failed')
                ids=[row['caseId']]
            for case_id in ids:
                if case_id not in A05_EXPECTED|LOAD02_EXPECTED:raise ValueError('Unknown canonical runtime receipt')
                collected[case_id].append({'native_receipt':row['caseId'],'mode':e.get('mode'),'source_receipt_sha256':hashlib.sha256(line.encode()).hexdigest(),'before_assets':public_assets(e.get('before')),'after_assets':public_assets(e.get('after',e.get('finalAssets'))),'acknowledged':e.get('acknowledged'),'next_prepare_cancel_verified':e.get('nextPrepareCancelVerified'),'scope':e.get('scope',e.get('limitations'))})
    if set(collected)!=A05_EXPECTED|LOAD02_EXPECTED:raise ValueError('Missing mandatory canonical runtime receipts')
    for case_id,actual in sorted(collected.items()):record(case_id,{'actual_native_receipts':actual,'trx_unskipped_passed':True},['OFFLINE','POSTGRES','AUDIT'] if case_id in A05_EXPECTED else ['OFFLINE','POSTGRES'])
    # These exact aliases retain the underlying canonical transaction/runtime
    # receipts; no new cycle or independent matrix is inferred from an exit code.
    for cid,parent in [('LOAD-05.3-T03','PR13-A05.1-T01'),('LOAD-05.4-T02','PR13-A05.1-T01'),
                       ('LOAD-10.3-T02','PR13-A05.3-T03'),('PR13-A09.3-T01','PR13-A05.3-T03'),
                       ('PR13-A03.4-T01','PR13-A05.2-T03')]:
        record(cid,{'actual_native_receipts':collected[parent],'exact_parent_case':parent,'trx_unskipped_passed':True,
                    'scope':'Exact real pending-hold/OS-restart/old-callback/ACK fault contract; natural full-route cycles separate.'},['OFFLINE','POSTGRES','AUDIT'])
    output.mkdir(parents=True,exist_ok=False)
    (output/'cases.jsonl').write_bytes(''.join(json.dumps(r,ensure_ascii=False,allow_nan=False)+'\n' for r in records).encode())
    files=[ready/'report.json',ready/'manifest.json',ready/'toolchain.json',ready/'inputs.json',lifecycle/'report.json',lifecycle/'lifecycle.trx',lifecycle/'process-evidence/receipts.jsonl']
    report={'source_sha':rr['source_sha'],'exporter_sha':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),'plan_sha256':sha(plan_path),'source':{'scope':'Actual owned full Program, production Godot and native PG tests; byte-drop/restart/transaction/route/assets evidence; no LIVE capacity/human claim','input_hashes':rr['input_hashes'] if 'input_hashes' in rr else read(ready/'inputs.json')['input_hashes']},'executed':len(records),'passed':len(records),'accepted':False,'native_ready_subcases':15,'native_pg_counters':counters,'remaining':'Other explicit cases/layers and MAIN task verdicts remain separate.'}
    write(output/'report.json',report);write(output/'artifact-index.json',{'files':[{'path':p.relative_to(ROOT).as_posix(),'bytes':p.stat().st_size,'sha256':sha(p)} for p in files]})
    write(output/'manifest.json',{'files':[{'path':p.name,'bytes':p.stat().st_size,'sha256':sha(p)} for p in sorted(output.glob('*')) if p.is_file()]})
    print(json.dumps({'executed':len(records),'passed':len(records),'source_sha':rr['source_sha']}));return 0

if __name__=='__main__':raise SystemExit(main())
