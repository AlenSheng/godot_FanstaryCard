"""Prepare by default; --run starts real Godot gameplay with 50 clients/120s.
--smoke runs one client for one completed match, with a 7 minute deadline.
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
from cloud_load_test import ROOT, CLIENT, load_client_status, aggregate_recent, stop_all, health_probe

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
    run_dir=args.output.resolve()/(time.strftime('%Y%m%d-%H%M%S')+'-'+uuid.uuid4().hex[:6])
    run_dir.mkdir(parents=True)
    stop_file=run_dir/'STOP'
    processes=[]; samples=[]; streaks=collections.Counter(); seen={}
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
                    process=subprocess.Popen([args.godot,'--headless','--audio-driver','Dummy','--path',str(CLIENT),
                        'res://tests/gameplay_load_client.tscn'],cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT,
                        creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
                    processes.append({'process':process,'log':log,'client_id':client_id,'group':groups,'report':report})
                next_group=started+groups*120
                print('GROUP',groups,'clients',len(processes),flush=True)
            if now>=next_sample:
                statuses=load_client_status(run_dir)
                fresh=[]
                for s in statuses:
                    cid=s['client_id']; cutoff=seen.get(cid,0)
                    copy=dict(s)
                    for field in ('operations','telemetry'):
                        copy[field]=[x for x in s.get(field,[]) if x.get('at_unix_ms',0)>cutoff]
                    seen[cid]=s.get('now_unix_ms',cutoff)
                    fresh.append(copy)
                window=aggregate_recent(fresh,10**12)
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
                dead=[p for p in processes if p['process'].poll() is not None]
                failed=[p for p in dead if p['process'].returncode!=0]
                # A workload failure is distinct from a performance capacity result.
                stale=[s for s in statuses if int(time.time()*1000)-s.get('now_unix_ms',0)>30000]
                stalled=[s for s in statuses if s.get('last_progress_age_ms',0)>90000]
                missing=[p for p in processes if p['client_id'] not in seen and now-started-(p['group']-1)*120>30]
                if failed or stale or stalled or missing: causes.append('workload_or_generator_failure')
                for key in set(streaks)|set(causes): streaks[key]=streaks[key]+1 if key in causes else 0
                row={'at':time.time(),'groups':groups,'clients':len(processes),'online':sum(bool(s.get('online')) for s in statuses),
                    'in_room':sum(bool(s.get('room')) for s in statuses),'completed_cycles':sum(s.get('cycles_completed',0) for s in statuses),
                    'failed_processes':[p['client_id'] for p in failed],'window':window,'health':health,'resources':resource,'reasons':causes,'streaks':dict(streaks)}
                samples.append(row)
                save(run_dir/'state.json',row)
                with (run_dir/'samples.jsonl').open('a',encoding='utf-8') as f: f.write(json.dumps(row)+'\n')
                print('SAMPLE',json.dumps(row),flush=True)
                breached=[k for k,v in streaks.items() if v>=3]
                if breached: reason='redline:'+','.join(breached); break
                if args.smoke and len(dead)==1:
                    data=json.loads(processes[0]['report'].read_text()) if processes[0]['report'].exists() else {}
                    reason='smoke_passed' if data.get('ok') and data.get('cycles_completed',0)>=1 else 'smoke_failed'
                    break
                next_sample=time.time()+10
            if args.smoke and time.time()-started>420: reason='smoke_timeout'; break
            time.sleep(.25)
    except KeyboardInterrupt: reason='operator_interrupted'
    except Exception as exc:
        reason='coordinator_error:'+type(exc).__name__+':'+str(exc)
    finally:
        stop_all(processes,stop_file)
        for entry in processes: entry['log'].close()
        save(run_dir/'report.json',{'started':started,'ended':time.time(),'groups':groups,'clients':len(processes),
            'stop_reason':reason,'group_size':group_size,'interval_seconds':120,'scope':'real Godot Game store: login once, repeated preparation/match/PVE or PVP/settlement; no market trades',
            'samples':samples,'final_clients':load_client_status(run_dir)})
    print('STOP',reason,'REPORT',run_dir/'report.json',flush=True)
    return 0 if reason=='smoke_passed' or reason.startswith('redline:') or reason.startswith('operator_') else 1

if __name__=='__main__': raise SystemExit(main())
