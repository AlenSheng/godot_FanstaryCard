"""Frozen-source LOAD-01 exact cases; no production patch or public network."""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(os.environ.get('PR13_SOURCE_ROOT', '/workspace/godot_FanstaryCard')).resolve()
sys.path.insert(0, str(ROOT / 'tools'))
import pr13_offline_cases as existing
from gameplay_load_validation import aggregate_window, workload_snapshot, owned_statuses, new_events
from gameplay_load_test import read_owned_statuses, read_audit_events
from pr13_runtime_evidence import reconcile_cycles

SHA = 'e06037f58738d0fbff86090e86d8bd06f8608e04'
PLAN = json.loads((ROOT / 'docs/plans/PR13_ACCEPTANCE_DETAILS_20260930.json').read_text())
TASKS = {t['id']: t for p in PLAN['packages'] for t in p['subtasks']}
CHILDREN = []


def checked(checks, actual):
    return dict(checks=checks, observations=actual), all(checks.values())


def ordinary(task, number):
    function = {'LOAD-01.1': existing.schema_cases,
                'LOAD-01.2': existing.ownership_cases,
                'LOAD-01.3': existing.population_cases}[task]
    actual, passed = function(number)
    checks = {'exact_existing_case_assertion': passed}
    if task == 'LOAD-01.1' and number == 1:
        checks.update(invalid_classified=all(r['invalid_schema_count'] == 1 for r in actual),
                      evidence_invalid=all(r['workload_failure'] for r in actual))
    if task == 'LOAD-01.1' and number == 2:
        p, w = actual['population'], actual['window']
        checks.update(bool_pid_classified=p['invalid_clients'] == ['a'] and p['workload_failure'],
                      nan_latency_excluded=w['valid_latency_count'] == 0,
                      nan_failure_retained=w['error_count'] == 1 and w['sample_count'] == 1,
                      invalid_duration_visible=w['invalid_duration_count'] == 1)
    if task == 'LOAD-01.1' and number == 3:
        checks.update(valid_row_retained=actual['sample_count'] == actual['valid_latency_count'] == 1,
                      malformed_row_visible=actual['invalid_schema_count'] == 1)
    if task == 'LOAD-01.2' and number == 3:
        checks.update(no_active_after_exit=actual['population']['alive_processes'] == 0,
                      legal_history_retained=actual['window']['sample_count'] == 1)
    if task == 'LOAD-01.3' and number == 1:
        checks.update(fresh_alive_offline=actual['alive_processes'] == actual['fresh_status_clients'] == 1,
                      retained_room_separate=actual['room_state_clients'] == 1,
                      offline_not_active=actual['online'] == actual['active_in_room'] == 0)
    if task == 'LOAD-01.3' and number == 3:
        checks.update(authority_unknown=actual['server_confirmed_in_room'] is None)
        actual['authority_unavailable_reason'] = 'No server authority source in this local process-accounting profile; client population is a separate field.'
    return checked(checks, actual)


