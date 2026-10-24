"""Replay sealed full-native cohorts and adjudicate their shared capacity window.

Raw cohort reports remain authoritative for their original scopes. This module
adds global identities, frozen Git inputs, native OS process inspection and
clock-bounded overlap. A smaller run, a scalar count, or the overlap component
alone cannot award joint capacity acceptance.
"""
from __future__ import annotations

import hashlib
import json
import ntpath
import os
from pathlib import Path, PurePosixPath
import subprocess
import uuid
import urllib.parse

try:
    from .pr13_distributed_load import joint_overlap, clock_envelope
    from .pr13_runtime_evidence import coverage, sampling_integrity, reconcile_cycles, finite
    from .gameplay_load_validation import workload_profile_identity, assess_cutoff_clock, request_cutoffs, summarize
    from .pr13_audit_archive import read_owned_audits, validate_storage
    from .pr13_resource_policy import latency_causes, memory_causes, disk_causes
except ImportError:
    from pr13_distributed_load import joint_overlap, clock_envelope
    from pr13_runtime_evidence import coverage, sampling_integrity, reconcile_cycles, finite
    from gameplay_load_validation import workload_profile_identity, assess_cutoff_clock, request_cutoffs, summarize
    from pr13_audit_archive import read_owned_audits, validate_storage
    from pr13_resource_policy import latency_causes, memory_causes, disk_causes


OFFICIAL_ENGINE = {
    'windows': 'ab1824f85bfd8e0e4128182c000c4003a3e042245b2967848d089b2a04b22424',
    'linux': '8d106cbe6144c2dc7e881d61d2429c1a8a76e6b22ef48bd5e48dcf934953f71e',
}
ENGINE_VERSION = '4.7.2.stable.official.ed1daf0bf'
SERVER_IMAGE = 'sha256:e647601a9fa6dd7e1934907699f7d9c58c0965da2116b1325b826ba458ee6a3e'
SOURCE_FILES = (
    'tools/gameplay_load_test.py', 'tools/cloud_load_test.py',
    'tools/pr13_resource_policy.py', 'tools/pr13_status_snapshot.py',
    'tools/pr13_native_package.py', 'tools/gameplay_load_validation.py',
    'client/tests/gameplay_load_client.gd', 'client/state/game_store.gd',
    'client/network/gateway.gd', 'client/network/reusable_http_client.gd',
    'tools/pr13_runtime_evidence.py', 'tools/pr13_audit_archive.py',
    'client/data/catalog.json', 'tools/pr13_local_network.py',
    'client/ui/card_details.gd', 'client/state/element_rules.gd',
    'protocol/realtime/v1/realtime.proto',
)
REQUIRED_DIMENSIONS = {'execution', 'evidence', 'load', 'performance', 'cleanup'}


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def strict_json(data):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            require(key not in result, 'duplicate_json_key')
            result[key] = value
        return result
    def invalid(_):
        raise ValueError('nonfinite_json_constant')
    return json.loads(data.decode('utf-8'), object_pairs_hook=unique, parse_constant=invalid)


