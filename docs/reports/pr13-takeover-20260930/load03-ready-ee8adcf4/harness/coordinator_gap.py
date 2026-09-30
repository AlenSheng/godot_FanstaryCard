"""Frozen coordinator main with model telemetry/clock and REAL owned subprocesses.

This is a verdict/lifecycle fixture, never a service capacity or gameplay proof.
Production coordinator, stop_all, sampling, aggregate and finalizer remain unedited.
"""
import json
import os
from pathlib import Path
import subprocess
import sys
import time as real_time
from types import SimpleNamespace
from unittest.mock import patch

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE / 'source/tools'))
import gameplay_load_test as coordinator

mode = sys.argv[1]
output = Path(sys.argv[2]).resolve()
output.mkdir(parents=True, exist_ok=True)
elapsed = [0.0]
entries = []
real_popen = subprocess.Popen
production_stop = coordinator.stop_all
production_save = coordinator.save

def write_status(entry):
    status = entry['status']
    entry['report'].write_text(json.dumps(dict(status, ok=True)), encoding='utf8')
    Path(str(entry['report'])+'.status.json').write_text(json.dumps(status), encoding='utf8')
    Path(str(entry['report'])+'.telemetry.jsonl').write_text(''.join(json.dumps(e)+'\n' for e in status['telemetry']), encoding='utf8')

def launch(argv, *, env, **kwargs):
    report = Path(env['FANTASYCARD_LOAD_REPORT'])
    behavior = 'immediate' if mode in ('smoke_complete','emergency') else mode
    cmd = [sys.executable, '-c',
        'import pathlib,sys,time,os,json\n'
        'stop=pathlib.Path(sys.argv[1]); mode=sys.argv[2]\n'
        'print(json.dumps({"pid":os.getpid(),"mode":mode,"actual_child":True}),flush=True)\n'
        'if mode=="immediate": raise SystemExit(0)\n'
        'while mode=="hang" or not stop.exists(): time.sleep(.005)\n'
        'print("STOP observed",flush=True)\n'
        'raise SystemExit(7 if mode=="exit7" else 0)\n',
        env['FANTASYCARD_LOAD_STOP_FILE'], behavior]
    child = real_popen(cmd, cwd=kwargs['cwd'], env=env, stdout=kwargs['stdout'], stderr=kwargs['stderr'])
    context = dict(run_id=env['FANTASYCARD_LOAD_RUN_ID'],client_id=env['FANTASYCARD_LOAD_CLIENT_ID'],process_epoch=env['FANTASYCARD_LOAD_PROCESS_EPOCH'])
    completed = 0 if mode in ('timeout_before','operator_wait') else 3
    events = [dict(context,event_seq=n,at_unix_ms=100000000+n,type='lifecycle',cycle_id=f'cycle:{(n+1)//2}',match_id=f'match:{(n+1)//2}',event_type='settlement.acknowledged' if n%2 else 'cycle.completed') for n in range(1, completed*2+1)]
    errors = []
    if mode == 'timeout_before':
        events = [dict(context,event_seq=1,at_unix_ms=100005000,type='http',event_type='http',cycle_id='cycle:1',match_id='',logical_request_id='timeout-before-stop',route='/fixture/pre-stop',path='/fixture/pre-stop',phase='match',ok=False,status=0,result='timeout',duration_ms=5000),dict(context,event_seq=2,at_unix_ms=100005001,type='lifecycle',event_type='cycle.failed',cycle_id='cycle:1',match_id='',reason='timeout_before_STOP')]
        errors = [{'message':'timeout before STOP','at_unix_ms':100005000}]
    if mode == 'gap_sticky':
        events = [dict(context,event_seq=n,at_unix_ms=100000000+n,type='realtime',event_type='realtime',cycle_id='cycle:1',match_id='',duration_ms=1) for n in [1,3]]
        completed = 0
    if mode == 'operator_wait':
        events = [dict(context,event_seq=1,at_unix_ms=100000001,type='lifecycle',event_type='cycle.started',cycle_id='cycle:1',match_id='')]
    status = dict(context,pid=child.pid,status_seq=1,now_unix_ms=100000000,online=False,room=False,last_progress_age_ms=0,cycles_completed=completed,event_seq_max=len(events),telemetry=events,operations=[e for e in events if e['type']=='http'],audit_lost_count=1 if mode=='invalid' else 0,errors=errors,cleanup={'state':'Unknown' if mode=='cleanup_unknown' else 'Passed'})
    entry = dict(report=report,status=status,child=child,stop=Path(env['FANTASYCARD_LOAD_STOP_FILE']))
    entries.append(entry)
    write_status(entry)
    (output/'owned-launch.json').write_text(json.dumps({'production_argv':argv,'fixture_child_command':cmd,'owned_pid':child.pid,'model_telemetry':True,'model_clock':True,'model_metrics':True,'capacity_claim':False},indent=2))
    real_time.sleep(.03)
    return child

