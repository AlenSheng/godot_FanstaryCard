"""Prepare by default; --run starts real Godot gameplay with 50 clients/120s.
--smoke runs one account for three completed matches by default.
Exit codes: 0 preparation-only or verified bounded run; 1 incomplete; 2 performance
redline; 3 invalid workload/evidence; 130 operator stop. No rate-limit changes.
"""
from __future__ import annotations
import argparse
import collections
import concurrent.futures
import hashlib
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
from gameplay_load_validation import aggregate_window, workload_profile_identity, native_frame_observations, assess_cutoff_clock, request_cutoffs, workload_snapshot, owned_statuses, new_events, classify_stop, provenance
from pr13_runtime_evidence import coverage, reconcile_cycles, result_dimensions, sampling_integrity
from pr13_audit_archive import read_owned_audits
from pr13_local_network import LocalOrigins
from pr13_server_diagnostics import current_window
from pr13_status_snapshot import SerializedStatusCache
from pr13_native_package import verify_package, launch_command, package_environment, package_unchanged, runtime_capabilities
from pr13_resource_policy import DEFAULT_GENERATOR_FLOOR, memory_causes, disk_causes, launch_memory_ready, latency_causes

QUERIES = {
    'cpu': '100*(1-avg(rate(node_cpu_seconds_total{job="node",instance="node-exporter:9100",mode="idle"}[1m])))',
    'memory_available': '100*node_memory_MemAvailable_bytes{job="node",instance="node-exporter:9100"}/node_memory_MemTotal_bytes{job="node",instance="node-exporter:9100"}',
    'memory_available_bytes': 'node_memory_MemAvailable_bytes{job="node",instance="node-exporter:9100"}',
    'disk_available': '100*node_filesystem_avail_bytes{job="node",instance="node-exporter:9100",mountpoint="/"}/node_filesystem_size_bytes{job="node",instance="node-exporter:9100",mountpoint="/"}',
    'actor_wait': 'histogram_quantile(0.95,sum(rate(fantasycard_room_actor_command_wait_milliseconds_bucket{job="fantasycard",instance="otel-collector:9464"}[5m])) by (le))',
    'server_humans_in_room': 'fantasycard_rooms_humans_active{job="fantasycard",instance="otel-collector:9464"}',
}
COVERAGE_METADATA = {'profile','acceptance_scope','launch_interval_seconds','http_transport','resource_source','server_metrics_missing_reason','client_max_fps','fps_scope',
                     'client_runtime','native_package_sha256','distinct_local_client_ips','client_memory_start_budget_mib','hero_class','strategy','strategy_seed','cycle_limit_seconds',
                     'minimum_generator_memory_bytes','minimum_cloud_memory_bytes','minimum_cloud_disk_percent',
                     'http_p95_limit_ms','command_p95_limit_ms','health_limit_ms','monitor_timeout_seconds',
                     'maximum_run_seconds','workload_profile_id','workload_profile_qualified','workload_profile_missing_reason'}

def metrics(base, timeout_seconds=3):
    result = dict.fromkeys(QUERIES)
    # One snapshot and one bounded network round trip for all independent
    # measurements; the label exists only in this query's result vector.
    query = ' or '.join('label_replace(('+expression+'),"pr13_metric","'+key+'","",".*")'
                        for key,expression in QUERIES.items())
    try:
        with urllib.request.urlopen(base.rstrip('/')+'/api/v1/query?'+urllib.parse.urlencode({'query':query}),timeout=timeout_seconds) as r:
            rows=json.load(r)['data']['result']
        for key in result:
            matches=[row for row in rows if row.get('metric',{}).get('pr13_metric')==key]
            if len(matches)!=1: continue
            value=float(matches[0]['value'][1])
            result[key]=value if math.isfinite(value) else None
    except (OSError, ValueError, KeyError, IndexError, TypeError): pass
    return result


def local_host_metrics(server_metrics_file=None, server_pid=None):
    """Measured shared Windows/local-host diagnostics; absent actor metrics stay null."""
    result = dict.fromkeys(QUERIES)
    if psutil is None:
        return result
    try:
        memory = psutil.virtual_memory()
        disk = psutil.disk_usage(str(ROOT.anchor))
        result.update(cpu=psutil.cpu_percent(interval=.2),
                      memory_available=100 * memory.available / memory.total,
                      memory_available_bytes=memory.available,
                      disk_available=100 * disk.free / disk.total)
    except (OSError, ValueError, psutil.Error):
        pass
    if server_metrics_file is not None:
        result.update(current_window(server_metrics_file, server_pid))
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
               all(report.get(key) == entry[key] for key in ('client_id', 'run_id', 'process_epoch') if key in entry) and
               ('run_id' not in entry or report.get('pid') == entry['process'].pid) and
               isinstance(report.get('cycles_completed'),int) and not isinstance(report.get('cycles_completed'),bool) and
               report['cycles_completed']>=cycles for entry,report in zip(processes,reports))

def read_owned_statuses(processes, cache=None, now_monotonic_ms=None, *, require_files=False, read_errors=None):
    statuses = []
    invalid_files = 0
    for entry in processes:
        path = Path(str(entry['report']) + '.status.json')
        failures = []
        disposition = 'unclassified_read_failure'
        try:
            # The Windows producer replaces this file while the reader opens
            # it. Retry only failed I/O, never malformed JSON or foreign data.
            # A permanent failure still invalidates the sample; a recovered
            # read must supply an actual heartbeat rather than refresh cache.
            for attempt in range(1, 4):
                try:
                    if path.stat().st_size > MAX_NATIVE_FINAL_REPORT_BYTES:
                        raise ValueError('Native status byte limit exceeded')
                    raw = path.read_text(encoding='utf8')
                    if len(raw.encode('utf8')) > MAX_NATIVE_FINAL_REPORT_BYTES:
                        raise ValueError('Native status byte limit exceeded')
                    break
                except (OSError, UnicodeError) as exc:
                    failures.append({'client_id': entry['client_id'], 'file': path.name,
                        'error': type(exc).__name__, 'errno': getattr(exc, 'errno', None),
                        'winerror': getattr(exc, 'winerror', None), 'attempt': attempt})
                    if isinstance(exc, (FileNotFoundError, UnicodeError)) or attempt == 3:
                        raise
                    time.sleep(.01)
            try:
                value=json.loads(raw)
            except ValueError as exc:
                failures.append({'client_id': entry['client_id'], 'file': path.name,
                    'error': type(exc).__name__, 'attempt': attempt,
                    'line': getattr(exc, 'lineno', None), 'column': getattr(exc, 'colno', None)})
                raise
            disposition = 'recovered_read' if failures else None
        except FileNotFoundError:
            disposition = 'missing_required_file' if require_files else 'missing_file'
            if require_files:
                invalid_files += 1
            elif cache is not None and entry['client_id'] in cache:
                statuses.append(cache[entry['client_id']])
                disposition = 'prior_owned_sample'
            continue
        except (OSError,UnicodeError,ValueError):
            disposition = 'invalid_file'
            invalid_files += 1
            continue
        finally:
            if read_errors is not None:
                read_errors.extend(dict(failure, disposition=disposition) for failure in failures)
        statuses.append(value)
    owned, invalid_ownership = owned_statuses(processes, statuses)
    receipt_ms=time.monotonic()*1000 if now_monotonic_ms is None else now_monotonic_ms
    for index,status in enumerate(owned):
        # Local receipt time advances only with the client's heartbeat sequence.
        # An unchanged cached file cannot remain online when the wall clock moves.
        status=dict(status)
        owned[index]=status
        status.pop('_received_at_monotonic_ms',None)
        sequence=status.get('status_seq')
        if sequence is None: continue  # Historical evidence keeps its old clock contract.
        if not isinstance(sequence,int) or isinstance(sequence,bool) or sequence<1:
            invalid_ownership+=1;continue
        previous=cache.get(status['client_id']) if cache is not None else None
        prior_sequence=previous.get('status_seq',0) if previous else 0
        if previous and sequence<=prior_sequence:
            if sequence==prior_sequence and status == {key: value for key, value in previous.items() if key != '_received_at_monotonic_ms'}:
                # Equal producer content already exists in the current decode.
                # Retain its original receipt without retaining another full tree.
                if '_received_at_monotonic_ms' in previous:
                    status['_received_at_monotonic_ms']=previous['_received_at_monotonic_ms']
                owned[index]=status
            else:
                owned[index]=dict(previous)
                invalid_ownership+=1
        else: status['_received_at_monotonic_ms']=receipt_ms
    owned=[status for status in owned if status.get('status_seq') is None or
           (isinstance(status['status_seq'],int) and not isinstance(status['status_seq'],bool) and status['status_seq']>0)]
    if cache is not None:
        cache.update((status['client_id'],status) for status in owned)
    return owned, invalid_files + invalid_ownership