def load_git_reference(repository, head):
    """Hash actual immutable Git blob contents, not caller-provided hash claims."""
    require(isinstance(head, str) and len(head) == 40 and all(c in '0123456789abcdef' for c in head), 'invalid_source_head')
    flags = getattr(subprocess, 'CREATE_NO_WINDOW', 0) | getattr(subprocess, 'BELOW_NORMAL_PRIORITY_CLASS', 0)
    env = dict(os.environ, GIT_TERMINAL_PROMPT='0', GIT_NO_LAZY_FETCH='1')
    def git(*args):
        r = subprocess.run(['git', *args], cwd=repository, env=env, capture_output=True, timeout=60, creationflags=flags)
        require(r.returncode == 0, 'frozen_git_object_unavailable')
        return r.stdout
    require(git('rev-parse', '--verify', head + '^{commit}').decode().strip() == head, 'frozen_commit_mismatch')
    tree = {}
    for record in git('ls-tree', '-r', '-z', head, '--', 'client', 'tools', 'protocol').split(b'\0'):
        if not record:
            continue
        meta, name = record.split(b'\t', 1)
        mode, kind, oid = meta.decode().split()
        path = name.decode()
        if path.startswith('client/') or path in SOURCE_FILES:
            require(kind == 'blob' and mode in ('100644', '100755'), 'nonregular_frozen_input')
            tree[path] = oid
    require(set(SOURCE_FILES) <= set(tree) and 'client/project.godot' in tree, 'incomplete_frozen_source')
    hashes = {}
    child = subprocess.Popen(['git', 'cat-file', '--batch'], cwd=repository, env=env,
                             stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                             creationflags=flags)
    try:
        for oid in dict.fromkeys(tree.values()):
            child.stdin.write((oid + '\n').encode())
            child.stdin.flush()
            header = child.stdout.readline().decode().split()
            require(len(header) == 3 and header[:2] == [oid, 'blob'], 'invalid_frozen_blob_header')
            remaining = int(header[2])
            h = hashlib.sha256()
            while remaining:
                data = child.stdout.read(min(1048576, remaining))
                require(bool(data), 'truncated_frozen_blob')
                h.update(data)
                remaining -= len(data)
            require(child.stdout.read(1) == b'\n', 'invalid_frozen_blob_boundary')
            hashes[oid] = h.hexdigest()
        child.stdin.close()
        require(child.wait(timeout=30) == 0, 'frozen_blob_reader_failed')
    finally:
        if not child.stdin.closed:
            child.stdin.close()
        if child.poll() is None:
            child.kill()
            child.wait(timeout=10)
        child.stdout.close()
    return dict(head=head, client_tree=git('rev-parse', head + ':client').decode().strip(),
                controls={p: hashes[tree[p]] for p in SOURCE_FILES},
                client={p: hashes[o] for p, o in tree.items() if p.startswith('client/')})


class Capture:
    """Read only sealed, bounded, regular original files below one capture root."""
    def __init__(self, root, manifest):
        self.root = Path(root).resolve()
        require(self.root.is_dir() and not Path(root).is_symlink(), 'invalid_capture_root')
        require(isinstance(manifest, list) and 1 <= len(manifest) <= 16384, 'invalid_capture_manifest')
        self.files = {}
        total = 0
        for row in manifest:
            name = row['path']
            path = PurePosixPath(name)
            require(isinstance(name, str) and name and not path.is_absolute() and '..' not in path.parts and '\\' not in name,
                    'unsafe_capture_path')
            require(name not in self.files and type(row['bytes']) is int and 0 <= row['bytes'] <= 64 * 1024**2,
                    'duplicate_or_unbounded_capture_file')
            require(isinstance(row['sha256'], str) and len(row['sha256']) == 64, 'invalid_capture_digest')
            self.files[name] = row
            total += row['bytes']
        require(total <= 2 * 1024**3, 'capture_total_size_exceeded')

    def path(self, name):
        require(name in self.files, 'original_not_in_capture_manifest')
        path = self.root / name
        require(path.resolve().is_relative_to(self.root) and path.is_file() and not path.is_symlink(), 'unsafe_original_file')
        return path

    def raw(self, name):
        path = self.path(name)
        before = path.stat()
        row = self.files[name]
        require(before.st_size == row['bytes'], 'original_size_mismatch')
        data = path.read_bytes()
        after = path.stat()
        require((before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) ==
                (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns), 'original_changed_during_read')
        require(hashlib.sha256(data).hexdigest() == row['sha256'], 'original_digest_mismatch')
        return data

    def json(self, name):
        return strict_json(self.raw(name))

    def verify_all(self):
        for name in self.files:
            self.raw(name)


def same_path(a, b, platform):
    if not isinstance(a, str) or not isinstance(b, str):
        return False
    return ntpath.normcase(ntpath.normpath(a)) == ntpath.normcase(ntpath.normpath(b)) if platform == 'windows' else a == b


def _frame_valid(frame):
    return (isinstance(frame, dict) and finite(frame.get('engine_max_fps')) and frame['engine_max_fps'] == 0 and
            type(frame.get('process_frames')) is int and frame['process_frames'] > 0 and
            finite(frame.get('observed_ms')) and frame['observed_ms'] > 0)