def spawn(directory, delay, exit_code=None, lifecycle=False):
    report = directory / 'client.json'
    code = r'''import json,os,pathlib,sys,time
report=pathlib.Path(sys.argv[1]); time.sleep(float(sys.argv[2]))
row=dict(client_id='owned',pid=os.getpid(),run_id='frozen-run',process_epoch='epoch-A',status_seq=1,
 now_unix_ms=int(time.time()*1000),online=True,room=True,last_progress_age_ms=0,event_seq_max=1)
event=dict(run_id='frozen-run',client_id='owned',process_epoch='epoch-A',event_seq=1,type='http',
 at_unix_ms=row['now_unix_ms'],phase='playing',duration_ms=5,status=200,ok=True)
events=[event]
if sys.argv[4]=='lifecycle':
 events=[dict(event,type='lifecycle',event_type=kind,cycle_id='owned:1',match_id='M',event_seq=index)
  for index,kind in enumerate(['cycle.started','settlement.acknowledged','cycle.completed'],1)]
 row.update(event_seq_max=3,cycles_completed=1)
row.update(telemetry=events,operations=[] if sys.argv[4]=='lifecycle' else [event])
pathlib.Path(str(report)+'.telemetry.jsonl').write_text(''.join(json.dumps(e)+'\n' for e in events))
pathlib.Path(str(report)+'.status.json').write_text(json.dumps(row))
print(json.dumps(dict(pid=os.getpid(),status_written=True)),flush=True)
if sys.argv[3]!='none': raise SystemExit(int(sys.argv[3]))
time.sleep(15)
'''
    command = [sys.executable, '-c', code, str(report), str(delay), 'none' if exit_code is None else str(exit_code), 'lifecycle' if lifecycle else 'http']
    log = (directory / 'child.log').open('w')
    started_wall = int(time.time()*1000)
    started_monotonic = time.monotonic()*1000
    child = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT)
    info = dict(process=child, log=log, client_id='owned', report=report, run_id='frozen-run', process_epoch='epoch-A',
                started_at_ms=started_wall, started_at_monotonic_ms=started_monotonic)
    CHILDREN.append(info)
    (directory / 'command.json').write_text(json.dumps(dict(argv=command,pid=child.pid,started_wall_ms=started_wall,started_monotonic_ms=started_monotonic),indent=2))
    return info


def wait_status(info):
    deadline = time.monotonic()+5
    while not Path(str(info['report'])+'.status.json').exists():
        if time.monotonic()>deadline: raise TimeoutError('owned child status deadline')
        time.sleep(.01)


def successful_exit_tail(directory):
    info=spawn(directory,0,0,lifecycle=True);child=info['process'];code=child.wait(timeout=5)
    rows,invalid=read_owned_statuses([info],{})
    population=workload_snapshot([info],rows,int(time.time()*1000),now_monotonic_ms=time.monotonic()*1000)
    tail,lost=new_events(rows,{})
    events,errors=read_audit_events([info],rows)
    counts=reconcile_cycles(events,int(time.time()*1000),int(time.time()*1000)+1)
    actual=dict(pid=child.pid,exit_code=code,population=population,tail=tail,archive=events,
                archive_errors=errors,cycle_counts=counts,ownership_invalid=invalid,lost=lost)
    return checked(dict(real_successful_exit=code==0,no_online=population['online']==population['alive_processes']==0,
                        owned_tail_preserved=invalid==lost==0 and not errors and len(tail[0]['telemetry'])==3,
                        cumulative_cycle_preserved=counts['final']['completed_cycles']==counts['final']['acknowledgements']==1,
                        no_cycle_evidence_errors=not counts['evidence_errors']),actual)