def sleep(seconds):
    elapsed[0] += seconds
    real_time.sleep(.002)
    if mode in ('timeout_before','operator_wait','operator') and elapsed[0] >= 11:
        for entry in entries: entry['stop'].touch()

clock = SimpleNamespace(time=lambda:100000+elapsed[0],monotonic=lambda:elapsed[0],monotonic_ns=lambda:int(elapsed[0]*1e9),sleep=sleep,strftime=real_time.strftime)

def stop(processes, stop_file):
    started = real_time.monotonic()
    for entry in entries:
        status = entry['status']
        if mode == 'operator_wait':
            status['telemetry'].append(dict(run_id=status['run_id'],client_id=status['client_id'],process_epoch=status['process_epoch'],event_seq=2,at_unix_ms=int((100000+elapsed[0])*1000)+1,type='lifecycle',event_type='cycle.cancelled',cycle_id='cycle:1',match_id='',reason='operator_stop'))
            status['event_seq_max']=2; status['status_seq']+=1
        if mode == 'gap_sticky':
            saved_audit = Path(str(entry['report'])+'.telemetry.jsonl').read_text()
            c={k:status[k] for k in ('run_id','client_id','process_epoch')}
            status['telemetry']=[dict(c,event_seq=n,at_unix_ms=100000000+n,type='realtime',event_type='realtime',cycle_id='cycle:1',match_id='',duration_ms=1) for n in [1,2,3,4]]
            status['event_seq_max']=4; status['status_seq']+=1
            write_status(entry)
            Path(str(entry['report'])+'.telemetry.jsonl').write_text(saved_audit+json.dumps(status['telemetry'][-1])+'\n')
        if mode == 'redline_corrupt': status['audit_lost_count']=1; status['status_seq']+=1
        if mode == 'late_business_error': status['errors']=[{'message':'late unexpected write failure'}]; status['status_seq']+=1
        if mode != 'gap_sticky': write_status(entry)
    # Keep the production 35-second grace unchanged, and use real monotonic time.
    forced = production_stop(processes, stop_file)
    (output/'cleanup-real-time.json').write_text(json.dumps({'grace_seconds':35,'real_elapsed_seconds':real_time.monotonic()-started,'forced_pids':forced,'children':[{'pid':p['process'].pid,'returncode':p['process'].poll()} for p in processes]},indent=2))
    return forced

def save(path, data):
    if mode=='emergency' and path.name=='report.json': raise OSError('isolated injected final report write failure')
    return production_save(path,data)

run = mode in ('time_limit','redline','redline_corrupt')
argv=['gameplay_load_test.py','--run' if run else '--smoke','--godot',sys.executable,'--max-seconds','45' if mode.startswith('redline') else '20','--max-groups','1','--group-size','1','--output',str(output/'runs')]
resources = {'cpu':90,'memory_available':10,'disk_available':10,'actor_wait':150,'server_humans_in_room':0} if mode.startswith('redline') else {'cpu':1,'memory_available':80,'disk_available':80,'actor_wait':0,'server_humans_in_room':0}
with patch.object(sys,'argv',argv), patch.object(coordinator,'time',clock), patch.object(coordinator,'subprocess',SimpleNamespace(Popen=launch,STDOUT=subprocess.STDOUT,SubprocessError=subprocess.SubprocessError)), patch.object(coordinator,'health_probe',return_value={'ok':True,'duration_ms':1,'status':200}), patch.object(coordinator,'metrics',return_value=resources), patch.object(coordinator,'generator_resources',return_value=({},None)), patch.object(coordinator,'stop_all',side_effect=stop), patch.object(coordinator,'save',side_effect=save):
    code=coordinator.main()
raise SystemExit(code)