def _client_inputs_match(actual, reference):
    require(isinstance(actual, dict) and all(actual.get(p) == h for p, h in reference.items()),
            'frozen_client_input_missing_or_changed')
    require(all(p in reference or (p.endswith('.uid') and p[:-4] in reference) for p in actual),
            'undeclared_client_input')


def _final_utc_cutoff(report):
    # Original coordinator reports persist final UTC in their qualified clock
    # capture, not in a top-level final_cutoff_ms field.
    quality = report['cutoff_clock_quality']
    cutoffs = quality['cutoffs_unix_ms']
    require(quality['qualified'] is True and not quality['evidence_errors'] and
            cutoffs['start'] == report['started'] * 1000 and cutoffs['stop'] == report['stop_issued_ms'] and
            finite(cutoffs['final']) and cutoffs['final'] >= cutoffs['stop'], 'inconsistent_original_cutoff_capture')
    if 'cycle_cutoffs' in report:
        require(report['cycle_cutoffs']['final_ms'] == cutoffs['final'] and
                report['cycle_cutoffs']['stop_ms'] == cutoffs['stop'], 'contradictory_cycle_cutoff_capture')
    if 'request_distributions' in report:
        require(report['request_distributions']['cutoffs_unix_ms'] == cutoffs, 'contradictory_request_cutoff_capture')
    return cutoffs['final']


def _replay_audits(processes, final_clients, report):
    events, errors = read_owned_audits(processes, final_clients)
    try:
        require(not errors, 'original_audit_stream_invalid')
        final_ms = _final_utc_cutoff(report)
        clock = assess_cutoff_clock(report['started'] * 1000, report['stop_issued_ms'], final_ms,
            start_monotonic_ms=report['started_monotonic_ms'],
            stop_monotonic_ms=report['stop_issued_monotonic_ns'] / 1000000,
            final_monotonic_ms=report['final_cutoff_monotonic_ns'] / 1000000)
        require(clock['qualified'], 'original_cutoff_clock_unqualified')
        cycles = reconcile_cycles(events, report['stop_issued_ms'], final_ms, cutoff_clock_qualified=True)
        requests = request_cutoffs(events, report['stop_issued_ms'], final_ms,
                                   started_ms=report['started'] * 1000, cutoff_clock_qualified=True)
        require(not cycles['evidence_errors'] and not requests['evidence_errors'], 'original_audit_replay_failed')
        require(all(r['cycles_completed'] == cycles['final']['cycles_by_client'].get(r['client_id'], 0)
                    for r in final_clients), 'native_cycle_watermark_disagreement')
        require(requests['final']['invalid_metric_count'] == 0, 'invalid_raw_request_metric')
        for family in ('http', 'realtime'):
            count = sum(s['window'][family]['count'] for s in report['samples']) + report['tail_window'][family]['count']
            require(count == requests['final'][family]['count'], 'request_population_disagreement')
        latencies = dict(http=[], realtime=[])
        for row in events:
            kind = row.get('type')
            if kind in latencies and report['started'] * 1000 <= row['at_unix_ms'] <= report['stop_issued_ms']:
                if kind != 'http' or row.get('result') != 'cancelled':
                    latencies[kind].append(row['duration_ms'])
        require(all(len(latencies[k]) == requests['running'][k]['count'] for k in latencies),
                'raw_running_latency_population_disagreement')
        requests['_raw_running_latencies'] = latencies
        return requests
    finally:
        if hasattr(events, 'close'):
            events.close()


