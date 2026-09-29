"""Prepare by default; --run starts real Godot gameplay with 50 clients/120s.
--smoke runs one client for one completed match, with a 7 minute deadline.
Exit codes: 0 preparation-only or verified bounded run; 1 incomplete; 2 performance
redline; 3 invalid workload/evidence; 130 operator stop. No rate-limit changes.
"""
from __future__ import annotations
import argparse
import collections
import concurrent.futures
import json
import math
import os
from pathlib import Path
import subprocess
import time
import urllib.parse
import urllib.request
import uuid
try:
    import psutil
except ImportError:
    psutil = None
from cloud_load_test import ROOT, CLIENT, stop_all, health_probe, read_json
from gameplay_load_validation import aggregate_window, workload_snapshot, owned_statuses, new_events, classify_stop, provenance

QUERIES = {
    'cpu': '100*(1-avg(rate(node_cpu_seconds_total{job="node",instance="node-exporter:9100",mode="idle"}[1m])))',
    'memory_available': '100*node_memory_MemAvailable_bytes{job="node",instance="node-exporter:9100"}/node_memory_MemTotal_bytes{job="node",instance="node-exporter:9100"}',
    'disk_available': '100*node_filesystem_avail_bytes{job="node",instance="node-exporter:9100",mountpoint="/"}/node_filesystem_size_bytes{job="node",instance="node-exporter:9100",mountpoint="/"}',
    'actor_wait': 'histogram_quantile(0.95,sum(rate(fantasycard_room_actor_command_wait_milliseconds_bucket{job="fantasycard",instance="otel-collector:9464"}[5m])) by (le))',
}

def metrics(base):
    result = {}
    for key, query in QUERIES.items():
        try:
            with urllib.request.urlopen(base.rstrip('/')+'/api/v1/query?'+urllib.parse.urlencode({'query':query}),timeout=3) as r:
                rows=json.load(r)['data']['result']
            if len(rows)!=1:
                result[key]=None
                continue
            value=float(rows[0]['value'][1])
            result[key]=value if math.isfinite(value) else None
        except (OSError, ValueError, KeyError, IndexError): result[key]=None
    return result

def save(path, data):
    tmp=path.with_suffix(path.suffix+'.tmp')
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2),encoding='utf-8')
    tmp.replace(path)


def read_owned_statuses(processes):
    statuses = []
    invalid_files = 0
    for entry in processes:
        path = Path(str(entry['report']) + '.status.json')
        if not path.exists():
            continue
        value = read_json(path)
        if value is None:
            invalid_files += 1
        else:
            statuses.append(value)
    owned, invalid_ownership = owned_statuses(processes, statuses)
    return owned, invalid_files + invalid_ownership


