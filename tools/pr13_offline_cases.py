"""Execute explicitly implemented PR13 cases; unimplemented cases stay unexecuted."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import subprocess
import sys
import time

from gameplay_load_validation import aggregate_window, owned_statuses, workload_snapshot, new_events, classify_stop
from gameplay_load_validation import provenance
from pr13_runtime_evidence import result_dimensions

ROOT = Path(__file__).resolve().parents[1]
ENGINE = ROOT.parent/'Godot_v4.7.2-stable_win64.exe'/'Godot_v4.7.2-stable_win64.exe'


class Process:
    def __init__(self, pid=7, code=None): self.pid, self.code = pid, code
    def poll(self): return self.code


def entry(code=None):
    return dict(client_id='a', process=Process(code=code), started_at_ms=9900, run_id='run', process_epoch='epoch')


def status(**changes):
    return dict(dict(client_id='a', pid=7, now_unix_ms=10000, online=True, room=True,
                     last_progress_age_ms=0, run_id='run', process_epoch='epoch'), **changes)


def event(seq, epoch='epoch', kind='http', **changes):
    return dict(dict(run_id='run', client_id='a', process_epoch=epoch, event_seq=seq,
                     at_unix_ms=10000, type=kind, duration_ms=5, status=200, ok=True), **changes)


def events_status(rows, epoch='epoch'):
    return dict(client_id='a', run_id='run', process_epoch=epoch,
                event_seq_max=max(row['event_seq'] for row in rows), telemetry=rows,
                operations=[row for row in rows if row['type']=='http'])


def schema_cases(which):
    if which==1:
        results=[workload_snapshot([entry()],[bad],10000) for bad in (None,[])]
        return results,all(row['invalid_schema_count']>0 and row['online']==0 for row in results)
    if which==2:
        population=workload_snapshot([entry()],[status(pid=True)],10000)
        window=aggregate_window([{'operations':[event(1,duration_ms=math.nan,status=500,ok=False)]}])
        return dict(population=population,window=window),population['online']==0 and window['error_count']==1 and window['sample_count']==1
    result=aggregate_window([{'operations':[event(1),None]}])
    return result,result['sample_count']==1 and result['invalid_metric_count']>0


def ownership_cases(which):
    process=entry(0 if which==3 else None)
    rows=[status()] if which!=2 else [status(process_epoch='another'),status(run_id='external')]
    owned,invalid=owned_statuses([process],rows)
    population=workload_snapshot([process],owned,10000)
    window=aggregate_window([{'operations':[event(1)]}] if owned else [])
    result=dict(owned=owned,invalid=invalid,population=population,window=window)
    passed=(population['online']==1 and window['sample_count']==1) if which==1 else (
        invalid==2 and not owned and population['online']==0 if which==2 else population['online']==0 and window['sample_count']==1)
    return result,passed


def population_cases(which):
    result=workload_snapshot([entry(0 if which==2 else None)],[status(online=which!=1)],10000)
    return result, result['room_state_clients']==1 and result['active_in_room']==0 if which==1 else (
        result['online']==0 if which==2 else result['server_confirmed_in_room'] is None and result['online']==1)


def real_process_case(which):
    child=subprocess.Popen([sys.executable,'-c','import time; time.sleep(5)' if which==1 else 'raise SystemExit(7)'])
    try:
        if which==2: child.wait(timeout=5)
        now=int(time.time()*1000)
        result=workload_snapshot([dict(client_id='owned-child',process=child,started_at_ms=now)],[],now)
        return result,not result['missing_clients'] if which==1 else result['failed_processes']==['owned-child']
    finally:
        if child.poll() is None: child.terminate(); child.wait(timeout=5)


def sequence_case(which):
    seen={}
    rows=[event(1),event(3 if which==2 else 2)]
    first,lost=new_events([events_status(rows)],seen)
    if which==3:
        other,other_lost=new_events([events_status([event(1,epoch='new')],epoch='new')],seen)
        return dict(seen={str(k):v for k,v in seen.items()},lost=lost,other_lost=other_lost),len(seen)==2 and other_lost==0
    second,second_lost=new_events([events_status(rows)],seen)
    result=dict(first=first,second=second,lost=lost,second_lost=second_lost)
    return result,lost==1 if which==2 else lost==0 and len(first[0]['operations'])==2 and not second[0]['operations']


def phase_case(which):
    row=event(1,path='/api/v1/bootstrap',**({'phase':'playing'} if which==1 else {'phase':'settlement'} if which==2 else {}))
    result=aggregate_window([{'operations':[row]}])
    key='playing' if which==1 else 'settlement' if which==2 else 'unknown/legacy'
    return result,result['phase_http'].get(key,{}).get('count')==1 and result['steady_sample_count']==0


def request_case(which):
    if which==1:
        result=aggregate_window([{'operations':[event(1)],'telemetry':[event(2,kind='http_attempt'),event(3,kind='http_attempt')]}])
        return result,result['logical_request_count']==1 and result['all_attempt_count']==2
    if which==2:
        result=aggregate_window([{'operations':[event(1,status=500,ok=False,duration_ms=math.nan)]}])
        return result,result['error_count']==1 and result['sample_count']==1 and result['invalid_duration_count']==1
    result=aggregate_window([{'operations':[event(1)],'telemetry':[event(1)]}])
    return result,result['logical_request_count']==1


def statistics_case(which):
    if which==1:
        result=aggregate_window([{'operations':[event(1,duration_ms=100)]},
                                 {'operations':[event(i,duration_ms=5) for i in range(2,21)]}])
        return result,result['http']['count']==20 and result['http']['p95_ms']==5
    if which==2:
        results=[aggregate_window([{'operations':[event(i) for i in range(1,n+1)]}]) for n in [0,19]]
        return results,[r['latency_sample_quality']['http'] for r in results]==['unavailable','insufficient']
    result=aggregate_window([{'operations':[event(1,status=500,ok=False),event(2),event(3,result='cancelled',status=0,ok=False)]}])
    return result,result['error_count']==1 and result['sample_count']==2 and result['error_rate']==.5 and result['cancelled_count']==1


def preparation_case():
    engine=ENGINE
    if not engine.is_file(): raise RuntimeError('This case needs the explicitly installed local Godot executable')
    command=[sys.executable,str(ROOT/'tools/gameplay_load_test.py'),'--godot',str(engine)]
    run=subprocess.run(command,capture_output=True,text=True,timeout=10)
    result=dict(command=command,exit_code=run.returncode,stdout=run.stdout,stderr=run.stderr)
    return result,run.returncode==0 and run.stdout.startswith('Prepared:')


def main():
    global ENGINE
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--godot',type=Path)
    args=parser.parse_args(); output=args.output.resolve();output.mkdir(parents=True,exist_ok=True)
    if args.godot: ENGINE=args.godot.resolve()
    plan_path=ROOT/'docs/plans/PR13_ACCEPTANCE_DETAILS_20260930.json'
    plan=json.loads(plan_path.read_text(encoding='utf8'))
    cases={c['id']:c for p in plan['packages'] for s in p['subtasks'] for c in s['test_cases']}
    actions={}
    for task,function in [('LOAD-01.1',schema_cases),('LOAD-01.2',ownership_cases),('LOAD-01.3',population_cases),
                          ('LOAD-03.1',sequence_case),('LOAD-03.2',phase_case),('LOAD-03.3',request_case),('LOAD-03.4',statistics_case)]:
        for index in range(1,4): actions[f'{task}-T0{index}']=lambda fn=function,n=index:fn(n)
    for index in [1,2]: actions[f'LOAD-01.4-T0{index}']=lambda n=index:real_process_case(n)
    actions['LOAD-02.4-T01']=preparation_case
    actions['LOAD-02.4-T03']=lambda:({'invalid':classify_stop('invalid_evidence:bad'),'operator':classify_stop('operator_stop_file')},
        classify_stop('invalid_evidence:bad')['exit_code']==3 and classify_stop('operator_stop_file')['exit_code']==130)
    actions['LOAD-02.1-T01']=lambda:(result_dimensions(execution=True,evidence=True,load=False,gameplay=None,performance=None,cleanup=None),
        classify_stop('duration_limit')['passed'] is False)
    records=[]
    for case_id,action in actions.items():
        record=dict(case_id=case_id,executed=True,setup=cases[case_id]['setup_and_injection'],expected=cases[case_id]['expected'],started_at=time.time())
        try:
            actual,passed=action();record.update(actual=actual,status='Passed' if passed else 'Failed')
        except Exception as error:record.update(status='Failed',error=repr(error))
        record['elapsed_seconds']=time.time()-record['started_at'];records.append(record)
    (output/'cases.jsonl').write_text(''.join(json.dumps(r,ensure_ascii=False,allow_nan=False)+'\n' for r in records),encoding='utf8')
    sha=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    report=dict(source_sha=sha,source=provenance(ROOT,('tools/pr13_offline_cases.py','tools/gameplay_load_validation.py','tools/pr13_runtime_evidence.py','tools/gameplay_load_test.py')),
        python=sys.version,scope='explicit offline cases only',plan_sha256=hashlib.sha256(plan_path.read_bytes()).hexdigest(),
        case_runner_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),executed=len(records),passed=sum(r['status']=='Passed' for r in records),
        unexecuted_case_ids=sorted(set(cases)-set(actions)),all_cases_accepted=False)
    (output/'report.json').write_text(json.dumps(report,indent=2),encoding='utf8')
    print(json.dumps({k:v for k,v in report.items() if k!='unexecuted_case_ids'}))
    return 0 if report['passed']==report['executed'] else 1


if __name__=='__main__':raise SystemExit(main())