def audit_cohort(capture, spec, partition, reference):
    capture.verify_all()
    meta = capture.json('host-capture.original.json')
    require(meta['spec_sha256'] == hashlib.sha256(canonical(spec)).hexdigest() and meta['host_id'] == partition['host_id'],
            'foreign_cohort_spec')
    report_name = meta['report_file']
    report = capture.json(report_name)
    directory = PurePosixPath(report_name).parent
    contract, samples = report['load_contract'], report['samples']
    count, platform = partition['clients'], partition['platform']
    require(platform in OFFICIAL_ENGINE and count > 0 and type(count) is int, 'invalid_partition')
    expected = dict(profile='active-hold', hero_class='Guardian', strategy='baseline_all_hand',
                    strategy_seed=partition['seed_start'], client_max_fps=None, client_runtime='editor',
                    target_online=count, target_active=partition.get('target_active', count), maximum_run_seconds=960,
                    minimum_window=720, minimum_continuous=120, minimum_coverage=.95,
                    maximum_gap=20.0, minimum_command_rate=1, http_p95_limit_ms=1500,
                    command_p95_limit_ms=2000, health_limit_ms=5000,
                    minimum_generator_memory_bytes=partition['memory_floor_bytes'],
                    minimum_cloud_memory_bytes=500000000, minimum_cloud_disk_percent=5.0,
                    cycle_limit_seconds=240, http_transport='reusable')
    require(all(k in contract and contract[k] == v for k, v in expected.items()), 'changed_native_workload_contract')
    require(report['clients'] == count and report['group_size'] == count and report['groups'] == 1,
            'cohort_count_mismatch')
    require(report['stop_reason'] == 'duration_limit' and report['outcome']['passed'] is True and
            report['outcome']['exit_code'] == 0, 'original_cohort_did_not_pass')
    require(report['stop_issued_monotonic_ns'] / 1000000 - report['started_monotonic_ms'] >= 960000,
            'cohort_stopped_before_registered_duration')
    dims = report['result_dimensions']
    require(set(dims['applicable']) == REQUIRED_DIMENSIONS and
            all(dims['dimensions'][k] == 'Passed' for k in REQUIRED_DIMENSIONS), 'original_dimension_not_passed')
    require(all(report[k] is True for k in ('load_window_verified', 'process_cleanup_complete', 'business_cleanup_verified')),
            'original_load_or_cleanup_unverified')
    require(all(not report[k] for k in ('audit_read_errors', 'final_status_read_errors', 'native_final_report_errors',
                                       'forced_termination_pids')) and report['final_audit_lost_count'] == 0,
            'original_evidence_failure_retained')
    require(report['final_read_errors'] == 0 and report['tail_lost_event_count'] == 0 and
            report['post_stop_failure'] is False and report['final_audit_count_invalid'] is False,
            'original_terminal_evidence_failed')
    source = report['source']
    require(source['git_commit'] == reference['head'] and source['sha256'] == reference['controls'], 'generator_source_mismatch')
    active = source['active_client_project']
    require(same_path(active['path'], partition['project_path'], platform), 'foreign_client_project')
    actual = active['input_hashes']
    _client_inputs_match(actual, reference['client'])
    identity_contract = {k: v for k, v in contract.items() if k not in
                         ('workload_profile_id', 'workload_profile_qualified', 'workload_profile_missing_reason')}
    identity = workload_profile_identity(identity_contract, source['sha256'])
    require(identity['qualified'] and identity['workload_profile_id'] == contract['workload_profile_id'], 'workload_identity_mismatch')
    stop, start = report['stop_issued_ms'] / 1000, report['started']
    load = coverage(samples, start=max(start, stop - 720), end=stop, target_online=count,
                    target_active=partition.get('target_active', count),
                    minimum_window=720, minimum_continuous=120, minimum_coverage=.95, maximum_gap=20)
    require(load['passed'], 'original_load_coverage_replay_failed')
    sampling = sampling_integrity(samples, report['started_monotonic_ms'],
                                  report['stop_issued_monotonic_ns'] / 1000000, 20)
    require(sampling['passed'], 'original_sampling_replay_failed')
    engine = capture.json(meta['engine_file'])
    require(engine['before_sha256'] == engine['after_sha256'] == OFFICIAL_ENGINE[platform] and
            engine['version'] == ENGINE_VERSION, 'unrecognized_or_changed_native_engine')
    require(same_path(engine['requested_path'], partition['engine_path'], platform), 'foreign_native_executable')
    require(engine['source_controls_after'] == reference['controls'], 'generator_source_changed_during_run')
    _client_inputs_match(engine['client_inputs_after'], reference['client'])
    require(engine['after_hash_scope'] == ('same_engine_file_after_run' if platform == 'windows' else
                                          'same_readonly_image_after_run'), 'engine_after_hash_scope_unqualified')
    if platform == 'linux':
        require(engine['readonly_image_root'] is True, 'native_image_was_writable')
    inspections = capture.json(meta['process_file'])
    require(len(inspections['processes']) == count, 'native_OS_process_inspection_missing')
    inspect_by = {p['pid']: p for p in inspections['processes']}
    receipts = report['launch_receipts']
    require(len(receipts) == count and len(inspect_by) == count, 'duplicate_or_missing_native_process')
    primary_by = {r['client_id']: r for r in report['native_final_reports']}
    final_by = {r['client_id']: r for r in report['final_clients']}
    require(len(report['native_final_reports']) == len(report['final_clients']) == count and
            len(primary_by) == len(final_by) == count, 'missing_final_native_population')
    exits = {r['client_id']: r['after_stop'] for r in report['process_exits']}
    require(len(report['process_exits']) == len(exits) == count and all(type(c) is int and c == 0 for c in exits.values()) and
            all(r['before_stop'] is None for r in report['process_exits']), 'native_process_exit_failure')
    processes, users, clients, epochs, pids, seeds = [], set(), set(), set(), set(), set()
    expected_command = [partition['engine_path'], '--headless', '--audio-driver', 'Dummy',
                        '--path', partition['project_path'], 'res://tests/gameplay_load_client.tscn']
    for receipt in receipts:
        cid, pid, epoch = receipt['client_id'], receipt['pid'], receipt['process_epoch']
        require(isinstance(cid, str) and cid and isinstance(epoch, str) and epoch and
                type(pid) is int and pid > 0 and pid not in pids and cid not in clients and epoch not in epochs,
                'reused_native_identity')
        clients.add(cid); pids.add(pid); epochs.add(epoch); seeds.add(receipt['strategy_seed'])
        require(receipt['command'] == expected_command and receipt['client_max_fps'] is None and
                receipt['server_origin'] == partition['server_origin'] and receipt['client_runtime'] == 'editor',
                'changed_native_launch_or_target')
        require(receipt['hero_class'] == 'Guardian' and receipt['strategy'] == 'baseline_all_hand', 'changed_actor_profile')
        native_name = str(directory / receipt['report_file'])
        require(PurePosixPath(receipt['report_file']).name == receipt['report_file'], 'unsafe_native_report_name')
        raw = capture.raw(native_name)
        native = strict_json(raw)
        primary, final = primary_by[cid], final_by[cid]
        require(hashlib.sha256(raw).hexdigest() == primary['_primary_report_sha256'] and len(raw) == primary['_primary_report_bytes'],
                'native_primary_digest_disagreement')
        require(all(native.get(k) == receipt[k] for k in ('pid', 'client_id', 'process_epoch', 'run_id', 'hero_class', 'strategy', 'strategy_seed')),
                'native_report_foreign_context')
        require(native['load_profile'] == 'active-hold' and native['cycle_limit_seconds'] == 240 and
                native['outcome'] in ('completed', 'cancelled') and not native['errors'] and native['audit_lost_count'] == 0 and
                native['cleanup']['state'] == 'Passed', 'native_business_or_cleanup_failure')
        require(all(native[k] == final[k] for k in ('cycles_completed', 'event_seq_max', 'audit_lost_count', 'errors', 'cleanup', 'audit_storage')),
                'native_final_heartbeat_disagreement')
        require(_frame_valid(native['generator_frame_clock']), 'native_uncapped_frame_clock_missing')
        require(native['event_seq_max'] > 0 and isinstance(native['checks'], list) and
                all(c.get('passed') is True for c in native['checks']) and
                {'realtime_connected', 'login_and_bootstrap', 'hero_class_confirmed', 'room_started'} <=
                {c['name'] for c in native['checks']}, 'native_authenticated_room_checks_missing')
        require(isinstance(native['user_id'], str), 'invalid_server_user_identity')
        user = uuid.UUID(native['user_id']).hex
        require(user != '0' * 32 and user not in users, 'duplicate_or_empty_server_user')
        users.add(user)
        process = inspect_by[pid]
        require(process['command'] == receipt['command'] and same_path(process['exe'], engine['real_path'], platform),
                'OS_process_is_not_the_launched_native')
        env = process['load_environment']
        values = dict(FANTASYCARD_LOAD_CLIENT_ID=cid, FANTASYCARD_LOAD_RUN_ID=receipt['run_id'],
                      FANTASYCARD_LOAD_PROCESS_EPOCH=epoch, FANTASYCARD_LOAD_PROFILE='active-hold',
                      FANTASYCARD_LOAD_MAX_CYCLES='0', FANTASYCARD_LOAD_SEED=str(receipt['strategy_seed']),
                      FANTASYCARD_LOAD_HERO_CLASS='Guardian', FANTASYCARD_LOAD_STRATEGY='baseline_all_hand',
                      FANTASYCARD_LOAD_HOLD_SECONDS='720', FANTASYCARD_LOAD_RUN_SECONDS='960',
                      FANTASYCARD_LOAD_CYCLE_LIMIT_SECONDS='240', FANTASYCARD_LOAD_HTTP_TRANSPORT='reusable')
        require(all(env.get(k) == v for k, v in values.items()), 'OS_process_owner_environment_mismatch')
        origin = urllib.parse.urlsplit(env['FANTASYCARD_SERVER_URL'])
        require({'scheme': origin.scheme, 'host': origin.hostname, 'port': origin.port} == receipt['server_origin']
                and origin.path in ('', '/') and not origin.query, 'OS_process_targets_another_backend')
        if platform == 'windows':
            require(process['priority_class'] == 0x4000 and process['cpu_affinity'] and
                    set(process['cpu_affinity']) <= set(partition['cpu_affinity']), 'Windows_silent_resource_policy_changed')
        storage = native['audit_storage']
        require(validate_storage(storage), 'invalid_primary_audit_storage')
        for index in range(storage['segment_count']):
            suffix = '' if index == 0 else '.' + str(index)
            capture.raw(native_name + '.telemetry' + suffix + '.jsonl')
        processes.append(dict(client_id=cid, run_id=receipt['run_id'], process_epoch=epoch,
                              report=capture.path(native_name)))
    require(seeds == set(range(partition['seed_start'], partition['seed_start'] + count)), 'cohort_seed_partition_mismatch')
    require(len({r['run_id'] for r in receipts}) == 1, 'mixed_coordinator_run_ids')
    run_id = receipts[0]['run_id']
    streaks = {}
    for s in samples:
        require(s['run_id'] == run_id and not s['window']['invalid_metric_count'] and
                not s['window']['lost_event_count'] and not s['window']['audit_lost_count'], 'invalid_native_window_evidence')
        for frame in s['generator']['native_frame_observations']:
            if 'engine_max_fps' in frame:
                require(finite(frame['engine_max_fps']) and frame['engine_max_fps'] == 0, 'native_FPS_override_observed')
        require(finite(s['resources'].get('cpu')) and finite(s['resources'].get('actor_wait')),
                'original_server_metric_missing')
        causes = latency_causes(s['window'], s['health'], 1500, 2000, 5000)
        causes += memory_causes(s['resources'], s['generator'], partition['memory_floor_bytes'], 500000000)
        causes += disk_causes(s['resources'], 5)
        if s['resources']['cpu'] > 85:
            causes.append('cpu_redline')
        if s['resources']['actor_wait'] > 100:
            causes.append('actor_wait_redline')
        if s['window']['realtime']['count'] >= 10 and s['window']['command_error_rate'] >= .1:
            causes.append('command_rejections_redline')
        if s['window']['sample_count'] >= 20 and s['window']['error_rate'] >= .1:
            causes.append('http_errors_redline')
        for key in set(streaks) | set(causes):
            streaks[key] = streaks.get(key, 0) + 1 if key in causes else 0
        require(not any(n >= 3 for n in streaks.values()), 'original_sustained_redline_replay_failed')
    requests = _replay_audits(processes, report['final_clients'], report)
    require(requests['running']['http']['count'] >= 20 and requests['running']['realtime']['count'] >= 10,
            'insufficient_original_latency_population')
    supervisor = capture.json(meta['supervisor_file'])
    require(supervisor['terminal']['ok'] is True and supervisor['terminal']['guard_stop'] is None,
            'host_supervisor_did_not_pass')
    require(supervisor['resources'] and all(finite(r['memory_available_bytes']) and
            r['memory_available_bytes'] >= partition['memory_floor_bytes'] for r in supervisor['resources']), 'host_memory_reserve_breached')
    if platform == 'linux':
        require(all(finite(r['root_disk_free_bytes']) and r['root_disk_free_bytes'] >= 3000000000
                    for r in supervisor['resources']), 'cloud_absolute_disk_floor_breached')
    resource_points = [r['monotonic_ms'] for r in supervisor['resources']]
    require(all(finite(p) for p in resource_points) and
            resource_points[0] <= report['started_monotonic_ms'] and
            resource_points[-1] >= report['final_cutoff_monotonic_ns'] / 1000000 and
            all(0 < b - a <= 5000 for a, b in zip(resource_points, resource_points[1:])),
            'supervisor_resource_observation_gap')
    clocks = capture.json(meta['clock_file'])
    envelope = clock_envelope(clocks, samples, host_id=partition['host_id'],
                              window_start_ms=spec['window_start_ms'], window_end_ms=spec['window_end_ms'])
    require(spec['registered_at_reference_ms'] < start * 1000 + envelope['lower_ms'], 'study_registered_after_cohort_start')
    require(inspections['observed_unix_ms'] + envelope['upper_ms'] < spec['window_start_ms'], 'native_inspection_not_before_window')
    require(max(r['started_at_monotonic_ms'] for r in receipts) <= inspections['observed_monotonic_ms'] <
            report['stop_issued_monotonic_ns'] / 1000000, 'native_inspection_outside_launched_run')
    frames = []
    for s in samples:
        row = dict(s)
        observations = s['generator']['native_frame_observations']
        valid = len(observations) == count and {f['client_id'] for f in observations} == clients and all(_frame_valid(f) for f in observations)
        row['workload_failure'] = row['workload_failure'] or not valid
        frames.append(row)
    return dict(host_id=partition['host_id'], clients=count, target_active=partition.get('target_active', count),
                samples=frames, clock_probes=clocks,
                users=users, pids=pids, epochs=epochs, client_ids=clients, seeds=seeds,
                run_id=run_id, request_distributions=requests)


