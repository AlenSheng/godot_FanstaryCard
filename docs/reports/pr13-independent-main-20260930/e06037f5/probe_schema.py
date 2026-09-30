"""Real owned status/audit replay; production functions and assertions unchanged."""
import argparse, hashlib, json, pathlib, subprocess, sys, time, traceback
p=argparse.ArgumentParser()
p.add_argument('--source', required=True)
p.add_argument('--fixture', choices=['finite-overflow','archive-match-list','archive-type-list','finite-control','archive-control'], required=True)
p.add_argument('--output', required=True)
a=p.parse_args()
source=pathlib.Path(a.source).resolve()
out=pathlib.Path(a.output).resolve()
out.mkdir(parents=True,exist_ok=False)
sys.path.insert(0,str(source/'tools'))
from gameplay_load_test import read_owned_statuses, read_audit_events
from gameplay_load_validation import new_events, aggregate_window, workload_snapshot, _number
from pr13_runtime_evidence import reconcile_cycles
code=r'''import json,os,pathlib,sys,time
base=pathlib.Path(sys.argv[1]);fixture=sys.argv[2];now=int(time.time()*1000)
row=dict(client_id='independent',pid=os.getpid(),run_id='independent-run',process_epoch='independent-epoch',status_seq=1,now_unix_ms=now,online=True,room=True,last_progress_age_ms=0)
event=dict(run_id=row['run_id'],client_id=row['client_id'],process_epoch=row['process_epoch'],event_seq=1,at_unix_ms=now,type='http',duration_ms=1e308 if fixture=='finite-overflow' else 1e100,status=500,ok=False,path='/fixture',phase='playing')
events=[event,dict(event,event_seq=2)]
if fixture.startswith('archive-'):
 event.update(type='lifecycle',event_type='cycle.started',cycle_id='independent:1',match_id='M',duration_ms=2)
 if fixture=='archive-match-list':event['match_id']=[]
 if fixture=='archive-type-list':event['event_type']=[]
 events=[event]
row.update(event_seq_max=len(events),telemetry=events,operations=events if not fixture.startswith('archive-') else [])
pathlib.Path(str(base)+'.telemetry.jsonl').write_text(''.join(json.dumps(e)+'\n' for e in events))
pathlib.Path(str(base)+'.status.json').write_text(json.dumps(row))
print(json.dumps(dict(pid=os.getpid(),status_written=True)),flush=True)
time.sleep(15)
'''
base=out/'client.json'
argv=[sys.executable,'-c',code,str(base),a.fixture]
wall=int(time.time()*1000);mono=time.monotonic()*1000
log=(out/'child.log').open('w')
child=subprocess.Popen(argv,stdout=log,stderr=subprocess.STDOUT)
record=dict(fixture=a.fixture,source_sha=subprocess.check_output(['git','rev-parse','HEAD'],cwd=source,text=True).strip(),child_argv=argv,pid=child.pid,started_at_ms=wall,started_at_monotonic_ms=mono,
            expected='No unhandled exception; malformed archive fields must classify invalid, finite metrics must aggregate or explicitly invalidate.',decision=None,Accepted=False)
try:
    deadline=time.monotonic()+5
    while not (out/'child.log').read_text().strip():
        if time.monotonic()>deadline:raise TimeoutError('owned child status deadline')
        time.sleep(.01)
    entry=dict(client_id='independent',process=child,report=base,run_id='independent-run',process_epoch='independent-epoch',started_at_ms=wall,started_at_monotonic_ms=mono)
    record['stage']='read_owned_statuses'
    rows,invalid=read_owned_statuses([entry],{},require_files=True)
    record.update(owned_statuses=len(rows),ownership_invalid=invalid)
    record['stage']='new_events'
    events,lost=new_events(rows,{})
    record.update(event_loss=lost,individual_duration_guard=[_number(e['duration_ms']) for e in rows[0]['telemetry']])
    record['stage']='aggregate_window'
    window=aggregate_window(events)
    record['window']=window
    record['stage']='workload_snapshot'
    record['population']=workload_snapshot([entry],rows,int(time.time()*1000),now_monotonic_ms=time.monotonic()*1000)
    if a.fixture.startswith('archive-'):
        record['stage']='read_audit_events'
        audit,errors=read_audit_events([entry],rows)
        record.update(archive_event_count=len(audit),archive_errors=errors)
        record['stage']='reconcile_cycles'
        record['cycle_counts']=reconcile_cycles(audit,int(time.time()*1000),int(time.time()*1000)+1)
    record.update(stage='completed',unhandled_exception=None,status='Passed')
except Exception as exc:
    record.update(unhandled_exception=type(exc).__name__,exception_message=str(exc),traceback=traceback.format_exc(),status='Failed')
    raise
finally:
    if child.poll() is None:child.terminate()
    record.update(child_exit_code=child.wait(timeout=5),child_reaped=True)
    log.close()
    record['source_files']=[dict(path='tools/'+name,sha256=hashlib.sha256((source/'tools'/name).read_bytes()).hexdigest()) for name in ['gameplay_load_test.py','gameplay_load_validation.py','pr13_runtime_evidence.py']]
    (out/'receipt.json').write_text(json.dumps(record,indent=2,allow_nan=False))
    print(json.dumps({k:record[k] for k in ['fixture','stage','status','unhandled_exception','child_reaped']}))