def real_process(number, directory):
    info = spawn(directory, .15 if number == 1 else 0, 7 if number == 2 else None)
    child = info['process']; cache = {}
    observations = dict(pid=child.pid,actual_os_process=True)
    if number == 1:
        before = workload_snapshot([info], [], int(time.time()*1000), now_monotonic_ms=time.monotonic()*1000)
        wait_status(info)
        rows, invalid = read_owned_statuses([info], cache)
        after = workload_snapshot([info], rows, int(time.time()*1000), now_monotonic_ms=time.monotonic()*1000)
        observations.update(before=before,after=after,ownership_invalid=invalid)
        return checked(dict(slow_start_no_missing=not before['missing_clients'],
                            actual_child_status_adopted=after['online'] == 1 and invalid == 0),observations)
    wait_status(info)
    if number == 2:
        code = child.wait(timeout=5)
        rows, invalid = read_owned_statuses([info], cache)
        population = workload_snapshot([info], rows, int(time.time()*1000), now_monotonic_ms=time.monotonic()*1000)
        history, lost = new_events(rows,{})
        window = aggregate_window(history)
        archive, archive_errors = read_audit_events([info],rows)
        observations.update(exit_code=code,population=population,window=window,events=archive,archive_errors=archive_errors)
        return checked(dict(exit7_attributed=code==7 and population['failed_processes']==['owned'],
                            exited_not_online=population['online']==0,
                            owned_tail_preserved=invalid==lost==0 and not archive_errors and window['sample_count']==1),observations)
    rows, invalid = read_owned_statuses([info],cache)
    received = rows[0]['_received_at_monotonic_ms']
    # Only the accounting seam sees counterfactual clock values. Host clock is untouched.
    jumps = [0, info['started_at_ms']+1000000000]
    grace = [workload_snapshot([info],[],wall,now_monotonic_ms=info['started_at_monotonic_ms']+1000) for wall in jumps]
    stale_rows, stale_invalid = read_owned_statuses([info],cache,received+31001)
    stale = [workload_snapshot([info],stale_rows,wall,now_monotonic_ms=received+31001) for wall in jumps]
    reused = dict(info,process_epoch='epoch-B')
    rejected, wrong_epoch = owned_statuses([reused],rows)
    observations.update(clock_seam='Counterfactual wall jump and monotonic observation values; actual child files and actual process, no host clock mutation.',
                        wall_values=jumps,grace=grace,stale=stale,reused_epoch_rejected=wrong_epoch,
                        epoch_injection='Same actual PID under a new owner epoch; not a claimed kernel PID recycle.')
    return checked(dict(grace_uses_monotonic=all(not r['missing_clients'] for r in grace),
                        stale_no_online=all(r['stale_clients']==['owned'] and r['online']==0 for r in stale),
                        wrong_epoch_excluded=wrong_epoch==1 and not rejected,
                        status_read_valid=invalid==stale_invalid==0),observations)


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    out=args.output.resolve();out.mkdir(parents=True,exist_ok=True)
    assert subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()==SHA
    records=[]
    try:
        for task in [f'LOAD-01.{i}' for i in range(1,5)]:
            for number,case in enumerate(TASKS[task]['test_cases'],1):
                directory=out/case['id'];directory.mkdir(exist_ok=True)
                started=time.monotonic()
                try:
                    if task=='LOAD-01.4':actual,passed=real_process(number,directory)
                    elif task=='LOAD-01.2' and number==3:actual,passed=successful_exit_tail(directory)
                    else:actual,passed=ordinary(task,number)
                    record=dict(case_id=case['id'],setup=case['setup_and_injection'],expected=case['expected'],
                                pass_criteria=TASKS[task]['pass_criteria'],actual=actual,status='Passed' if passed else 'Failed')
                except Exception as error:
                    record=dict(case_id=case['id'],status='Failed',error=repr(error))
                record.update(source_sha=SHA,profile='OFFLINE',elapsed_seconds=time.monotonic()-started,Accepted=False)
                records.append(record)
    finally:
        cleanup=[]
        for info in CHILDREN:
            child=info['process'];running=child.poll() is None
            if running: child.terminate()
            child.wait(timeout=5);info['log'].close()
            cleanup.append(dict(pid=child.pid,alive_before_cleanup=running,exit_code=child.returncode,reaped=True))
        (out/'cleanup.json').write_text(json.dumps(dict(owned_children=cleanup,all_reaped=all(c['reaped'] for c in cleanup),no_nonowned_process_touched=True),indent=2))
    (out/'cases.jsonl').write_text(''.join(json.dumps(r,ensure_ascii=False,allow_nan=False)+'\n' for r in records))
    report=dict(source_sha=SHA,executed=len(records),passed=sum(r['status']=='Passed' for r in records),failed=sum(r['status']=='Failed' for r in records),skipped=0,Accepted=False)
    (out/'report.json').write_text(json.dumps(report,indent=2));print(json.dumps(report))
    return 0 if report['failed']==0 and report['executed']==12 else 1


if __name__=='__main__':raise SystemExit(main())