def assess_captures(spec, captures, reference, backend_before, backend_after):
    """Capacity verdict for this study only; never promotes whole-project status."""
    result = dict(capacity_accepted=False, whole_project_accepted=False, evidence_errors=[])
    try:
        require(spec['source_head'] == reference['head'] and type(spec['target_clients']) is int and spec['target_clients'] == 50 and
                spec['reference_host_id'] == 'windows', 'wrong_registered_study')
        require(type(spec['world_budget']) is int and 1 <= spec['world_budget'] <= 300,
                'world_budget_exceeds_user_limit')
        partitions = spec['partitions']
        population = spec.get('target_online_clients', 50)
        require(type(population) is int and population in (50, 60), 'unregistered_online_population')
        expected_partitions = {'windows': (25, 25), 'cloud': (25, 25)} if population == 50 else {
            'windows': (32, 27), 'cloud': (28, 23)}
        require(population == 50 or spec.get('workload_profile') == 'full-native60-for50active',
                'stronger_population_profile_not_declared')
        require(len(partitions) == len(captures) == 2 and {p['host_id'] for p in partitions} == {'windows', 'cloud'} and
                all(type(p['clients']) is int and type(p.get('target_active', p['clients'])) is int and
                    (p['clients'], p.get('target_active', p['clients'])) == expected_partitions[p['host_id']]
                    for p in partitions), 'wrong_full50_partitions')
        require(next(p for p in partitions if p['host_id'] == 'windows')['memory_floor_bytes'] >= 6442450944 and
                next(p for p in partitions if p['host_id'] == 'cloud')['memory_floor_bytes'] >= 500000000, 'host_reserve_reduced')
        fields = ('app_id', 'app_image', 'app_started_at', 'environment_sha256', 'pg_id', 'database',
                  'study_id', 'owner', 'read_only_app')
        require(all(backend_before[k] == backend_after[k] for k in fields) and
                backend_before['app_image'] == SERVER_IMAGE and backend_before['study_id'] == spec['study_id'] and
                backend_before['owner'] == spec['owner'] and backend_before['read_only_app'] is True and
                type(backend_before['initial_humans']) is int and backend_before['initial_humans'] == 0 and
                type(backend_before['initial_matches']) is int and
                backend_before['initial_matches'] == spec.get('warmup_matches', 0),
                'backend_not_same_fresh_isolated_server')
        require(type(backend_after['final_humans']) is int and type(backend_after['pending_holds']) is int and
                backend_after['final_humans'] == 0 and backend_after['pending_holds'] == 0, 'backend_cleanup_incomplete')
        require(type(backend_after['matches']) is int and
                backend_before['initial_matches'] <= backend_after['matches'] <= spec['world_budget'],
                'actual_world_budget_exceeded')
        audited = [audit_cohort(captures[p['host_id']], spec, p, reference) for p in partitions]
        require(audited[0]['run_id'] != audited[1]['run_id'] and not audited[0]['users'] & audited[1]['users'] and
                not audited[0]['epochs'] & audited[1]['epochs'], 'cohorts_reuse_runtime_or_user_identity')
        users = set.union(*(r['users'] for r in audited))
        excluded = {uuid.UUID(v).hex for v in spec.get('warmup_user_ids', [])}
        require(not excluded & users and
                {uuid.UUID(v).hex for v in backend_before.get('settled_user_ids', [])} == excluded,
                'warmup_participants_not_explicitly_closed_before_study')
        require(len(users) == population and {uuid.UUID(v).hex for v in backend_after['settled_user_ids']} == users | excluded,
                'server_participants_do_not_match_all50_native_users')
        seeds = [s for r in audited for s in r['seeds']]
        require(len(set(seeds)) == population and set(seeds) == set(range(spec['seed_start'], spec['seed_start'] + population)),
                'not_original_full50_seed_distribution')
        overlap = joint_overlap(audited, spec)
        require(overlap['joint_overlap_passed'], 'shared_full50_window_not_verified')
        pooled = {family:summarize([v for r in audited for v in r['request_distributions']['_raw_running_latencies'][family]])
                  for family in ('http', 'realtime')}
        require(pooled['http']['count'] >= 40 and pooled['realtime']['count'] >= 20 and
                pooled['http']['p95_ms'] <= 1500 and pooled['realtime']['p95_ms'] <= 2000,
                'pooled_raw_latency_redline')
        for r in audited:
            r['request_distributions'].pop('_raw_running_latencies')
        result.update(capacity_accepted=True, participants=population, target_active=50, overlap=overlap,
                      per_host_latency={r['host_id']:r['request_distributions']['running'] for r in audited},
                      pooled_running_latency=pooled,
                      original_single_generator_failure_not_reclassified=True)
    except (OSError, KeyError, TypeError, ValueError, RecursionError, StopIteration) as error:
        result['evidence_errors'].append(str(error) if isinstance(error, ValueError) else type(error).__name__)
    return result


