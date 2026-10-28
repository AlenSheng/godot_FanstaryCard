"""Actual owned status-file -> reader -> event reducer -> validation path."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time
import traceback

parser = argparse.ArgumentParser()
parser.add_argument('--source', required=True)
parser.add_argument('--output', required=True)
args = parser.parse_args()
source = Path(args.source).resolve()
out = Path(args.output).resolve()
out.mkdir(parents=True, exist_ok=False)
sys.path.insert(0, str(source / 'tools'))
from gameplay_load_test import read_owned_statuses, read_audit_events
from gameplay_load_validation import aggregate_window, new_events, workload_snapshot, classify_stop
from pr13_runtime_evidence import reconcile_cycles

code = r'''import json,os,pathlib,sys,time
base=pathlib.Path(sys.argv[1]); fixture=sys.argv[2]
row=dict(client_id='schema-owned',pid=os.getpid(),run_id='schema-run',process_epoch='schema-epoch',status_seq=1,
 now_unix_ms=int(time.time()*1000),online=True,room=True,last_progress_age_ms=0,event_seq_max=1)
event=dict(run_id=row['run_id'],client_id=row['client_id'],process_epoch=row['process_epoch'],event_seq=1,
 type='http',duration_ms=2,status=500,ok=False,path='/fixture',phase='playing')
if fixture=='type-list': event['type']=[]
if fixture=='type-dict': event['type']={}
if fixture=='huge-duration': event['duration_ms']=10**400
if fixture=='huge-timestamp': row['now_unix_ms']=10**400
if fixture in ('huge-event-time','unhashable-match','unhashable-event-type'):
 event.update(type='lifecycle',event_type='cycle.started',cycle_id='schema:1',match_id='M',at_unix_ms=10**400 if fixture=='huge-event-time' else row['now_unix_ms'])
 if fixture=='unhashable-match': event['match_id']=[]
 if fixture=='unhashable-event-type': event['event_type']=[]
if fixture=='fmean-overflow': event['duration_ms']=1e308
events=[event]
if fixture=='fmean-overflow': events.append(dict(event,event_seq=2)); row['event_seq_max']=2
row['telemetry']=events; row['operations']=events if event['type']=='http' else []
pathlib.Path(str(base)+'.status.json').write_text(json.dumps(row))
pathlib.Path(str(base)+'.telemetry.jsonl').write_text(''.join(json.dumps(e)+'\n' for e in events))
print(json.dumps(dict(pid=os.getpid(),written=True)),flush=True)
time.sleep(15)
'''
records=[]
for fixture in ('fmean-overflow','unhashable-match','unhashable-event-type'):
 directory=out/fixture; directory.mkdir(); report=directory/'client.json'
 argv=[sys.executable,'-c',code,str(report),fixture]
 started_wall=int(time.time()*1000); started_monotonic=time.monotonic()*1000
 with (directory/'child.log').open('w') as log:
  child=subprocess.Popen(argv,stdout=log,stderr=subprocess.STDOUT)
  record=dict(fixture=fixture,pid=child.pid,argv=argv,source=str(source),stage='status_write')
  try:
   deadline=time.monotonic()+5
   while not Path(str(report)+'.status.json').exists():
    if time.monotonic()>deadline: raise TimeoutError('owned child status deadline')
    time.sleep(.01)
   entry=dict(client_id='schema-owned',process=child,report=report,run_id='schema-run',process_epoch='schema-epoch',started_at_ms=started_wall,started_at_monotonic_ms=started_monotonic)
   record['stage']='read_owned_statuses'
   rows,invalid=read_owned_statuses([entry],{},require_files=True)
   record.update(ownership_invalid=invalid,owned_statuses=len(rows))
   record['stage']='new_events'
   events,lost=new_events(rows,{})
   record['event_loss']=lost
   record['stage']='aggregate_window'
   window=aggregate_window(events)
   record['stage']='workload_snapshot'
   population=workload_snapshot([entry],rows,int(time.time()*1000),now_monotonic_ms=time.monotonic()*1000)
   archive_errors=[]; counts=None
   if fixture in ('huge-event-time','unhashable-match','unhashable-event-type'):
    record['stage']='read_audit_events -> reconcile_cycles'
    audit,archive_errors=read_audit_events([entry],rows)
    counts=reconcile_cycles(audit,int(time.time()*1000),int(time.time()*1000)+1)
   invalid_evidence=bool(window['invalid_metric_count'] or population['invalid_schema_count'] or invalid or lost or archive_errors or (counts and counts['evidence_errors']))
   record.update(archive_errors=archive_errors,cycle_reconciliation=counts)
   record.update(window=window,population=population,invalid_evidence=invalid_evidence,
    decision=classify_stop('invalid_evidence:invalid_telemetry' if invalid_evidence else 'duration_limit'))
   record['stage']='completed'; record['unhandled_exception']=None
  except Exception as exc:
   record.update(unhandled_exception=type(exc).__name__,exception_message=str(exc),traceback=traceback.format_exc())
  finally:
   if child.poll() is None: child.terminate()
   record.update(child_exit_code=child.wait(timeout=5),child_reaped=True)
  (directory/'receipt.json').write_text(json.dumps(record,indent=2))
  records.append(record)
sources=[]
for name in ('gameplay_load_validation.py','gameplay_load_test.py','cloud_load_test.py','pr13_runtime_evidence.py'):
 data=(source/'tools'/name).read_bytes()
 sources.append(dict(path='tools/'+name,bytes=len(data),sha256=hashlib.sha256(data).hexdigest()))
report=dict(records=records,source_files=sources,all_reaped=all(x['child_reaped'] for x in records),
 unhandled_exceptions=sum(x['unhandled_exception'] is not None for x in records),
 invalid_failures=sum(x.get('decision',{}).get('exit_code')==3 for x in records),Accepted=False)
(out/'REPORT.json').write_text(json.dumps(report,indent=2))
print(json.dumps(dict(unhandled_exceptions=report['unhandled_exceptions'],invalid_failures=report['invalid_failures'],all_reaped=report['all_reaped'])))
