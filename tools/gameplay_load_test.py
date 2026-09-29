"""Prepare by default; --run starts real Godot gameplay with 50 clients/120s.
--smoke runs one client for one completed match, with a 7 minute deadline.
Exit codes: 0 preparation-only or verified smoke; 1 incomplete; 2 performance
redline; 3 invalid workload/evidence; 130 operator stop. No rate-limit changes.
"""
from __future__ import annotations
import argparse
import collections
import json
import math
import os
from pathlib import Path
import subprocess
import time
import urllib.parse
import urllib.request
import uuid
from cloud_load_test import ROOT, CLIENT, load_client_status, stop_all, health_probe, read_json
from gameplay_load_validation import aggregate_window, workload_snapshot, classify_stop, provenance

QUERIES = {
    'cpu': '100*(1-avg(rate(node_cpu_seconds_total{mode="idle"}[1m])))',
    'memory_available': '100*node_memory_MemAvailable_bytes/node_memory_MemTotal_bytes',
    'disk_available': '100*node_filesystem_avail_bytes{mountpoint="/"}/node_filesystem_size_bytes{mountpoint="/"}',
    'actor_wait': 'histogram_quantile(0.95,sum(rate(fantasycard_room_actor_command_wait_milliseconds_bucket[5m])) by (le))',
}

def metrics(base):
    result = {}
    for key, query in QUERIES.items():
        try:
            with urllib.request.urlopen(base.rstrip('/')+'/api/v1/query?'+urllib.parse.urlencode({'query':query}),timeout=3) as r:
                rows=json.load(r)['data']['result']
            value=float(rows[0]['value'][1])
            result[key]=value if math.isfinite(value) else None
        except (OSError, ValueError, KeyError, IndexError): result[key]=None
    return result