def read_audit_events(processes, final_clients):
    """Validate bounded original segments and spool owned events off heap."""
    return read_owned_audits(processes, final_clients)


MAX_NATIVE_FINAL_REPORT_BYTES = 8 * 1024 * 1024


def read_native_final_reports(processes, final_clients, *, max_bytes=MAX_NATIVE_FINAL_REPORT_BYTES):
    """Validate terminal JSON independently of the last heartbeat/status file.

    A valid status cannot repair a missing, corrupt, foreign, or contradictory
    primary report. Keep raw files intact and record only bounded diagnostics.
    """
    reports, errors = [], []
    final_by_id = {row['client_id']: row for row in final_clients}
    for entry in processes:
        cid, path = entry['client_id'], Path(entry['report'])
        context = dict(client_id=cid, file=path.name)
        try:
            with path.open('rb') as stream:
                raw = stream.read(max_bytes + 1)
            if len(raw) > max_bytes:
                errors.append(dict(context, error='native_final_report_too_large', limit_bytes=max_bytes))
                continue
            context.update(bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())
            report = json.loads(raw.decode('utf-8'))
        except (OSError, UnicodeError, ValueError) as exc:
            errors.append(dict(context, error='native_final_read_failed', error_type=type(exc).__name__,
                               line=getattr(exc, 'lineno', None), column=getattr(exc, 'colno', None)))
            continue
        if not isinstance(report, dict):
            errors.append(dict(context, error='native_final_not_object'))
            continue
        if (type(report.get('pid')) is not int or report['pid'] != entry['process'].pid
                or any(report.get(k) != entry.get(k) for k in ('client_id', 'run_id', 'process_epoch'))):
            errors.append(dict(context, error='native_final_foreign_context'))
            continue
        invalid = []
        for key in ('cycles_completed', 'event_seq_max', 'audit_lost_count'):
            if type(report.get(key)) is not int or report[key] < 0:
                invalid.append(key)
        if type(report.get('ok')) is not bool:
            invalid.append('ok')
        if report.get('outcome') not in ('completed', 'cancelled', 'failed'):
            invalid.append('outcome')
        if not isinstance(report.get('errors'), list):
            invalid.append('errors')
        if (not isinstance(report.get('cleanup'), dict)
                or report['cleanup'].get('state') not in ('Passed', 'Failed', 'Unknown')):
            invalid.append('cleanup')
        if invalid:
            errors.append(dict(context, error='native_final_invalid_schema', fields=invalid))
            continue
        status = final_by_id.get(cid)
        if status is None:
            errors.append(dict(context, error='native_final_status_missing'))
        else:
            fields = ('cycles_completed', 'event_seq_max', 'audit_lost_count', 'errors', 'cleanup')
            different = [key for key in fields if report[key] != status.get(key)]
            for key in ('hero_class', 'strategy', 'strategy_seed', 'load_profile', 'cycle_limit_seconds', 'audit_storage'):
                if key in report and report[key] != status.get(key):
                    different.append(key)
            if different:
                errors.append(dict(context, error='native_final_status_disagreement', fields=different))
        report['_primary_report_sha256'] = context['sha256']
        report['_primary_report_bytes'] = len(raw)
        reports.append(report)
    return reports, errors