def generator_resources(processes, previous):
    if psutil is None:
        return {'available':False,'reason':'psutil_missing'}, previous
    now=time.monotonic()
    cpu_by_pid={}; rss_bytes=0; threads=0; handles=0; write_bytes=0; measured=0
    for pid in [os.getpid()]+[entry['process'].pid for entry in processes if entry['process'].poll() is None]:
        try:
            process=psutil.Process(pid)
            times=process.cpu_times()
            cpu_by_pid[pid]=times.user+times.system
            rss_bytes+=process.memory_info().rss
            threads+=process.num_threads()
            if hasattr(process,'num_handles'): handles+=process.num_handles()
            if hasattr(process,'io_counters'): write_bytes+=process.io_counters().write_bytes
            measured+=1
        except (psutil.NoSuchProcess,psutil.AccessDenied,OSError):
            continue
    cpu_delta=sum(max(0.0, seconds-previous[1][pid]) for pid,seconds in cpu_by_pid.items() if previous is not None and pid in previous[1])
    cpu_percent=None if previous is None or now<=previous[0] else round(100*cpu_delta/(now-previous[0]),2)
    result={'available':True,'measured_processes':measured,'cpu_percent_of_one_core':cpu_percent,
            'logical_cores':psutil.cpu_count(logical=True),'rss_bytes':rss_bytes,
            'host_memory_available_bytes':psutil.virtual_memory().available,
            'threads':threads,'handles':handles if os.name=='nt' else None,'write_bytes_cumulative':write_bytes}
    return result,(now,cpu_by_pid)

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run',action='store_true')
    parser.add_argument('--smoke',action='store_true')
    # On Windows the small *_console.exe is a launcher with a different PID
    # from the engine process. Own the actual engine PID for status validation.
    parser.add_argument('--godot',default=r'F:\GitHubFiles\Godot_v4.7.2-stable_win64.exe\Godot_v4.7.2-stable_win64.exe')
    parser.add_argument('--server-url',default='http://127.0.0.1:5000')
    parser.add_argument('--allow-public-target',action='store_true')
    parser.add_argument('--max-groups',type=int,default=2)
    parser.add_argument('--max-seconds',type=int,default=1800)
    parser.add_argument('--group-size',type=int,default=50)
    parser.add_argument('--group-interval',type=int,default=120)
    parser.add_argument('--smoke-cycles',type=int,default=3)
    parser.add_argument('--prometheus',default='http://127.0.0.1:19090')
    parser.add_argument('--output',type=Path,default=ROOT/'outputs'/'gameplay-load')
    args=parser.parse_args()
    if not Path(args.godot).is_file(): parser.error('Godot executable is missing')
    if min(args.max_groups,args.max_seconds,args.group_size,args.group_interval,args.smoke_cycles)<1:
        parser.error('Group, duration and cycle limits must be positive')
    target=urllib.parse.urlparse(args.server_url)
    if target.scheme not in ('http','https') or not target.hostname:
        parser.error('A valid --server-url is required')
    if target.hostname not in ('127.0.0.1','localhost','::1') and not args.allow_public_target:
        parser.error('Public targets require --allow-public-target and an explicit --server-url')
    if not args.run and not args.smoke:
        print('Prepared: bounded local run; --smoke validates three cycles by default. --run requires monitoring.')
        return 0
    if args.run and args.smoke: parser.error('Choose --smoke or --run')
    if args.run:
        baseline=metrics(args.prometheus)
        if any(baseline[k] is None for k in ('cpu','memory_available','disk_available')):
            parser.error('Host monitoring is unavailable; open the SSH Prometheus tunnel before --run')
    source=provenance(ROOT, ('tools/gameplay_load_test.py','tools/cloud_load_test.py',
        'tools/gameplay_load_validation.py','client/tests/gameplay_load_client.gd','client/state/game_store.gd',
        'client/network/gateway.gd','protocol/realtime/v1/realtime.proto'))
    run_dir=args.output.resolve()/(time.strftime('%Y%m%d-%H%M%S')+'-'+uuid.uuid4().hex[:6])
    run_dir.mkdir(parents=True)
    stop_file=run_dir/'STOP'
    processes=[]; samples=[]; group_launches=[]; streaks=collections.Counter(); seen={}
    run_id=uuid.uuid4().hex
    workload_failed=False; smoke_verified=False; previous_sample_ms=None; previous_generator=None
    started=time.time(); started_monotonic=time.monotonic()
    next_group=started_monotonic; next_sample=started_monotonic+10
    groups=0; reason='running'
    group_size=1 if args.smoke else args.group_size
    probes=concurrent.futures.ThreadPoolExecutor(max_workers=2,thread_name_prefix='load-probe')
    try:
        while True:
            now=time.monotonic()
            if stop_file.exists(): reason='operator_stop_file'; break
            if now-started_monotonic>=args.max_seconds: reason='duration_limit'; break
            if now>=next_group and groups<(1 if args.smoke else args.max_groups):
                scheduled_group_at=next_group
                group_started_at=time.time()
                groups+=1
                for index in range(group_size):
                    client_id='g%03dc%02d%s'%(groups,index+1,uuid.uuid4().hex[:6])
                    process_epoch=uuid.uuid4().hex
                    report=run_dir/(client_id+'.json')
                    env=dict(os.environ,FANTASYCARD_SERVER_URL=args.server_url,FANTASYCARD_LOAD_CLIENT_ID=client_id,
                        FANTASYCARD_LOAD_GROUP=str(groups),FANTASYCARD_LOAD_REPORT=str(report),
                        FANTASYCARD_LOAD_STOP_FILE=str(stop_file),FANTASYCARD_LOAD_RUN_ID=run_id,
                        FANTASYCARD_LOAD_PROCESS_EPOCH=process_epoch,
                        FANTASYCARD_LOAD_MAX_CYCLES=str(args.smoke_cycles) if args.smoke else '0')
                    log=(run_dir/(client_id+'.log')).open('w',encoding='utf-8')
                    try:
                        process=subprocess.Popen([args.godot,'--headless','--audio-driver','Dummy','--path',str(CLIENT),
                            'res://tests/gameplay_load_client.tscn'],cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT,
                            creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
                    except Exception:
                        log.close()
                        raise
                    processes.append({'process':process,'log':log,'client_id':client_id,'group':groups,
                        'report':report,'started_at_ms':int(time.time()*1000),
                        'run_id':run_id,'process_epoch':process_epoch})
                group_launches.append({'group':groups,'scheduled_at':started+(scheduled_group_at-started_monotonic),
                    'started_at':group_started_at,'finished_at':time.time(),
                    'clients':group_size})
                next_group=time.monotonic()+args.group_interval
                print('GROUP',groups,'clients',len(processes),flush=True)
            if now>=next_sample:
                scheduled_sample_at=next_sample
                sample_started=time.monotonic()
                statuses, invalid_files=read_owned_statuses(processes)
                sample_ms=int(time.time()*1000)
                workload=workload_snapshot(processes,statuses,sample_ms)
                workload_failed=workload_failed or workload['workload_failure']
                fresh, lost_events=new_events(statuses,seen)
                window=aggregate_window(fresh)
                window['lost_event_count']=lost_events
                audit_lost=sum(s.get('audit_lost_count',0) for s in statuses if isinstance(s.get('audit_lost_count',0),int) and not isinstance(s.get('audit_lost_count',0),bool) and s.get('audit_lost_count',0)>=0)
                window['audit_lost_count']=audit_lost
                audit_count_invalid=any(not isinstance(s.get('audit_lost_count',0),int) or isinstance(s.get('audit_lost_count',0),bool) or s.get('audit_lost_count',0)<0 for s in statuses)
                commands=[t for s in fresh for t in s.get('telemetry',[]) if t.get('type')=='realtime']
                rejected=[t for t in commands if t.get('response_type')=='error.command_rejected']
                window['command_rejections']=len(rejected)
                window['command_error_rate']=len(rejected)/len(commands) if commands else 0
                health_task=probes.submit(health_probe,args.server_url)
                metrics_task=probes.submit(metrics,args.prometheus) if args.run else None
                probe_tasks=[health_task]+([metrics_task] if metrics_task is not None else [])
                _,pending_probes=concurrent.futures.wait(probe_tasks,timeout=6)
                probe_timeout=bool(pending_probes)
                health=health_task.result() if health_task.done() else {'ok':False,'duration_ms':None,'status':0,'error':'probe_timeout'}
                resource=metrics_task.result() if metrics_task is not None and metrics_task.done() else {}
                generator,previous_generator=generator_resources(processes,previous_generator)
                causes=[]
                if probe_timeout: causes.append('probe_timeout')
                if len(commands)>=10 and window['command_error_rate']>=.1: causes.append('command_rejections_10pct')
                if not health['ok'] or (health['duration_ms'] is not None and health['duration_ms']>5000): causes.append('health_failed_or_over_5000ms')
                if window['sample_count']>=20 and window['error_rate']>=.1: causes.append('http_errors_10pct')
                if window['valid_latency_count']>=20 and window['http'].get('p95_ms',0)>1500: causes.append('http_p95_over_1500ms')
                if window['realtime'].get('count',0)>=10 and window['realtime'].get('p95_ms',0)>2000: causes.append('command_p95_over_2000ms')
                for key,limit,less in [('cpu',85,False),('memory_available',15,True),('disk_available',15,True),('actor_wait',100,False)]:
                    value=resource.get(key)
                    if value is not None and (value<limit if less else value>limit): causes.append(key+'_redline')
                if args.run and any(resource.get(k) is None for k in ('cpu','memory_available','disk_available')): causes.append('monitoring_unavailable')
                if args.run and generator.get('available') and generator.get('host_memory_available_bytes',0)<2*1024**3:
                    causes.append('generator_memory_low')
                if window['invalid_metric_count'] or lost_events or audit_lost or audit_count_invalid or invalid_files or workload['invalid_schema_count']:
                    causes.append('invalid_telemetry'); workload_failed=True
                if workload['workload_failure']: causes.append('workload_or_generator_failure')
                cycle_counts=[s.get('cycles_completed') for s in statuses]
                if any(not isinstance(n,int) or isinstance(n,bool) or n<0 for n in cycle_counts):
                    causes.append('invalid_cycle_count'); workload_failed=True
                for key in set(streaks)|set(causes): streaks[key]=streaks[key]+1 if key in causes else 0
                row={'schema_version':4,'at':sample_ms/1000,'run_id':run_id,'groups':groups,'clients':len(processes),**workload,
                    'completed_cycles':sum(n for n in cycle_counts if isinstance(n,int) and not isinstance(n,bool) and n>=0),
                    'invalid_status_files':invalid_files,
                    'generator':generator,
                    'observed_interval_seconds':None if previous_sample_ms is None else (sample_ms-previous_sample_ms)/1000,
                    'scheduled_at':started+(scheduled_sample_at-started_monotonic),
                    'sample_schedule_lag_ms':round(max(0.0,sample_started-scheduled_sample_at)*1000,2),
                    'sample_collection_ms':round((time.monotonic()-sample_started)*1000,2),
                    'window':window,'health':health,'resources':resource,'reasons':causes,'streaks':dict(streaks)}
                previous_sample_ms=sample_ms
                samples.append(row)
                save(run_dir/'state.json',row)
                with (run_dir/'samples.jsonl').open('a',encoding='utf-8') as f: f.write(json.dumps(row)+'\n')
                print('SAMPLE',json.dumps(row),flush=True)
                evidence_failures=[cause for cause in causes if cause in ('invalid_telemetry','invalid_cycle_count','workload_or_generator_failure','monitoring_unavailable','probe_timeout','generator_memory_low')]
                if evidence_failures:
                    reason='invalid_evidence:'+','.join(evidence_failures)
                    break
                breached=[k for k,v in streaks.items() if v>=3]
                if breached: reason='redline:'+','.join(breached); break
                if args.smoke and len(processes)==1 and processes[0]['process'].poll() is not None:
                    data=read_json(processes[0]['report']) or {}
                    smoke_verified=processes[0]['process'].returncode==0 and data.get('ok') is True and data.get('cycles_completed',0)>=args.smoke_cycles
                    reason='smoke_passed' if smoke_verified else 'smoke_failed'
                    break
                while next_sample<=time.monotonic(): next_sample+=10
            if args.smoke and time.monotonic()-started_monotonic>420*args.smoke_cycles: reason='smoke_timeout'; break
            time.sleep(.25)
    except KeyboardInterrupt: reason='operator_interrupted'
    except Exception as exc:
        reason='coordinator_error:'+type(exc).__name__+':'+str(exc)
    finally:
        probes.shutdown(wait=False,cancel_futures=True)
        before_stop={p['client_id']:p['process'].poll() for p in processes}
        # A process that failed before STOP is not an intentional shutdown.
        workload_failed=workload_failed or any(code not in (None,0) for code in before_stop.values())
        cleanup_error=None
        forced_termination=[]
        stop_issued_monotonic_ns=time.monotonic_ns()
        try:
            forced_termination=stop_all(processes,stop_file)
        except Exception as exc:
            cleanup_error=type(exc).__name__+':'+str(exc)
            workload_failed=True
            for entry in processes:
                process=entry['process']
                if process.poll() is None:
                    forced_termination.append(process.pid)
                    try:
                        process.kill()
                        process.wait(timeout=10)
                    except (OSError, subprocess.SubprocessError):
                        cleanup_error+='; fallback termination failed for PID '+str(process.pid)
        finally:
            for entry in processes: entry['log'].close()
        if forced_termination:
            workload_failed=True
            cleanup_error=(cleanup_error+'; ' if cleanup_error else '')+'forced_termination:'+','.join(map(str,forced_termination))
        final_before_cleanup = samples[-1] if samples else None
        required_samples = max(1, math.ceil(args.max_seconds / 10 * .9))
        load_verified = (args.run and reason == 'duration_limit' and not workload_failed and
            groups == args.max_groups and len(processes) == args.max_groups * args.group_size and
            len(samples) >= required_samples and all(code is None for code in before_stop.values()) and
            final_before_cleanup is not None and final_before_cleanup['fresh_status_clients'] == len(processes) and
            any(sample['online'] == len(processes) for sample in samples) and
            any(sample['in_room'] == len(processes) for sample in samples) and
            not forced_termination and not cleanup_error)
        outcome=classify_stop(reason,smoke_verified=smoke_verified,
            load_verified=load_verified,workload_failed=workload_failed)
        report_data={'schema_version':5,'started':started,'ended':time.time(),'groups':groups,'clients':len(processes),
            'stop_reason':reason,'outcome':outcome,'source':source,'cleanup_error':cleanup_error,
            'load_window_verified':load_verified,'required_samples':required_samples,
            'stop_issued_monotonic_ns':stop_issued_monotonic_ns,
            'first_trigger':next((cause for sample in samples for cause in sample['reasons']),reason),
            'all_triggers':sorted({cause for sample in samples for cause in sample['reasons']} | {reason}),
            'forced_termination_pids':forced_termination,'cleanup_complete':not cleanup_error,
            'process_exits':[{'client_id':p['client_id'],'before_stop':before_stop[p['client_id']],
                'after_stop':p['process'].poll()} for p in processes],
            'group_size':group_size,'interval_seconds':args.group_interval,'scope':'real Godot Game store: login once, repeated preparation/match/PVE or PVP/settlement; no market trades',
            'group_launches':group_launches,'samples':samples,'final_clients':read_owned_statuses(processes)[0]}
        try:
            save(run_dir/'report.json',report_data)
        except OSError as exc:
            outcome=classify_stop('invalid_evidence:report_write_failed',workload_failed=True)
            try:
                (run_dir/'report.emergency.txt').write_text('Report write failed: '+repr(exc)+'\nstop='+reason+'\noutcome='+repr(outcome),encoding='utf-8')
            except OSError:
                pass
    print('STOP',reason,'OUTCOME',outcome,'REPORT',run_dir/'report.json',flush=True)
    return outcome['exit_code']

if __name__=='__main__': raise SystemExit(main())
