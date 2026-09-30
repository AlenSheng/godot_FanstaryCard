"""Five frozen, real-file schema boundaries; unmodified production helpers."""
import argparse,json,pathlib,subprocess,sys,time,traceback
p=argparse.ArgumentParser();p.add_argument('--source',required=True);p.add_argument('--output',required=True);a=p.parse_args()
source=pathlib.Path(a.source).resolve();out=pathlib.Path(a.output).resolve();out.mkdir(parents=True,exist_ok=False)
sys.path.insert(0,str(source/'tools'))
from gameplay_load_test import read_owned_statuses,read_audit_events
from gameplay_load_validation import new_events,aggregate_window,workload_snapshot,classify_stop
from pr13_runtime_evidence import reconcile_cycles
code=r'''import json,os,pathlib,sys,time
base=pathlib.Path(sys.argv[1]);fixture=sys.argv[2];now=int(time.time()*1000)
row=dict(client_id='boundary',pid=os.getpid(),run_id='boundary-run',process_epoch='boundary-epoch',status_seq=1,now_unix_ms=now,online=True,room=True,last_progress_age_ms=0)
event=dict(run_id=row['run_id'],client_id=row['client_id'],process_epoch=row['process_epoch'],event_seq=1,at_unix_ms=now,type='http',duration_ms=sys.float_info.max,status=500,ok=False,path='/fixture',phase='playing')
events=[event,dict(event,event_seq=2)]
if fixture!='finite-max-pair':
 event.update(type='lifecycle',duration_ms=2,event_type='cycle.started',cycle_id='boundary:1',match_id='M')
 if fixture=='match-dict':event['match_id']={}
 if fixture=='event-type-dict':event['event_type']={}
 if fixture=='optional-match-none':event['match_id']=None
 if fixture=='optional-match-empty':event['match_id']=''
 events=[event]
row.update(event_seq_max=len(events),telemetry=events,operations=events if fixture=='finite-max-pair' else [])
pathlib.Path(str(base)+'.telemetry.jsonl').write_text(''.join(json.dumps(e)+'\n' for e in events))
pathlib.Path(str(base)+'.status.json').write_text(json.dumps(row))
print(json.dumps(dict(pid=os.getpid(),written=True)),flush=True);time.sleep(15)
'''
records=[]
for fixture in ('finite-max-pair','match-dict','event-type-dict','optional-match-none','optional-match-empty'):
    d=out/fixture;d.mkdir();base=d/'client.json';argv=[sys.executable,'-c',code,str(base),fixture]
    wall=int(time.time()*1000);mono=time.monotonic()*1000;log=(d/'child.log').open('w');child=subprocess.Popen(argv,stdout=log,stderr=subprocess.STDOUT)
    r=dict(fixture=fixture,child_argv=argv,pid=child.pid,source_sha=subprocess.check_output(['git','rev-parse','HEAD'],cwd=source,text=True).strip(),started_at_ms=wall,started_at_monotonic_ms=mono,decision=None,stage='child_write')
    try:
        deadline=time.monotonic()+5
        while not (d/'child.log').read_text().strip():
            if time.monotonic()>deadline:raise TimeoutError('owned child write deadline')
            time.sleep(.01)
        entry=dict(client_id='boundary',process=child,report=base,run_id='boundary-run',process_epoch='boundary-epoch',started_at_ms=wall,started_at_monotonic_ms=mono)
        r['stage']='read_owned_statuses';rows,invalid=read_owned_statuses([entry],{},require_files=True)
        r['stage']='new_events';fresh,lost=new_events(rows,{})
        r['stage']='aggregate_window';window=aggregate_window(fresh)
        r['stage']='workload_snapshot';pop=workload_snapshot([entry],rows,int(time.time()*1000),now_monotonic_ms=time.monotonic()*1000)
        r['stage']='read_audit_events';events,archive_errors=read_audit_events([entry],rows)
        counts=None
        if fixture!='finite-max-pair':
            r['stage']='reconcile_cycles';counts=reconcile_cycles(events,int(time.time()*1000),int(time.time()*1000)+1)
        bad=bool(invalid or lost or window['invalid_metric_count'] or pop['invalid_schema_count'] or archive_errors or (counts and counts['evidence_errors']))
        decision=classify_stop('invalid_evidence:invalid_telemetry' if bad else 'duration_limit')
        checks=dict(owned=invalid==0 and len(rows)==1,sequence_intact=lost==0,archive_owned=not archive_errors)
        if fixture=='finite-max-pair':
            checks.update(mean_finite=window['http']['mean_ms']==sys.float_info.max,counts_preserved=window['sample_count']==window['error_count']==window['http']['count']==2,quality_insufficient=window['latency_sample_quality']['http']=='insufficient',not_invalid=window['invalid_metric_count']==0,not_load_pass=decision['exit_code']==1 and not decision['passed'])
        elif fixture in ('match-dict','event-type-dict'):
            error='invalid_business_match_type' if fixture=='match-dict' else 'invalid_event_type'
            checks.update(classified=error in counts['evidence_errors'],invalid_exit3=decision['exit_code']==3 and not decision['passed'],no_false_completion=counts['final']['completed_cycles']==counts['final']['acknowledgements']==0)
        else:
            checks.update(optional_compatible=counts['evidence_errors']==[],no_false_completion=counts['final']['completed_cycles']==counts['final']['acknowledgements']==0,not_load_pass=decision['exit_code']==1 and not decision['passed'])
        r.update(ownership_invalid=invalid,event_loss=lost,window=window,population=pop,archive_errors=archive_errors,cycle_counts=counts,decision=decision,checks=checks,unhandled_exception=None,status='Passed' if all(checks.values()) else 'Failed',stage='completed')
    except Exception as exc:r.update(status='Failed',unhandled_exception=type(exc).__name__,exception_message=str(exc),traceback=traceback.format_exc())
    finally:
        if child.poll() is None:child.terminate()
        r.update(child_exit_code=child.wait(timeout=5),child_reaped=True);log.close()
        (d/'receipt.json').write_text(json.dumps(r,indent=2,allow_nan=False)+'\n');records.append(r)
report=dict(records=records,passed=sum(r['status']=='Passed' for r in records),failed=sum(r['status']=='Failed' for r in records),all_reaped=all(r['child_reaped'] for r in records),Accepted=False)
(out/'REPORT.json').write_text(json.dumps(report,indent=2,allow_nan=False)+'\n');print(json.dumps({k:report[k] for k in ('passed','failed','all_reaped')}))
raise SystemExit(0 if report['failed']==0 and report['passed']==5 else 1)
