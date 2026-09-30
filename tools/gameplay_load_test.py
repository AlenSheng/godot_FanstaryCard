"""Prepare by default; --run starts real Godot gameplay with 50 clients/120s.
--smoke runs one account for three completed matches by default.
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
from pr13_runtime_evidence import coverage, reconcile_cycles, result_dimensions

QUERIES = {
    'cpu': '100*(1-avg(rate(node_cpu_seconds_total{job="node",instance="node-exporter:9100",mode="idle"}[1m])))',
    'memory_available': '100*node_memory_MemAvailable_bytes{job="node",instance="node-exporter:9100"}/node_memory_MemTotal_bytes{job="node",instance="node-exporter:9100"}',
    'disk_available': '100*node_filesystem_avail_bytes{job="node",instance="node-exporter:9100",mountpoint="/"}/node_filesystem_size_bytes{job="node",instance="node-exporter:9100",mountpoint="/"}',
    'actor_wait': 'histogram_quantile(0.95,sum(rate(fantasycard_room_actor_command_wait_milliseconds_bucket{job="fantasycard",instance="otel-collector:9464"}[5m])) by (le))',
    'server_humans_in_room': 'fantasycard_rooms_humans_active{job="fantasycard",instance="otel-collector:9464"}',
}

def metrics(base):
    result = dict.fromkeys(QUERIES)
    # One snapshot and one bounded network round trip for all independent
    # measurements; the label exists only in this query's result vector.
    query = ' or '.join('label_replace(('+expression+'),"pr13_metric","'+key+'","",".*")'
                        for key,expression in QUERIES.items())
    try:
        with urllib.request.urlopen(base.rstrip('/')+'/api/v1/query?'+urllib.parse.urlencode({'query':query}),timeout=3) as r:
            rows=json.load(r)['data']['result']
        for key in result:
            matches=[row for row in rows if row.get('metric',{}).get('pr13_metric')==key]
            if len(matches)!=1: continue
            value=float(matches[0]['value'][1])
            result[key]=value if math.isfinite(value) else None
    except (OSError, ValueError, KeyError, IndexError, TypeError): pass
    return result

def save(path, data):
    tmp=path.with_suffix(path.suffix+'.tmp')
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2),encoding='utf-8')
    tmp.replace(path)

def completed_smoke(processes, expected_clients, cycles):
    if len(processes)!=expected_clients or any(entry['process'].poll() is None for entry in processes):
        return None
    reports=[read_json(entry['report']) or {} for entry in processes]
    return all(entry['process'].returncode==0 and report.get('ok') is True and
               isinstance(report.get('cycles_completed'),int) and not isinstance(report.get('cycles_completed'),bool) and
               report['cycles_completed']>=cycles for entry,report in zip(processes,reports))

def read_owned_statuses(processes, cache=None):
    statuses = []
    invalid_files = 0
    for entry in processes:
        path = Path(str(entry['report']) + '.status.json')
        if not path.exists():
            if cache is not None and entry['client_id'] in cache:
                statuses.append(cache[entry['client_id']])
            continue
        value = read_json(path)
        if value is None:
            invalid_files += 1
        else:
            statuses.append(value)
    owned, invalid_ownership = owned_statuses(processes, statuses)
    if cache is not None:
        cache.update((status['client_id'],status) for status in owned)
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
    parser.add_argument('--launch-interval-seconds',type=float,default=0,
                        help='Preregistered spacing between account launches; sampling continues during ramps')
    parser.add_argument('--smoke-cycles',type=int,default=3)
    parser.add_argument('--smoke-clients',type=int,default=1)
    parser.add_argument('--load-profile', choices=('cyclic-gameplay','active-hold','functional-cycles'), default='cyclic-gameplay')
    parser.add_argument('--target-online',type=int)
    parser.add_argument('--target-active',type=int)
    parser.add_argument('--hold-seconds',type=int,default=600)
    parser.add_argument('--minimum-continuous-seconds',type=int,default=120)
    parser.add_argument('--minimum-coverage',type=float,default=.95)
    parser.add_argument('--maximum-sample-gap',type=float,default=20)
    parser.add_argument('--minimum-command-rate',type=float,default=1)
    parser.add_argument('--hero-class',choices=('Mage','Priest','Guardian','mixed'),default='Mage')
    parser.add_argument('--strategy',choices=('baseline_all_hand','basic','build','mixed'),default='baseline_all_hand')
    parser.add_argument('--strategy-seed',type=int,default=20260930)
    parser.add_argument('--prometheus',default='http://127.0.0.1:19090')
    parser.add_argument('--output',type=Path,default=ROOT/'outputs'/'gameplay-load')
    args=parser.parse_args()
    if not Path(args.godot).is_file(): parser.error('Godot executable is missing')
    if min(args.max_groups,args.max_seconds,args.group_size,args.group_interval,args.smoke_cycles,args.smoke_clients)<1:
        parser.error('Group, duration and cycle limits must be positive')
    if not math.isfinite(args.launch_interval_seconds) or args.launch_interval_seconds < 0:
        parser.error('Launch spacing must be finite and nonnegative')
    target=urllib.parse.urlparse(args.server_url)
    if target.scheme not in ('http','https') or not target.hostname:
        parser.error('A valid --server-url is required')
    if target.hostname not in ('127.0.0.1','localhost','::1') and not args.allow_public_target:
        parser.error('Public targets require --allow-public-target and an explicit --server-url')
    if not args.run and not args.smoke:
        print('Prepared: bounded local run; --smoke validates three cycles by default. --run requires monitoring.')
        return 0
    if args.run and args.smoke: parser.error('Choose --smoke or --run')
    if args.run and args.smoke_clients!=1: parser.error('--smoke-clients belongs to the smoke profile')
    if args.run and args.load_profile == 'functional-cycles': parser.error('Functional cycles are smoke scenarios and cannot prove capacity')
    if args.run:
        baseline=metrics(args.prometheus)
        if any(baseline[k] is None for k in ('cpu','memory_available','disk_available')):
            parser.error('Host monitoring is unavailable; open the SSH Prometheus tunnel before --run')
    source=provenance(ROOT, ('tools/gameplay_load_test.py','tools/cloud_load_test.py',
        'tools/gameplay_load_validation.py','client/tests/gameplay_load_client.gd','client/state/game_store.gd',
        'client/network/gateway.gd','client/network/reusable_http_client.gd',
        'tools/pr13_runtime_evidence.py','client/data/catalog.json',
        'client/ui/card_details.gd','client/state/element_rules.gd',
        'protocol/realtime/v1/realtime.proto'))
    run_dir=args.output.resolve()/(time.strftime('%Y%m%d-%H%M%S')+'-'+uuid.uuid4().hex[:6])
    run_dir.mkdir(parents=True)
    expected_clients = args.smoke_clients if args.smoke else args.max_groups * args.group_size
    contract = {'profile':args.load_profile,
        'acceptance_scope':['execution','evidence','load','gameplay','cleanup'] if args.smoke else ['execution','evidence','load','performance','cleanup'],
        'target_online':expected_clients if args.target_online is None else args.target_online,
        'target_active':expected_clients if args.target_active is None else args.target_active,
        'minimum_window':args.hold_seconds,'minimum_continuous':args.minimum_continuous_seconds,
        'minimum_coverage':args.minimum_coverage,'maximum_gap':args.maximum_sample_gap,
        'minimum_command_rate':args.minimum_command_rate,
        'launch_interval_seconds':args.launch_interval_seconds}
    coverage([],start=0,end=1,**{k:v for k,v in contract.items() if k not in ('profile','acceptance_scope','launch_interval_seconds')})
    save(run_dir/'load-contract.json',contract)
    stop_file=run_dir/'STOP'
    processes=[]; samples=[]; group_launches=[]; streaks=collections.Counter(); seen={}; status_cache={}
    run_id=uuid.uuid4().hex
    workload_failed=False; smoke_verified=False; previous_sample_ms=None; previous_generator=None
    started=time.time(); started_monotonic=time.monotonic()
    next_group=started_monotonic; next_sample=started_monotonic+10
    pending_launches=collections.deque(); next_launch=started_monotonic
    groups=0; reason='running'
    group_size=args.smoke_clients if args.smoke else args.group_size
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
                pending_launches.extend((groups,index) for index in range(group_size))
                group_launches.append({'group':groups,'scheduled_at':started+(scheduled_group_at-started_monotonic),
                    'started_at':group_started_at,'finished_at':None,
                    'clients_scheduled':group_size,'clients':0})
                next_group=time.monotonic()+args.group_interval
                print('GROUP SCHEDULED',groups,'accounts',group_size,flush=True)
            if pending_launches and now>=next_launch:
                launch_group,index=pending_launches.popleft()
                client_id='g%03dc%02d%s'%(launch_group,index+1,uuid.uuid4().hex[:6])
                process_epoch=uuid.uuid4().hex
                report=run_dir/(client_id+'.json')
                env=dict(os.environ,FANTASYCARD_SERVER_URL=args.server_url,FANTASYCARD_LOAD_CLIENT_ID=client_id,
                    FANTASYCARD_LOAD_GROUP=str(launch_group),FANTASYCARD_LOAD_REPORT=str(report),
                    FANTASYCARD_LOAD_STOP_FILE=str(stop_file),FANTASYCARD_LOAD_RUN_ID=run_id,
                    FANTASYCARD_LOAD_PROCESS_EPOCH=process_epoch,
                    FANTASYCARD_LOAD_HERO_CLASS=('Mage','Priest','Guardian')[(len(processes))%3] if args.hero_class=='mixed' else args.hero_class,
                    FANTASYCARD_LOAD_STRATEGY=('baseline_all_hand','basic','build')[(len(processes)//3)%3] if args.strategy=='mixed' else args.strategy,
                    FANTASYCARD_LOAD_SEED=str(args.strategy_seed+len(processes)),
                    FANTASYCARD_LOAD_PROFILE=args.load_profile,
                    FANTASYCARD_LOAD_HOLD_SECONDS=str(args.hold_seconds),
                    FANTASYCARD_LOAD_MAX_CYCLES=str(args.smoke_cycles) if args.smoke else '0')
                log=(run_dir/(client_id+'.log')).open('w',encoding='utf-8')
                try:
                    process=subprocess.Popen([args.godot,'--headless','--audio-driver','Dummy','--path',str(CLIENT),
                        'res://tests/gameplay_load_client.tscn'],cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT,
                        creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
                except Exception:
                    log.close()
                    raise
                processes.append({'process':process,'log':log,'client_id':client_id,'group':launch_group,
                    'report':report,'started_at_ms':int(time.time()*1000),
                    'run_id':run_id,'process_epoch':process_epoch})
                group_record=group_launches[launch_group-1]
                group_record['clients']+=1
                if group_record['clients']==group_size: group_record['finished_at']=time.time()
                next_launch=time.monotonic()+args.launch_interval_seconds
                print('CLIENT LAUNCHED',len(processes),'group',launch_group,flush=True)
            if now>=next_sample:
                scheduled_sample_at=next_sample
                sample_started=time.monotonic()
                statuses, invalid_files=read_owned_statuses(processes,status_cache)
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
                health_task=probes.submit(health_probe,args.server_url,5)
                metrics_task=probes.submit(metrics,args.prometheus) if args.run else None
                probe_tasks=[health_task]+([metrics_task] if metrics_task is not None else [])
                _,pending_probes=concurrent.futures.wait(probe_tasks,timeout=6)
                probe_timeout=bool(pending_probes)
                health=health_task.result() if health_task.done() else {'ok':False,'duration_ms':None,'status':0,'error':'probe_timeout'}
                resource=metrics_task.result() if metrics_task is not None and metrics_task.done() else {}
                workload['server_confirmed_in_room']=resource.get('server_humans_in_room')
                workload['server_count_scope']='all registered non-bot active player routes on this server; no per-run labels'
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
                    'command_rate':None if previous_sample_ms is None or sample_ms<=previous_sample_ms else len(commands)/((sample_ms-previous_sample_ms)/1000),
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
                smoke_result=completed_smoke(processes,expected_clients,args.smoke_cycles) if args.smoke else None
                if smoke_result is not None:
                    smoke_verified=smoke_result
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
        stop_issued_ms=int(time.time()*1000)
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
        hold_end = stop_issued_ms/1000
        hold_start = max(started, hold_end-args.hold_seconds)
        load_coverage = coverage(samples,start=hold_start,end=max(hold_start+.001,hold_end),
            **{k:v for k,v in contract.items() if k not in ('profile','acceptance_scope','launch_interval_seconds')})
        final_clients, final_read_errors = read_owned_statuses(processes,status_cache)
        tail, tail_lost = new_events(final_clients,seen)
        post_stop_failure = any(p['process'].poll() not in (0,None) for p in processes)
        workload_failed = workload_failed or bool(final_read_errors or tail_lost or post_stop_failure)
        load_verified = (args.run and reason == 'duration_limit' and not workload_failed and
            groups == args.max_groups and len(processes) == args.max_groups * args.group_size and
            len(samples) >= required_samples and all(code is None for code in before_stop.values()) and
            final_before_cleanup is not None and final_before_cleanup['fresh_status_clients'] == len(processes) and
            load_coverage['passed'] and
            not forced_termination and not cleanup_error)
        outcome=classify_stop(reason,smoke_verified=smoke_verified,
            load_verified=load_verified,workload_failed=workload_failed)
        audit_events=[]; audit_errors=[]
        for entry in processes:
            try:
                for line in Path(str(entry['report'])+'.telemetry.jsonl').read_text(encoding='utf-8').splitlines():
                    audit_events.append(json.loads(line))
            except (OSError,ValueError) as exc:
                audit_errors.append({'client_id':entry['client_id'],'error':type(exc).__name__})
        cutoffs=reconcile_cycles(audit_events,stop_issued_ms,int(time.time()*1000))
        launched_clients={entry['client_id'] for entry in processes}
        completed_clients=set(cutoffs['final']['cycles_by_client'])
        cutoffs['zero_cycle_clients']=sorted(launched_clients-completed_clients)
        cutoffs['zero_cycle_reason']=None
        final_distribution=collections.Counter(cutoffs['final']['cycles_by_client'].values())
        final_distribution[0]=len(cutoffs['zero_cycle_clients'])
        cutoffs['final']['distribution']=dict(sorted(final_distribution.items()))
        business_cleanup=bool(final_clients) and len(final_clients)==len(processes) and all(client.get('cleanup',{}).get('state')=='Passed' for client in final_clients)
        performance_inputs={'http_latency_samples':sum(sample['window']['http'].get('count',0) for sample in samples),
            'realtime_latency_samples':sum(sample['window']['realtime'].get('count',0) for sample in samples),
            'scope':'existing bounded diagnostic stop rules; not a formal service SLO'}
        performance_verified=(reason=='duration_limit' and load_verified and
            performance_inputs['http_latency_samples']>=20 and performance_inputs['realtime_latency_samples']>=10)
        dimensions=result_dimensions(execution=not reason.startswith('coordinator_error:'),
            evidence=not bool(final_read_errors or tail_lost or audit_errors or cutoffs['evidence_errors'] or
                reason.startswith('invalid_evidence:') or reason.startswith('coordinator_error:')),
            load=load_coverage['passed'] if args.run else smoke_verified,
            gameplay=smoke_verified if args.smoke else None,
            performance=False if args.run and reason.startswith('redline:') else True if args.run and performance_verified else None,
            cleanup=False if cleanup_error else (True if business_cleanup else None),
            applicable=contract['acceptance_scope'])
        if outcome['exit_code']==0 and not dimensions['all_applicable_passed']:
            outcome={'classification':'incomplete_acceptance','passed':False,'exit_code':1}
        report_data={'schema_version':5,'started':started,'ended':time.time(),'groups':groups,'clients':len(processes),
            'stop_reason':reason,'outcome':outcome,'source':source,'cleanup_error':cleanup_error,
            'load_window_verified':load_verified,'required_samples':required_samples,
            'stop_issued_monotonic_ns':stop_issued_monotonic_ns,'stop_issued_ms':stop_issued_ms,
            'load_contract':contract,'load_coverage':load_coverage,'result_dimensions':dimensions,
            'performance_inputs':performance_inputs,
            'cycle_cutoffs':cutoffs,'audit_read_errors':audit_errors,
            'final_read_errors':final_read_errors,'tail_lost_event_count':tail_lost,
            'tail_window':aggregate_window(tail),'post_stop_failure':post_stop_failure,
            'first_trigger':next((cause for sample in samples for cause in sample['reasons']),reason),
            'all_triggers':sorted({cause for sample in samples for cause in sample['reasons']} | {reason}),
            'forced_termination_pids':forced_termination,'process_cleanup_complete':not cleanup_error,
            'business_cleanup_verified':business_cleanup,'cleanup_complete':business_cleanup and not cleanup_error,
            'process_exits':[{'client_id':p['client_id'],'before_stop':before_stop[p['client_id']],
                'after_stop':p['process'].poll()} for p in processes],
            'group_size':group_size,'interval_seconds':args.group_interval,'scope':'real Godot Game store: login once, repeated preparation/match/PVE or PVP/settlement; no market trades',
            'group_launches':group_launches,'samples':samples,'final_clients':final_clients,
            'acceptance_passed':dimensions['all_applicable_passed'],
            'full_acceptance_passed':dimensions['full_acceptance_passed']}
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
