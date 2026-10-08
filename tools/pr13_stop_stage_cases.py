"""Actual owned child STOP/drain/tail protocol for declared controlled phase labels."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from cloud_load_test import stop_all
from gameplay_load_validation import classify_stop, owned_statuses
from pr13_render_cases import ROOT, sha, write

CHILD = '''import json,os,pathlib,time
p=pathlib.Path(os.environ['OWNED_REPORT']);stop=pathlib.Path(os.environ['OWNED_STOP'])
row=dict(pid=os.getpid(),client_id=os.environ['OWNED_ID'],run_id='controlled-stop-phases',process_epoch=os.environ['OWNED_EPOCH'],status_seq=1,stage=os.environ['OWNED_STAGE'],now_unix_ms=time.time()*1000,online=False,room=False,cycles_completed=0,cleanup=dict(state='Pending'),event_seq_max=0,audit_lost_count=0)
p.write_text(json.dumps(row),encoding='utf8')
deadline=time.monotonic()+20
while not stop.exists() and time.monotonic()<deadline:time.sleep(.01)
event=dict(run_id=row['run_id'],client_id=row['client_id'],process_epoch=row['process_epoch'],event_seq=1,event_type='cleanup.verified',cleanup=dict(state='Passed'),type='lifecycle')
pathlib.Path(str(p)+'.telemetry.jsonl').write_text(json.dumps(event)+'\\n',encoding='utf8')
row.update(cleanup=dict(state='Passed'),event_seq_max=1,status_seq=2)
p.write_text(json.dumps(row),encoding='utf8')
'''


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    out=args.output.resolve();out.mkdir(parents=True,exist_ok=False);script=out/'child.py';script.write_bytes(CHILD.encode())
    stages=['login','preparation','enqueue','ticket','ready','move','settlement','ack'];entries=[];actual=[]
    try:
        for index,stage in enumerate(stages):
            report=out/(stage+'.json');stop=out/(stage+'.STOP');cid='controlled-'+stage;epoch='epoch-'+str(index)
            env=dict(os.environ,OWNED_REPORT=str(report),OWNED_STOP=str(stop),OWNED_ID=cid,OWNED_EPOCH=epoch,OWNED_STAGE=stage)
            child=subprocess.Popen([sys.executable,str(script)],env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,
                                   creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            entry=dict(process=child,report=report,client_id=cid,run_id='controlled-stop-phases',process_epoch=epoch,pid=child.pid,stop=stop)
            entries.append(entry);deadline=time.monotonic()+5
            while not report.exists() and child.poll() is None and time.monotonic()<deadline:time.sleep(.01)
            if not report.exists():raise ValueError('Actual owned child failed to publish stage receipt')
        for entry in entries:
            forced=stop_all([entry],entry['stop'],grace_seconds=3)
            final=json.loads(entry['report'].read_text(encoding='utf8'));owned,invalid=owned_statuses([entry],[final])
            tail=Path(str(entry['report'])+'.telemetry.jsonl');events=[json.loads(line) for line in tail.read_text(encoding='utf8').splitlines()]
            classification=classify_stop('operator_stop_file',False,False)
            ok=not forced and entry['process'].returncode==0 and invalid==0 and len(owned)==1 and final['cycles_completed']==0 and final['cleanup']['state']=='Passed' and len(events)==1 and events[0]['event_seq']==final['event_seq_max']
            if not ok:raise ValueError('STOP/drain/identity/final-tail invariant failed')
            actual.append(dict(stage=final['stage'],pid=entry['pid'],child_exit=0,forced_processes=forced,completed_cycles=0,
                               classification=classification,cleanup='Passed',final_tail_high_watermark=1,tail_sha256=sha(tail)))
    finally:
        for entry in entries:
            if entry['process'].poll() is None:entry['process'].kill();entry['process'].wait(timeout=5)
    plan=ROOT/'docs/plans/PR13_ACCEPTANCE_DETAILS_20260930.json';contract=next(c for p in json.loads(plan.read_text(encoding='utf8'))['packages'] for s in p['subtasks'] for c in s['test_cases'] if c['id']=='LOAD-10.3-T03')
    row=dict(case_id=contract['id'],executed=True,status='Passed',setup=contract['setup_and_injection'],expected=contract['expected'],profiles_executed=['OFFLINE'],actual=dict(actual_owned_children=actual,phase_labels_controlled=True),scope='Actual production coordinator STOP/identity/classification/drain primitives with eight owned Python children and declared phase labels. No Godot/Program/PG stage injection or natural completion claim; those mandatory layers remain separate.')
    (out/'cases.jsonl').write_bytes((json.dumps(row,ensure_ascii=False)+'\n').encode());write(out/'report.json',dict(source_sha=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),plan_sha256=sha(plan),source=dict(scope=row['scope'],input_hashes={p:sha(ROOT/p) for p in ['tools/pr13_stop_stage_cases.py','tools/cloud_load_test.py','tools/gameplay_load_validation.py']}),executed=1,passed=1,accepted=False))
    print(json.dumps(dict(executed=1,passed=1,actual_owned_children=8)));return 0


if __name__=='__main__':raise SystemExit(main())