def save(path, data):
    tmp=path.with_suffix(path.suffix+'.tmp')
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2),encoding='utf-8')
    tmp.replace(path)

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run',action='store_true')
    parser.add_argument('--smoke',action='store_true')
    parser.add_argument('--godot',default=r'F:\GitHubFiles\Godot_v4.7.2-stable_win64.exe\Godot_v4.7.2-stable_win64_console.exe')
    parser.add_argument('--server-url',default='https://www.relicbound.cn')
    parser.add_argument('--prometheus',default='http://127.0.0.1:19090')
    parser.add_argument('--output',type=Path,default=ROOT/'outputs'/'gameplay-load')
    args=parser.parse_args()
    if not Path(args.godot).is_file(): parser.error('Godot executable is missing')
    if not args.run and not args.smoke:
        print('Prepared: 50 real Godot clients every 120 seconds, no group/runtime limit. Use --smoke to validate one complete match; --run requires Prometheus monitoring.')
        return 0
    if args.run and args.smoke: parser.error('Choose --smoke or --run')
    if args.run:
        baseline=metrics(args.prometheus)
        if any(baseline[k] is None for k in ('cpu','memory_available','disk_available')):
            parser.error('Host monitoring is unavailable; open the SSH Prometheus tunnel before --run')
    source=provenance(ROOT, ('tools/gameplay_load_test.py','tools/cloud_load_test.py',
        'tools/gameplay_load_validation.py','client/tests/gameplay_load_client.gd','client/network/gateway.gd'))
    run_dir=args.output.resolve()/(time.strftime('%Y%m%d-%H%M%S')+'-'+uuid.uuid4().hex[:6])
    run_dir.mkdir(parents=True)
    stop_file=run_dir/'STOP'
    processes=[]; samples=[]; streaks=collections.Counter(); seen={}
    workload_failed=False; smoke_verified=False; previous_sample_ms=None
    started=time.time(); next_group=started; next_sample=started+10; groups=0; reason='running'
    group_size=1 if args.smoke else 50
    try:
        while True:
            now=time.time()
            if stop_file.exists(): reason='operator_stop_file'; break
            if now>=next_group and (not args.smoke or groups==0):
                groups+=1
                for index in range(group_size):
                    client_id='g%03dc%02d%s'%(groups,index+1,uuid.uuid4().hex[:6])
                    report=run_dir/(client_id+'.json')
                    env=dict(os.environ,FANTASYCARD_SERVER_URL=args.server_url,FANTASYCARD_LOAD_CLIENT_ID=client_id,
                        FANTASYCARD_LOAD_GROUP=str(groups),FANTASYCARD_LOAD_REPORT=str(report),
                        FANTASYCARD_LOAD_STOP_FILE=str(stop_file),FANTASYCARD_LOAD_MAX_CYCLES='1' if args.smoke else '0')
                    log=(run_dir/(client_id+'.log')).open('w',encoding='utf-8')
                    try:
                        process=subprocess.Popen([args.godot,'--headless','--audio-driver','Dummy','--path',str(CLIENT),
                            'res://tests/gameplay_load_client.tscn'],cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT,
                            creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
                    except Exception:
                        log.close()
                        raise
                    processes.append({'process':process,'log':log,'client_id':client_id,'group':groups,
                        'report':report,'started_at_ms':int(time.time()*1000)})
                next_group=started+groups*120
                print('GROUP',groups,'clients',len(processes),flush=True)
            if now>=next_sample:
                sample_started=time.monotonic()
                statuses=load_client_status(run_dir)
                sample_ms=int(time.time()*1000)
                workload=workload_snapshot(processes,statuses,sample_ms)
                workload_failed=workload_failed or workload['workload_failure']
                fresh=[]
                for s in statuses:
                    cid=s['client_id']; cutoff=seen.get(cid,0)
                    copy=dict(s)
                    for field in ('operations','telemetry'):
                        copy[field]=[x for x in s.get(field,[]) if x.get('at_unix_ms',0)>cutoff]
                    seen[cid]=s.get('now_unix_ms',cutoff)
                    fresh.append(copy)
                window=aggregate_window(fresh)
                commands=[t for s in fresh for t in s.get('telemetry',[]) if t.get('type')=='realtime']
                rejected=[t for t in commands if t.get('response_type')=='error.command_rejected']
                window['command_rejections']=len(rejected)
                window['command_error_rate']=len(rejected)/len(commands) if commands else 0
                health=health_probe(args.server_url)
                resource=metrics(args.prometheus) if args.run else {}
                causes=[]
                if len(commands)>=10 and window['command_error_rate']>=.1: causes.append('command_rejections_10pct')
                if not health['ok'] or health['duration_ms']>5000: causes.append('health_failed_or_over_5000ms')
                if window['sample_count']>=20 and window['error_rate']>=.1: causes.append('http_errors_10pct')
                if window['sample_count']>=20 and window['http'].get('p95_ms',0)>1500: causes.append('http_p95_over_1500ms')
                if window['realtime'].get('count',0)>=10 and window['realtime'].get('p95_ms',0)>2000: causes.append('command_p95_over_2000ms')
                for key,limit,less in [('cpu',85,False),('memory_available',15,True),('disk_available',15,True),('actor_wait',100,False)]:
                    value=resource.get(key)
                    if value is not None and (value<limit if less else value>limit): causes.append(key+'_redline')
                if args.run and any(resource.get(k) is None for k in ('cpu','memory_available','disk_available')): causes.append('monitoring_unavailable')
                if window['invalid_metric_count']:
                    causes.append('invalid_telemetry'); workload_failed=True
                if workload['workload_failure']: causes.append('workload_or_generator_failure')
                for key in set(streaks)|set(causes): streaks[key]=streaks[key]+1 if key in causes else 0
                row={'at':sample_ms/1000,'groups':groups,'clients':len(processes),**workload,
                    'completed_cycles':sum(s.get('cycles_completed',0) for s in statuses),
                    'observed_interval_seconds':None if previous_sample_ms is None else (sample_ms-previous_sample_ms)/1000,
                    'sample_collection_ms':round((time.monotonic()-sample_started)*1000,2),
                    'window':window,'health':health,'resources':resource,'reasons':causes,'streaks':dict(streaks)}
                previous_sample_ms=sample_ms
                samples.append(row)
                save(run_dir/'state.json',row)
                with (run_dir/'samples.jsonl').open('a',encoding='utf-8') as f: f.write(json.dumps(row)+'\n')
                print('SAMPLE',json.dumps(row),flush=True)
                breached=[k for k,v in streaks.items() if v>=3]
                if breached: reason='redline:'+','.join(breached); break
                if args.smoke and len(processes)==1 and processes[0]['process'].poll() is not None:
                    data=read_json(processes[0]['report']) or {}
                    smoke_verified=processes[0]['process'].returncode==0 and data.get('ok') is True and data.get('cycles_completed',0)>=1
                    reason='smoke_passed' if smoke_verified else 'smoke_failed'
                    break
                next_sample=time.time()+10
            if args.smoke and time.time()-started>420: reason='smoke_timeout'; break
            time.sleep(.25)
    except KeyboardInterrupt: reason='operator_interrupted'
    except Exception as exc:
        reason='coordinator_error:'+type(exc).__name__+':'+str(exc)
    finally:
        before_stop={p['client_id']:p['process'].poll() for p in processes}
        # A process that failed before STOP is not an intentional shutdown.
        workload_failed=workload_failed or any(code not in (None,0) for code in before_stop.values())
        cleanup_error=None
        try:
            stop_all(processes,stop_file)
        except Exception as exc:
            cleanup_error=type(exc).__name__+':'+str(exc)
            workload_failed=True
        finally:
            for entry in processes: entry['log'].close()
        outcome=classify_stop(reason,smoke_verified=smoke_verified,workload_failed=workload_failed)
        save(run_dir/'report.json',{'schema_version':2,'started':started,'ended':time.time(),'groups':groups,'clients':len(processes),
            'stop_reason':reason,'outcome':outcome,'source':source,'cleanup_error':cleanup_error,
            'process_exits':[{'client_id':p['client_id'],'before_stop':before_stop[p['client_id']],
                'after_stop':p['process'].poll()} for p in processes],
            'group_size':group_size,'interval_seconds':120,'scope':'real Godot Game store: login once, repeated preparation/match/PVE or PVP/settlement; no market trades',
            'samples':samples,'final_clients':load_client_status(run_dir)})
    print('STOP',reason,'OUTCOME',outcome,'REPORT',run_dir/'report.json',flush=True)
    return outcome['exit_code']

if __name__=='__main__': raise SystemExit(main())