def main(argv=None):
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, required=True, help='Captured study specification, file seals and backend snapshots')
    parser.add_argument('--source-repository', type=Path, required=True, help='Real Git object database containing the preregistered commit')
    parser.add_argument('--output', type=Path, required=True, help='New derived adjudication JSON; never overwrites an original')
    args = parser.parse_args(argv)
    require(args.input.stat().st_size <= 64 * 1024**2, 'study_input_too_large')
    raw = args.input.read_bytes()
    try:
        data = strict_json(raw)
        spec = data['spec']
        reference = load_git_reference(args.source_repository, spec['source_head'])
        captures = {}
        for c in data['captures']:
            require(c['host_id'] not in captures, 'duplicate_capture_host')
            root = Path(c['root'])
            root = root if root.is_absolute() else args.input.parent / root
            captures[c['host_id']] = Capture(root, c['files'])
        result = assess_captures(spec, captures, reference, data['backend_before'], data['backend_after'])
        result.update(source_head=reference['head'], frozen_client_tree=reference['client_tree'])
    except (OSError, KeyError, TypeError, ValueError, RecursionError) as error:
        result = dict(capacity_accepted=False, whole_project_accepted=False,
                      evidence_errors=[str(error) if isinstance(error, ValueError) else type(error).__name__])
    result.update(algorithm_version='distributed-full-native-capacity-v1',
                  captured_input_sha256=hashlib.sha256(raw).hexdigest())
    with args.output.open('xb') as out:
        out.write(json.dumps(result, indent=2, allow_nan=False).encode() + b'\n')
    return 0 if result['capacity_accepted'] else 3


if __name__ == '__main__':
    raise SystemExit(main())