def generator_resources(processes, previous):
    if psutil is None:
        return {'available':False,'reason':'psutil_missing'}, previous
    now=time.monotonic()
    cpu_by_pid={}; observations=[]; excluded=[]
    expected=[{'pid':os.getpid(),'role':'coordinator'}]
    for entry in processes:
        code=entry['process'].poll()
        if code is None:
            expected.append({'pid':entry['process'].pid,'role':'native','client_id':entry['client_id'],
                'run_id':entry.get('run_id'),'process_epoch':entry.get('process_epoch')})
        else:
            excluded.append({'pid':entry['process'].pid,'client_id':entry['client_id'],'exit_code':code})
    for entry in expected:
        row=dict(entry)
        try:
            process=psutil.Process(entry['pid']);times=process.cpu_times()
            seconds=times.user+times.system;cpu_by_pid[entry['pid']]=seconds
            row.update(available=True,rss_bytes=process.memory_info().rss,threads=process.num_threads())
            if previous is None or entry['pid'] not in previous[1] or now<=previous[0]:
                row.update(cpu_percent_of_one_core=None,cpu_missing_reason='first_or_new_process_counter')
            else:
                row.update(cpu_percent_of_one_core=round(100*max(0,seconds-previous[1][entry['pid']])/(now-previous[0]),2),cpu_missing_reason=None)
            for key,method,field in [('handles','num_handles',None),('write_bytes_cumulative','io_counters','write_bytes')]:
                try:
                    value=getattr(process,method)();row[key]=getattr(value,field) if field else value
                    row[key+'_missing_reason']=None
                except (AttributeError,psutil.NoSuchProcess,psutil.AccessDenied,OSError) as error:
                    row[key]=None;row[key+'_missing_reason']=type(error).__name__
        except (psutil.NoSuchProcess,psutil.AccessDenied,OSError) as error:
            row.update(available=False,missing_reason=type(error).__name__,rss_bytes=None,cpu_percent_of_one_core=None,threads=None,handles=None,write_bytes_cumulative=None)
        row.update(packet_send_rate=None,packet_send_rate_missing_reason='No per-process socket packet counter hook; command completion rates are reported separately')
        observations.append(row)
    def complete_sum(key):
        values=[row.get(key) for row in observations]
        return sum(values) if all(value is not None for value in values) else None
    measured=sum(row.get('available') is True for row in observations)
    result={'available':True,'measured_processes':measured,'processes':observations,
        'excluded_exited_native_processes':excluded,'native_alive_processes':len(expected)-1,
        'cpu_percent_of_one_core':complete_sum('cpu_percent_of_one_core'),
        'cpu_missing_reason':None if complete_sum('cpu_percent_of_one_core') is not None else 'First/new/unavailable process counters; partial totals are not a full generator CPU measurement',
        'logical_cores':psutil.cpu_count(logical=True),'rss_bytes':complete_sum('rss_bytes'),
        'rss_missing_reason':None if complete_sum('rss_bytes') is not None else 'One or more owned process RSS observations unavailable',
        'host_memory_available_bytes':psutil.virtual_memory().available,'threads':complete_sum('threads'),
        'handles':complete_sum('handles'),'handles_missing_reason':None if complete_sum('handles') is not None else 'One or more owned process handle observations unavailable',
        'write_bytes_cumulative':complete_sum('write_bytes_cumulative'),
        'packet_send_rate':None,'packet_send_rate_missing_reason':'No attributable per-process socket packet counter; I/O writes are not network packets',
        'scope':'Measured local generator/coordinator processes, separate from cloud server metrics'}
    return result,(now,cpu_by_pid)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run',action='store_true')
    parser.add_argument('--smoke',action='store_true')
    # On Windows the small *_console.exe is a launcher with a different PID
    # from the engine process. Own the actual engine PID for status validation.
    parser.add_argument('--godot',default=r'F:\GitHubFiles\Godot_v4.7.2-stable_win64.exe\Godot_v4.7.2-stable_win64.exe')
    parser.add_argument('--native-package',type=Path,help='Verified complete debug package; directly owns its Native PID')
    parser.add_argument('--native-package-contract',type=Path,help='Exact executable/PCK/current source input verification contract')
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
    parser.add_argument('--cycle-limit-seconds',type=int,default=240,
                        help='Preregistered per-expedition observation limit, 60-2400 seconds; overall deadline still applies')
    parser.add_argument('--load-profile', choices=('cyclic-gameplay','active-hold','functional-cycles','cleared-extraction'), default='cyclic-gameplay')
    parser.add_argument('--target-online',type=int)
    parser.add_argument('--target-active',type=int)
    parser.add_argument('--hold-seconds',type=int,default=600)
    parser.add_argument('--minimum-continuous-seconds',type=int,default=120)
    parser.add_argument('--minimum-coverage',type=float,default=.95)
    parser.add_argument('--maximum-sample-gap',type=float,default=20)
    parser.add_argument('--minimum-generator-memory-bytes',type=int,default=DEFAULT_GENERATOR_FLOOR)
    parser.add_argument('--minimum-cloud-memory-bytes',type=int,
                        help='Explicit absolute available-memory floor; otherwise the legacy 15 percent guard applies')
    parser.add_argument('--minimum-cloud-disk-percent',type=float,default=15.0,
                        help='Explicit per-run cloud free-disk minimum, 5-100 percent; legacy default remains 15')
    parser.add_argument('--client-memory-start-budget-mib',type=int,default=256)
    parser.add_argument('--http-p95-limit-ms',type=int,default=1500)
    parser.add_argument('--command-p95-limit-ms',type=int,default=2000)
    parser.add_argument('--health-limit-ms',type=int,default=5000)
    parser.add_argument('--monitor-timeout-seconds',type=float,default=3)
    parser.add_argument('--minimum-command-rate',type=float,default=1)
    parser.add_argument('--hero-class',choices=('Mage','Priest','Guardian','mixed'),default='Mage')
    parser.add_argument('--strategy',choices=('baseline_all_hand','basic','build','mixed'),default='baseline_all_hand')
    parser.add_argument('--strategy-seed',type=int,default=20260930)
    parser.add_argument('--prometheus',default='http://127.0.0.1:19090')
    parser.add_argument('--local-resource-sampling',action='store_true',
                        help='Owned loopback diagnostic only; shared-host CPU/memory/disk, missing server metrics remain unknown')
    parser.add_argument('--local-server-metrics', type=Path, help='Actual owned native server diagnostic JSONL')
    parser.add_argument('--local-server-pid', type=int, help='Exact owned server OS process identity')
    parser.add_argument('--client-project', type=Path, help='Immutable copied real client project; defaults to repository client')
    parser.add_argument('--http-transport',choices=('reusable','per-request'),default='reusable')
    parser.add_argument('--client-max-fps', type=int,
                        help='Optional 1-240 FPS candidate; creates a distinct workload profile')
    parser.add_argument('--distinct-local-client-ips',action='store_true',
                        help='Owned loopback byte relays use real 127.0.0.x client source IPs, preserving default per-IP limits')
    parser.add_argument('--output',type=Path,default=ROOT/'outputs'/'gameplay-load')
    parser.add_argument('--stop-file',type=Path,
                        help='Owned supervisor stop signal; may exist before the run directory is created')
    args=parser.parse_args()
    if args.minimum_generator_memory_bytes < 1 or args.client_memory_start_budget_mib < 1 or (args.minimum_cloud_memory_bytes is not None and args.minimum_cloud_memory_bytes < 1):
        parser.error('Memory floors and launch reserve must be positive')
    if any(not 1 <= value <= 60000 for value in [args.http_p95_limit_ms,args.command_p95_limit_ms,args.health_limit_ms]) or not math.isfinite(args.monitor_timeout_seconds) or not 0 < args.monitor_timeout_seconds <= 60:
        parser.error('Latency limits must be positive and bounded to 60 seconds')
    if not math.isfinite(args.minimum_cloud_disk_percent) or not 5 <= args.minimum_cloud_disk_percent <= 100:
        parser.error('Cloud disk minimum must be finite and between 5 and 100 percent')
    if args.client_max_fps is not None and not 1 <= args.client_max_fps <= 240:
        parser.error('Explicit FPS candidate must be between 1 and 240')
    if args.native_package is None and not Path(args.godot).is_file(): parser.error('Godot executable is missing')
    if args.native_package_contract is not None and args.native_package is None: parser.error('Package contract requires --native-package')
    if args.native_package is not None and (args.native_package_contract is None or args.client_project is None or args.client_max_fps is not None):
        parser.error('Verified debug package requires its contract, explicit complete client project and uncapped FPS')
    active_client = CLIENT if args.client_project is None else args.client_project.resolve()
    if not (active_client/'project.godot').is_file() or not (active_client/'tests/gameplay_load_client.tscn').is_file():
        parser.error('The actual client project and gameplay scene are required')
    native_package_proof=None
    if args.native_package is not None:
        names=subprocess.check_output(['git','ls-files','client'],cwd=ROOT,text=True).splitlines()
        try: native_package_proof=verify_package(args.native_package,args.native_package_contract,active_client,names)
        except (OSError,ValueError,TypeError) as error: parser.error(str(error))
    if min(args.max_groups,args.max_seconds,args.group_size,args.group_interval,args.smoke_cycles,args.smoke_clients)<1:
        parser.error('Group, duration and cycle limits must be positive')
    if not math.isfinite(args.launch_interval_seconds) or args.launch_interval_seconds < 0:
        parser.error('Launch spacing must be finite and nonnegative')
    if not 60<=args.cycle_limit_seconds<=2400:
        parser.error('Per-expedition observation limit must be between 60 and 2400 seconds')
    target=urllib.parse.urlparse(args.server_url)
    if target.scheme not in ('http','https') or not target.hostname:
        parser.error('A valid --server-url is required')
    if target.hostname not in ('127.0.0.1','localhost','::1') and not args.allow_public_target:
        parser.error('Public targets require --allow-public-target and an explicit --server-url')
    if args.local_resource_sampling and target.hostname not in ('127.0.0.1','localhost','::1'):
        parser.error('Local resource sampling requires an owned loopback server')
    if (args.local_server_metrics is None) != (args.local_server_pid is None):
        parser.error('Native diagnostic file and exact owned server PID must be provided together')
    if args.local_server_metrics is not None and (not args.local_resource_sampling or args.local_server_pid < 1):
        parser.error('Native diagnostics require the explicit owned loopback diagnostic profile and a positive PID')
    if args.distinct_local_client_ips and (target.scheme!='http' or target.hostname!='127.0.0.1'):
        parser.error('Distinct local client IPs require an owned HTTP 127.0.0.1 server')
    if not args.run and not args.smoke:
        print('Prepared: bounded local run; --smoke validates three cycles by default. --run requires monitoring.')
        return 0
    if args.run and args.smoke: parser.error('Choose --smoke or --run')
    if args.run and args.smoke_clients!=1: parser.error('--smoke-clients belongs to the smoke profile')
    if args.run and args.load_profile in ('functional-cycles','cleared-extraction'): parser.error('Functional/cleared extraction cycles are smoke scenarios and cannot prove original capacity')
    if args.run:
        baseline=local_host_metrics(args.local_server_metrics, args.local_server_pid) if args.local_resource_sampling else metrics(args.prometheus,args.monitor_timeout_seconds)
        memory_key = 'memory_available' if args.minimum_cloud_memory_bytes is None else 'memory_available_bytes'
        if any(baseline[k] is None for k in ('cpu',memory_key,'disk_available')):
            parser.error('Host monitoring is unavailable; provide an authorized Prometheus endpoint before --run')
        if psutil is None:
            parser.error('Generator memory monitoring is required before --run')
    source=provenance(ROOT, ('tools/gameplay_load_test.py','tools/cloud_load_test.py','tools/pr13_resource_policy.py',
        'tools/pr13_status_snapshot.py','tools/pr13_native_package.py',
        'tools/gameplay_load_validation.py','client/tests/gameplay_load_client.gd','client/state/game_store.gd',
        'client/network/gateway.gd','client/network/reusable_http_client.gd',
        'tools/pr13_runtime_evidence.py','tools/pr13_audit_archive.py','client/data/catalog.json',
        'tools/pr13_local_network.py',
        'client/ui/card_details.gd','client/state/element_rules.gd',
        'protocol/realtime/v1/realtime.proto'))
    if native_package_proof is not None:
        source['native_package']=dict(native_package_proof)
        source['sha256'].update({'native-package/'+key:native_package_proof[key+'_sha256'] for key in ('executable','pck','contract')})
    if args.client_project is not None:
        # Preserve the actual executed bytes independently of later checkout
        # edits. No claim that an arbitrary replacement project is equivalent.
        import hashlib
        names = subprocess.check_output(['git','ls-files','client'],cwd=ROOT,text=True).splitlines()
        actual_inputs = {}
        for name in names:
            file = active_client / Path(name).relative_to('client')
            if not file.is_file(): parser.error('Copied client is missing a tracked source dependency')
            actual_inputs[name] = hashlib.sha256(file.read_bytes()).hexdigest()
        source['active_client_project'] = dict(path=str(active_client), input_hashes=actual_inputs,
            scope='actual immutable copied project; per-file hashes are authoritative, not current checkout bytes')
    run_dir=args.output.resolve()/(time.strftime('%Y%m%d-%H%M%S')+'-'+uuid.uuid4().hex[:6])
    run_dir.mkdir(parents=True)
    expected_clients = args.smoke_clients if args.smoke else args.max_groups * args.group_size
    if args.distinct_local_client_ips and expected_clients>100: parser.error('Local IP origins are bounded to 100 clients')
    contract = {'profile':args.load_profile,
        'acceptance_scope':['execution','evidence','load','gameplay','cleanup'] if args.smoke else ['execution','evidence','load','performance','cleanup'],
        'target_online':expected_clients if args.target_online is None else args.target_online,
        'target_active':expected_clients if args.target_active is None else args.target_active,
        'minimum_window':args.hold_seconds,'minimum_continuous':args.minimum_continuous_seconds,
        'minimum_coverage':args.minimum_coverage,'maximum_gap':args.maximum_sample_gap,
        'minimum_command_rate':args.minimum_command_rate,
        'launch_interval_seconds':args.launch_interval_seconds,
        'http_transport':args.http_transport,
        'client_max_fps':args.client_max_fps,
        'fps_scope':'explicit candidate override' if args.client_max_fps is not None else 'unchanged engine/project default',
        'resource_source':('shared_local_host_and_owned_native_server_diagnostic' if args.local_server_metrics is not None else 'shared_local_host_diagnostic') if args.local_resource_sampling else 'preregistered_prometheus',
        'server_metrics_missing_reason':'No server actor-wait or authoritative room collector configured' if args.local_resource_sampling and args.local_server_metrics is None else None}
    contract.update(distinct_local_client_ips=args.distinct_local_client_ips,client_memory_start_budget_mib=args.client_memory_start_budget_mib,
                    minimum_generator_memory_bytes=args.minimum_generator_memory_bytes,
                    minimum_cloud_memory_bytes=args.minimum_cloud_memory_bytes,
                    minimum_cloud_disk_percent=args.minimum_cloud_disk_percent,
                    http_p95_limit_ms=args.http_p95_limit_ms,command_p95_limit_ms=args.command_p95_limit_ms,
                    health_limit_ms=args.health_limit_ms,monitor_timeout_seconds=args.monitor_timeout_seconds,
                    hero_class=args.hero_class,strategy=args.strategy,strategy_seed=args.strategy_seed,
                    cycle_limit_seconds=args.cycle_limit_seconds,maximum_run_seconds=args.max_seconds)
    contract.update(client_runtime='verified-debug-package' if native_package_proof else 'editor',
                    native_package_sha256=native_package_proof['pck_sha256'] if native_package_proof else None)
    profile_sources=dict(source.get('sha256',{}))
    profile_sources.update(source.get('active_client_project',{}).get('input_hashes',{}))
    profile_identity=workload_profile_identity(contract,profile_sources)
    contract.update(workload_profile_id=profile_identity['workload_profile_id'],workload_profile_qualified=profile_identity['qualified'],
        workload_profile_missing_reason=profile_identity['missing_reason'])
    save(run_dir/'workload-profile.json',profile_identity)
    coverage([],start=0,end=1,**{k:v for k,v in contract.items() if k not in COVERAGE_METADATA})
    save(run_dir/'load-contract.json',contract)
    stop_file=args.stop_file.resolve() if args.stop_file is not None else run_dir/'STOP'
    processes=[]; samples=[]; group_launches=[]; launch_receipts=[]; streaks=collections.Counter(); seen={}; status_cache=SerializedStatusCache()
    run_id=uuid.uuid4().hex
    workload_failed=False; smoke_verified=False; previous_sample_monotonic_ms=None; previous_generator=None
    package_source_failed=False
    started=time.time(); started_monotonic=time.monotonic()
    next_group=started_monotonic; next_sample=started_monotonic+10
    pending_launches=collections.deque(); next_launch=started_monotonic
    groups=0; reason='running'; local_origins=None; origins_cleanup_complete=True
    group_size=args.smoke_clients if args.smoke else args.group_size
    probes=concurrent.futures.ThreadPoolExecutor(max_workers=2,thread_name_prefix='load-probe')
    try:
        save(run_dir/'launch-manifest.json',{'schema_version':1,'run_id':run_id,'source':source,'launches':launch_receipts})
        if args.distinct_local_client_ips:
            local_origins=LocalOrigins(args.server_url,expected_clients).__enter__()
            save(run_dir/'client-origins.json',local_origins.records)
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
                    'scheduled_monotonic_ms':scheduled_group_at*1000,'started_monotonic_ms':now*1000,
                    'started_at':group_started_at,'finished_at':None,
                    'clients_scheduled':group_size,'clients':0})
                next_group=time.monotonic()+args.group_interval
                print('GROUP SCHEDULED',groups,'accounts',group_size,flush=True)
            if pending_launches and now>=next_launch:
                admission_available_bytes = psutil.virtual_memory().available if args.run else None
                if args.run and not launch_memory_ready(admission_available_bytes,args.minimum_generator_memory_bytes,args.client_memory_start_budget_mib):
                    save(run_dir/'launch-admission-rejected.json', {
                        'schema_version':1,'run_id':run_id,'process_started':False,
                        'observed_at_monotonic_ns':time.monotonic_ns(),
                        'available_bytes':admission_available_bytes,
                        'floor_bytes':args.minimum_generator_memory_bytes,
                        'start_budget_mib':args.client_memory_start_budget_mib,
                        'required_bytes':args.minimum_generator_memory_bytes+args.client_memory_start_budget_mib*1024**2,
                        'next_client_number':len(processes)+1,
                        'scheduled_group':pending_launches[0][0],
                        'scheduled_index':pending_launches[0][1],
                        'measurement_source':'psutil.virtual_memory().available at rejected admission'})
                    reason='invalid_evidence:generator_memory_low_before_launch'; break
                launch_group,index=pending_launches.popleft()
                client_id='g%03dc%02d%s'%(launch_group,index+1,uuid.uuid4().hex[:6])
                process_epoch=uuid.uuid4().hex
                report=run_dir/(client_id+'.json')
                env=dict(os.environ,FANTASYCARD_SERVER_URL=local_origins.origins[len(processes)] if local_origins is not None else args.server_url,FANTASYCARD_LOAD_CLIENT_ID=client_id,
                    FANTASYCARD_LOAD_HTTP_TRANSPORT=args.http_transport,
                    FANTASYCARD_LOAD_GROUP=str(launch_group),FANTASYCARD_LOAD_REPORT=str(report),
                    FANTASYCARD_LOAD_STOP_FILE=str(stop_file),FANTASYCARD_LOAD_RUN_ID=run_id,
                    FANTASYCARD_LOAD_PROCESS_EPOCH=process_epoch,
                    FANTASYCARD_LOAD_HERO_CLASS=('Mage','Priest','Guardian')[(len(processes))%3] if args.hero_class=='mixed' else args.hero_class,
                    FANTASYCARD_LOAD_STRATEGY=('baseline_all_hand','basic','build')[(len(processes)//3)%3] if args.strategy=='mixed' else args.strategy,
                    FANTASYCARD_LOAD_SEED=str(args.strategy_seed+len(processes)),
                    FANTASYCARD_LOAD_PROFILE=args.load_profile,
                    FANTASYCARD_LOAD_HOLD_SECONDS=str(args.hold_seconds),
                    FANTASYCARD_LOAD_RUN_SECONDS=str(args.max_seconds),
                    FANTASYCARD_LOAD_CYCLE_LIMIT_SECONDS=str(args.cycle_limit_seconds),
                    FANTASYCARD_LOAD_MAX_CYCLES=str(args.smoke_cycles) if args.smoke else '0')
                feature_report=run_dir/(client_id+'.runtime-features.json') if native_package_proof else None
                if native_package_proof:
                    if feature_report.exists(): raise FileExistsError('Owned runtime capability report already exists')
                    env.update(package_environment(feature_report))
                log=(run_dir/(client_id+'.log')).open('w',encoding='utf-8')
                try:
                    command=launch_command(args.godot,active_client,package=args.native_package,max_fps=args.client_max_fps)
                    process=subprocess.Popen(command,cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT,
                        creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
                except Exception:
                    log.close()
                    raise
                processes.append({'process':process,'log':log,'client_id':client_id,'group':launch_group,
                    'report':report,'started_at_ms':int(time.time()*1000),
                    'started_at_monotonic_ms':time.monotonic()*1000,
                    'run_id':run_id,'process_epoch':process_epoch})
                entry=processes[-1]
                if feature_report is not None: entry['runtime_feature_report']=feature_report
                origin=urllib.parse.urlparse(env['FANTASYCARD_SERVER_URL'])
                launch_receipts.append({key:entry[key] for key in ('client_id','group','run_id','process_epoch',
                    'started_at_ms','started_at_monotonic_ms')})
                launch_receipts[-1].update(pid=process.pid,report_file=report.name,
                    server_origin={'scheme':origin.scheme,'host':origin.hostname,'port':origin.port},
                    hero_class=env['FANTASYCARD_LOAD_HERO_CLASS'],strategy=env['FANTASYCARD_LOAD_STRATEGY'],
                    strategy_seed=int(env['FANTASYCARD_LOAD_SEED']),cycle_limit_seconds=args.cycle_limit_seconds,
                    client_max_fps=args.client_max_fps,command=command)
                launch_receipts[-1].update(client_runtime='verified-debug-package' if native_package_proof else 'editor',
                    runtime_feature_file=feature_report.name if feature_report is not None else None,
                    native_package_sha256=native_package_proof['pck_sha256'] if native_package_proof else None)
                # Checkpoint the real PID/epoch immediately after launch. Never
                # reconstruct process ownership from final client JSON alone.
                # The child is already in processes, so a write fault still
                # reaches owned cleanup and cannot orphan an unrecorded process.
                save(run_dir/'launch-manifest.json',{'schema_version':1,'run_id':run_id,'source':source,'launches':launch_receipts})
                group_record=group_launches[launch_group-1]
                group_record['clients']+=1
                if group_record['clients']==group_size: group_record['finished_at']=time.time()
                next_launch=time.monotonic()+args.launch_interval_seconds
                print('CLIENT LAUNCHED',len(processes),'group',launch_group,flush=True)
            if now>=next_sample:
                scheduled_sample_at=next_sample
                sample_started=time.monotonic()
                status_read_errors=[]
                statuses, invalid_files=read_owned_statuses(processes,status_cache,read_errors=status_read_errors)
                sample_ms=int(time.time()*1000)
                sample_monotonic_ms=time.monotonic()*1000
                workload=workload_snapshot(processes,statuses,sample_ms,now_monotonic_ms=time.monotonic()*1000)
                workload_failed=workload_failed or workload['workload_failure']
                fresh, lost_events=new_events(statuses,seen)
                observed_ms = sample_monotonic_ms - (previous_sample_monotonic_ms if previous_sample_monotonic_ms is not None else started_monotonic * 1000)
                window=aggregate_window(fresh, observed_seconds=observed_ms / 1000 if observed_ms > 0 else None)
                window['lost_event_count']=lost_events
                audit_lost=sum(s.get('audit_lost_count',0) for s in statuses if isinstance(s.get('audit_lost_count',0),int) and not isinstance(s.get('audit_lost_count',0),bool) and s.get('audit_lost_count',0)>=0)
                window['audit_lost_count']=audit_lost
                audit_count_invalid=any(not isinstance(s.get('audit_lost_count',0),int) or isinstance(s.get('audit_lost_count',0),bool) or s.get('audit_lost_count',0)<0 for s in statuses)
                commands=[t for s in fresh for t in s.get('telemetry',[]) if t.get('type')=='realtime']
                rejected=[t for t in commands if t.get('response_type')=='error.command_rejected']
                window['command_rejections']=len(rejected)
                window['command_error_rate']=len(rejected)/len(commands) if commands else 0
                health_task=probes.submit(health_probe,args.server_url,args.health_limit_ms/1000)
                metrics_task=(probes.submit(local_host_metrics, args.local_server_metrics, args.local_server_pid) if args.local_resource_sampling else probes.submit(metrics,args.prometheus,args.monitor_timeout_seconds)) if args.run else None
                probe_tasks=[health_task]+([metrics_task] if metrics_task is not None else [])
                _,pending_probes=concurrent.futures.wait(probe_tasks,timeout=max(args.health_limit_ms/1000,args.monitor_timeout_seconds)+1)
                probe_timeout=bool(pending_probes)
                health=health_task.result() if health_task.done() else {'ok':False,'duration_ms':None,'status':0,'error':'probe_timeout'}
                resource=metrics_task.result() if metrics_task is not None and metrics_task.done() else {}
                workload['server_confirmed_in_room']=resource.get('server_humans_in_room')
                workload['server_count_scope']='all registered non-bot active player routes on this server; no per-run labels'
                generator,previous_generator=generator_resources(processes,previous_generator)
                active_native_pids={entry['process'].pid for entry in processes if entry['process'].poll() is None}
                generator['native_frame_observations']=native_frame_observations([s for s in statuses if s.get('pid') in active_native_pids])
                generator['status_cache']={'representation':'lossless-zlib-json-v1','entries':len(status_cache),'compressed_payload_bytes':status_cache.retained_bytes,'decoded_snapshot_bytes':status_cache.decoded_snapshot_bytes,'byte_scope':'serialized payload only; not total Python heap'}
                causes=[]
                if probe_timeout: causes.append('probe_timeout')
                if len(commands)>=10 and window['command_error_rate']>=.1: causes.append('command_rejections_10pct')
                if window['sample_count']>=20 and window['error_rate']>=.1: causes.append('http_errors_10pct')
                causes.extend(latency_causes(window,health,args.http_p95_limit_ms,args.command_p95_limit_ms,args.health_limit_ms))
                for key,limit,less in [('cpu',85,False),('actor_wait',100,False)]:
                    value=resource.get(key)
                    if value is not None and (value<limit if less else value>limit): causes.append(key+'_redline')
                if args.run or resource.get('disk_available') is not None:
                    causes.extend(disk_causes(resource,args.minimum_cloud_disk_percent))
                if args.run:
                    if resource.get('cpu') is None: causes.append('monitoring_unavailable')
                    causes.extend(memory_causes(resource,generator,args.minimum_generator_memory_bytes,args.minimum_cloud_memory_bytes))
                if window['invalid_metric_count'] or lost_events or audit_lost or audit_count_invalid or invalid_files or workload['invalid_schema_count']:
                    causes.append('invalid_telemetry'); workload_failed=True
                if workload['workload_failure']: causes.append('workload_or_generator_failure')
                cycle_counts=[s.get('cycles_completed') for s in statuses]
                if any(not isinstance(n,int) or isinstance(n,bool) or n<0 for n in cycle_counts):
                    causes.append('invalid_cycle_count'); workload_failed=True
                for key in set(streaks)|set(causes): streaks[key]=streaks[key]+1 if key in causes else 0
                row={'schema_version':4,'at':sample_ms/1000,'sample_monotonic_ms':sample_monotonic_ms,
                    'run_id':run_id,'groups':groups,'clients':len(processes),**workload,
                    'command_rate':None if previous_sample_monotonic_ms is None or observed_ms<=0 else len(commands)/(observed_ms/1000),
                    'command_rate_clock':'local_monotonic',
                    'completed_cycles':sum(n for n in cycle_counts if isinstance(n,int) and not isinstance(n,bool) and n>=0),
                    'invalid_status_files':invalid_files,
                    'status_read_errors':status_read_errors,
                    'generator':generator,
                    'observed_interval_seconds':None if previous_sample_monotonic_ms is None else (sample_monotonic_ms-previous_sample_monotonic_ms)/1000,
                    'scheduled_at':started+(scheduled_sample_at-started_monotonic),
                    'sample_schedule_lag_ms':round(max(0.0,sample_started-scheduled_sample_at)*1000,2),
                    'sample_collection_ms':round((time.monotonic()-sample_started)*1000,2),
                    'window':window,'health':health,'resources':resource,'reasons':causes,'streaks':dict(streaks)}
                previous_sample_monotonic_ms=sample_monotonic_ms
                samples.append(row)
                save(run_dir/'state.json',row)
                with (run_dir/'samples.jsonl').open('a',encoding='utf-8') as f: f.write(json.dumps(row)+'\n')
                print('SAMPLE',json.dumps(row),flush=True)
                evidence_failures=[cause for cause in causes if cause in ('invalid_telemetry','invalid_cycle_count','workload_or_generator_failure','monitoring_unavailable','probe_timeout','generator_memory_low','generator_memory_monitoring_unavailable')]
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
                # Raw producer files remain intact; the next tick needs only
                # compressed snapshots and monotonic/event cursors in memory.
                statuses=fresh=commands=rejected=None
                while next_sample<=time.monotonic(): next_sample+=10
            # The registered overall deadline above applies to smoke as well.
            # A second fixed 420s/cycle cutoff would truncate a valid 600s/cycle
            # profile before its declared --max-seconds observation budget.
            time.sleep(.25)
    except KeyboardInterrupt: reason='operator_interrupted'
    except Exception as exc:
        reason='coordinator_error:'+type(exc).__name__+':'+str(exc)
    finally:
        statuses=fresh=commands=rejected=None
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
            if local_origins is not None:
                try: local_origins.close()
                except (OSError,RuntimeError,TimeoutError) as exc:
                    origins_cleanup_complete=False; workload_failed=True
                    cleanup_error=(cleanup_error+'; ' if cleanup_error else '')+'origin_cleanup:'+type(exc).__name__
        if native_package_proof is not None:
            capability_reports=[];package_errors=[]
            try:
                intact=package_unchanged(native_package_proof)
                if not intact: package_errors.append({'error':'native_package_changed_during_run'})
            except (OSError,ValueError) as error:
                intact=False;package_errors.append({'error':'native_package_read_failed','type':type(error).__name__})
            for entry in processes:
                try:
                    observation=runtime_capabilities(entry['runtime_feature_report'])
                    observation.update(client_id=entry['client_id'],expected_Native_PID=entry['process'].pid,
                        owner_scope='Unique owned launch path; process identity independently checked in status/final Native report')
                    capability_reports.append(observation)
                except (OSError,ValueError,TypeError) as error:
                    package_errors.append({'client_id':entry['client_id'],'error':'native_runtime_capability_invalid','type':type(error).__name__})
            package_source_failed=bool(package_errors)
            source['native_package'].update(unchanged_after_run=intact,capability_reports=capability_reports,evidence_errors=package_errors)
            workload_failed=workload_failed or package_source_failed
        if forced_termination:
            workload_failed=True
            cleanup_error=(cleanup_error+'; ' if cleanup_error else '')+'forced_termination:'+','.join(map(str,forced_termination))
        final_before_cleanup = samples[-1] if samples else None
        required_samples = max(1, math.ceil(args.max_seconds / 10 * .9))
        hold_end = stop_issued_ms/1000
        hold_start = max(started, hold_end-args.hold_seconds)
        load_coverage = coverage(samples,start=hold_start,end=max(hold_start+.001,hold_end),
            **{k:v for k,v in contract.items() if k not in COVERAGE_METADATA})
        sampling=sampling_integrity(samples,started_monotonic*1000,stop_issued_monotonic_ns/1000000,contract['maximum_gap'])
        final_status_read_errors=[]
        final_clients, final_read_errors = read_owned_statuses(processes,status_cache,require_files=True,read_errors=final_status_read_errors)
        native_final_reports, native_report_errors = read_native_final_reports(processes, final_clients)
        tail, tail_lost = new_events(final_clients,seen)
        tail_window = aggregate_window(tail)
        final_audit_lost = sum(s.get('audit_lost_count', 0) for s in final_clients
            if isinstance(s.get('audit_lost_count'), int) and not isinstance(s['audit_lost_count'], bool)
            and s['audit_lost_count'] >= 0)
        final_audit_invalid = any(not isinstance(s.get('audit_lost_count'), int)
            or isinstance(s.get('audit_lost_count'), bool) or s['audit_lost_count'] < 0 for s in final_clients)
        final_cycle_invalid = any(not isinstance(s.get('cycles_completed'), int)
            or isinstance(s.get('cycles_completed'), bool) or s['cycles_completed'] < 0 for s in final_clients)
        final_errors_invalid = any(not isinstance(s.get('errors'), list) for s in final_clients)
        final_business_failed = (any(bool(s.get('errors')) for s in final_clients)
            or any(bool(row['errors']) for row in native_final_reports))
        post_stop_failure = any(p['process'].poll() not in (0,None) for p in processes)
        audit_events, audit_errors = read_audit_events(processes, final_clients)
        final_cutoff_ms=int(time.time()*1000)
        final_cutoff_monotonic_ns=time.monotonic_ns()
        cutoff_clock=assess_cutoff_clock(started*1000,stop_issued_ms,final_cutoff_ms,
            start_monotonic_ms=started_monotonic*1000,
            stop_monotonic_ms=stop_issued_monotonic_ns/1000000,
            final_monotonic_ms=final_cutoff_monotonic_ns/1000000)
        try:
            cutoffs=reconcile_cycles(audit_events,stop_issued_ms,final_cutoff_ms,
                cutoff_clock_qualified=cutoff_clock['qualified'])
        except (OSError, ValueError, RecursionError) as exc:
            audit_errors.append({'error':'audit_stream_analysis_failed','exception':type(exc).__name__})
            cutoffs=reconcile_cycles([],stop_issued_ms,final_cutoff_ms,
                cutoff_clock_qualified=cutoff_clock['qualified'])
            cutoffs['evidence_errors'].append('audit_stream_analysis_failed')
        try:
            request_distributions=request_cutoffs(audit_events,stop_issued_ms,final_cutoff_ms,started_ms=started*1000,
                cutoff_clock_qualified=cutoff_clock['qualified'])
        except (OSError, ValueError, RecursionError) as exc:
            audit_errors.append({'error':'audit_request_analysis_failed','exception':type(exc).__name__})
            # Preserve raw timestamps and the completed cleanup when UTC jumps.
            # No corrected cutoff or elapsed duration is invented for accounting.
            request_distributions={'algorithm_version':'owned-request-cutoffs-v1',
                'running':None,'drain':None,'final':None,
                'evidence_errors':['invalid_request_cutoff_clock' if not cutoff_clock['qualified'] else 'invalid_audit_stream'],
                'cutoffs_unix_ms':{'start':started*1000,'stop':stop_issued_ms,'final':final_cutoff_ms},
                'missing_reason':'Audit/cutoff analysis unavailable; raw retained, local monotonic scheduling unchanged'}
        finally:
            if hasattr(audit_events, 'close'):
                try:
                    audit_events.close()
                except OSError as exc:
                    audit_errors.append({'error':'audit_spool_cleanup_failed','exception':type(exc).__name__})
        final_cycle_disagreement = any(s.get('cycles_completed') !=
            cutoffs['final']['cycles_by_client'].get(s['client_id'], 0) for s in final_clients)
        coverage_evidence_failed = bool(load_coverage.get('evidence_errors'))
        origin_evidence_failed = local_origins is not None and bool(local_origins.errors)
        final_evidence_failed = bool(final_read_errors or native_report_errors or tail_lost or tail_window['invalid_metric_count']
            or final_audit_lost or final_audit_invalid or final_cycle_invalid or final_cycle_disagreement or final_errors_invalid
            or audit_errors or cutoffs['evidence_errors'] or request_distributions['evidence_errors'] or coverage_evidence_failed or origin_evidence_failed or package_source_failed)
        # An operator may intentionally end a run before its first sample.
        # That leaves acceptance incomplete, while preserving exit 130. Real
        # malformed/lost evidence or abnormal child exits still take priority.
        sampling_invalid_stop = not sampling['passed'] and not reason.startswith('operator_')
        workload_failed = workload_failed or final_evidence_failed or post_stop_failure or sampling_invalid_stop
        load_verified = (args.run and reason == 'duration_limit' and not workload_failed and
            groups == args.max_groups and len(processes) == args.max_groups * args.group_size and
            len(samples) >= required_samples and all(code is None for code in before_stop.values()) and
            final_before_cleanup is not None and final_before_cleanup['fresh_status_clients'] == len(processes) and
            load_coverage['passed'] and sampling['passed'] and
            not forced_termination and not cleanup_error)
        outcome=classify_stop(reason,smoke_verified=smoke_verified,
            load_verified=load_verified,workload_failed=workload_failed)
        launched_clients={entry['client_id'] for entry in processes}
        completed_clients=set(cutoffs['final']['cycles_by_client'])
        cutoffs['zero_cycle_clients']=sorted(launched_clients-completed_clients)
        cutoffs['zero_cycle_reason']=None
        final_distribution=collections.Counter(cutoffs['final']['cycles_by_client'].values())
        final_distribution[0]=len(cutoffs['zero_cycle_clients'])
        cutoffs['final']['distribution']=dict(sorted(final_distribution.items()))
        process_cleanup_complete = not cleanup_error and origins_cleanup_complete and all(p['process'].poll() == 0 for p in processes)
        business_cleanup=bool(final_clients) and len(final_clients)==len(processes) and all(
            isinstance(client.get('cleanup'), dict) and client['cleanup'].get('state')=='Passed' for client in final_clients)
        performance_inputs={'http_latency_samples':sum(sample['window']['http'].get('count',0) for sample in samples),
            'realtime_latency_samples':sum(sample['window']['realtime'].get('count',0) for sample in samples),
            'scope':'existing bounded diagnostic stop rules; not a formal service SLO'}
        performance_inputs['actor_wait_samples']=sum(isinstance(sample.get('resources',{}).get('actor_wait'),(int,float))
            and not isinstance(sample['resources']['actor_wait'],bool) and math.isfinite(sample['resources']['actor_wait']) for sample in samples)
        performance_inputs['resource_source']=contract['resource_source']
        performance_verified=(not args.local_resource_sampling and reason=='duration_limit' and load_verified and
            performance_inputs['http_latency_samples']>=20 and performance_inputs['realtime_latency_samples']>=10 and
            performance_inputs['actor_wait_samples']==len(samples))
        business_cleanup_failed = any(isinstance(client.get('cleanup'), dict)
            and client['cleanup'].get('state') == 'Failed' for client in final_clients)
        business_cleanup_failed = business_cleanup_failed or any(
            row['cleanup']['state'] == 'Failed' for row in native_final_reports)
        normal_required = args.smoke and args.load_profile != 'functional-cycles'
        normal_by_client = cutoffs['final']['normal_cycles_by_client']
        normal_verified = (len(processes) == expected_clients and all(
            normal_by_client.get(entry['client_id'], 0) >= args.smoke_cycles
            for entry in processes))
        normal_cycle_requirement = {
            'required': normal_required,
            'passed': normal_verified if normal_required else None,
            'minimum_per_client': args.smoke_cycles if normal_required else None,
            'normal_cycles_by_client': normal_by_client,
            'scope': cutoffs['normal_completion_scope'],
            'functional_workflow_only': args.load_profile == 'functional-cycles'}
        dimensions=result_dimensions(execution=not reason.startswith('coordinator_error:') and process_cleanup_complete
                and not final_business_failed,
            evidence=not bool(final_evidence_failed or not sampling['passed'] or
                reason.startswith('invalid_evidence:') or reason.startswith('coordinator_error:')),
            load=load_coverage['passed'] if args.run else smoke_verified,
            gameplay=(smoke_verified and not final_business_failed and
                (not normal_required or normal_verified)) if args.smoke else None,
            performance=False if args.run and reason.startswith('redline:') else True if args.run and performance_verified else None,
            cleanup=False if not process_cleanup_complete or business_cleanup_failed else (True if business_cleanup else None),
            applicable=contract['acceptance_scope'])
        if outcome['exit_code']==0 and not dimensions['all_applicable_passed']:
            outcome={'classification':'incomplete_acceptance','passed':False,'exit_code':1}
        final_triggers = []
        for failed, trigger in ((final_read_errors, 'final_status_read_failed'),
                (native_report_errors, 'native_final_report_invalid'),
                (tail_lost, 'tail_event_loss'), (tail_window['invalid_metric_count'], 'tail_invalid_metric'),
                (final_audit_lost, 'final_audit_loss'), (final_audit_invalid, 'final_audit_count_invalid'),
                (final_cycle_invalid, 'final_cycle_count_invalid'), (final_errors_invalid, 'final_errors_schema_invalid'),
                (final_cycle_disagreement, 'final_cycle_count_disagreement'),
                (audit_errors, 'audit_archive_invalid'), (cutoffs['evidence_errors'], 'cycle_evidence_invalid'),
                (request_distributions['evidence_errors'], 'request_cutoff_evidence_invalid'),
                (origin_evidence_failed, 'local_origin_evidence_invalid'),
                (package_source_failed, 'native_package_evidence_invalid'),
                (coverage_evidence_failed, 'load_coverage_evidence_invalid'),
                (post_stop_failure, 'post_stop_process_failure'), (final_business_failed, 'final_business_failure'),
                (business_cleanup_failed, 'business_cleanup_failed'), (not sampling['passed'], 'sampling_integrity_failed'),
                (normal_required and smoke_verified and not normal_verified, 'normal_cycle_requirement_not_met')):
            if failed: final_triggers.append(trigger)
        report_data={'schema_version':5,'started':started,'ended':time.time(),'groups':groups,'clients':len(processes),
            'stop_file':str(stop_file),
            'stop_reason':reason,'outcome':outcome,'source':source,'cleanup_error':cleanup_error,
            'load_window_verified':load_verified,'required_samples':required_samples,
            'stop_issued_monotonic_ns':stop_issued_monotonic_ns,'stop_issued_ms':stop_issued_ms,
            'final_cutoff_monotonic_ns':final_cutoff_monotonic_ns,'cutoff_clock_quality':cutoff_clock,
            'load_contract':contract,'load_coverage':load_coverage,'result_dimensions':dimensions,
            'launch_manifest':'launch-manifest.json','launch_receipts':launch_receipts,
            'launch_admission_rejection':read_json(run_dir/'launch-admission-rejected.json'),
            'sampling_integrity':sampling,'started_monotonic_ms':started_monotonic*1000,
            'performance_inputs':performance_inputs,
            'cycle_cutoffs':cutoffs,'normal_cycle_requirement':normal_cycle_requirement,
            'request_distributions':request_distributions,'audit_read_errors':audit_errors,
            'final_read_errors':final_read_errors,'tail_lost_event_count':tail_lost,
            'final_status_read_errors':final_status_read_errors,
            'native_final_report_errors':native_report_errors,
            'native_final_reports':[{key:row[key] for key in ('client_id','pid','ok','outcome','cycles_completed',
                'event_seq_max','audit_lost_count','cleanup','_primary_report_sha256','_primary_report_bytes')} for row in native_final_reports],
            'native_final_report_limit_bytes':MAX_NATIVE_FINAL_REPORT_BYTES,
            'tail_window':tail_window,'post_stop_failure':post_stop_failure,
            'final_audit_lost_count':final_audit_lost,'final_audit_count_invalid':final_audit_invalid,
            'final_triggers':final_triggers,
            'first_trigger':next((cause for sample in samples for cause in sample['reasons']),reason),
            'all_triggers':sorted({cause for sample in samples for cause in sample['reasons']} | {reason} | set(final_triggers)),
            'forced_termination_pids':forced_termination,'process_cleanup_complete':process_cleanup_complete,
            'business_cleanup_verified':business_cleanup,'cleanup_complete':business_cleanup and process_cleanup_complete,
            'process_exits':[{'client_id':p['client_id'],'before_stop':before_stop[p['client_id']],
                'after_stop':p['process'].poll()} for p in processes],
            'group_size':group_size,'interval_seconds':args.group_interval,'scope':'real Godot Game store: login once, repeated preparation/match/PVE or PVP/settlement; no market trades',
            'group_launches':group_launches,'samples':samples,'final_clients':final_clients,
            'local_origin_manifest':local_origins.records if local_origins is not None else None,
            'local_origin_errors':local_origins.errors if local_origins is not None else [],
            'local_origin_cleanup_complete':origins_cleanup_complete,
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
