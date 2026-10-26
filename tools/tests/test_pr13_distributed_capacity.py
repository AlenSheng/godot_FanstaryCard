"""Synthetic counterexamples for the joint verifier, not live capacity evidence."""
import copy
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
import uuid

from tools.pr13_distributed_capacity import (Capture, ENGINE_VERSION, OFFICIAL_ENGINE,
    SERVER_IMAGE, SOURCE_FILES, NORTH_AMERICA_LATENCY_PROFILE, assess_captures,
    canonical, latency_policy, load_git_reference, strict_json)
from tools.gameplay_load_validation import aggregate_window, workload_profile_identity
from tools.tests.test_pr13_distributed_load import BASE, probe
from tools.pr13_authority_transitions import AUTHORITY_TRANSITION_POLICY, POLICY_SOURCE_FILES, review_authority_refusals
from tools.pr13_authority_transitions import CAPACITY_RECOVERY_POLICY_V2
from tools.pr13_distributed_load import GLOBAL50_AGGREGATE_PROFILE, AGGREGATE_LATENCY_PROFILE, THREE_HOST100_PROFILE


def identifier(text):
    return uuid.uuid5(uuid.NAMESPACE_URL, text).hex


def json_bytes(value):
    return (json.dumps(value, allow_nan=False, sort_keys=True) + '\n').encode()


class SyntheticStudy:
    def __init__(self, root, *, cloud_seed_start=None, stronger_population=False,
                 latency_profile=None, http_ms=10, command_ms=10, target_clients=50, global_surplus=False, aggregate=False,
                 three_host100=False):
        self.root = Path(root)
        assert target_clients in (50, 100) and (not stronger_population or target_clients == 50)
        assert not global_surplus or target_clients == 50 and not stronger_population
        assert not aggregate or target_clients == 50 and not stronger_population and not global_surplus
        self.http_ms, self.command_ms = http_ms, command_ms
        self.reference = dict(head='1' * 40,
            controls={p:hashlib.sha256(p.encode()).hexdigest() for p in SOURCE_FILES},
            client={'client/project.godot':'2' * 64, 'client/tests/gameplay_load_client.gd':'3' * 64})
        assert not three_host100 or target_clients == 100 and not (stronger_population or global_surplus or aggregate)
        if global_surplus or aggregate or three_host100:
            source_root=Path(__file__).resolve().parents[2]
            self.reference['controls'].update({p:hashlib.sha256((source_root/p).read_bytes()).hexdigest() for p in POLICY_SOURCE_FILES})
        partitions = []
        hosts = [('windows', 'windows', 0), ('cloud', 'linux', 32 if stronger_population else target_clients // 2)]
        if three_host100:
            hosts = [('windows','windows',0), ('sjh','windows',30), ('cloud','linux',80)]
        for host, platform, offset in hosts:
            count = (32 if host == 'windows' else 28) if stronger_population else target_clients // 2
            if global_surplus:
                count, offset = (35, 0) if host == 'windows' else (25, 35)
            if aggregate:
                count, offset = (40, 0) if host == 'windows' else (20, 40)
            if three_host100:
                count = {'windows':30,'sjh':50,'cloud':20}[host]
            partitions.append(dict(host_id=host, platform=platform, clients=count,
                seed_start=20260930 + offset, memory_floor_bytes=6442450944 if platform == 'windows' else 500000000,
                engine_path='G:\\engine\\godot.exe' if platform == 'windows' else '/usr/local/bin/godot',
                project_path='G:\\fixture\\client' if platform == 'windows' else '/fixture/client',
                server_origin=dict(scheme='http', host='127.0.0.1', port=18641 if offset == 0 else 18541),
                cpu_affinity=[12, 13, 14, 15]))
            if stronger_population:
                partitions[-1]['target_active'] = 27 if host == 'windows' else 23
            if global_surplus:
                partitions[-1]['target_active'] = 25 if host == 'windows' else 15
            if aggregate:
                partitions[-1]['target_active'] = 30 if host == 'windows' else 10
                partitions[-1]['target_online'] = partitions[-1]['target_active']
        if cloud_seed_start is not None:
            partitions[1]['seed_start'] = cloud_seed_start
        self.spec = dict(study_id=identifier('study'), owner=identifier('owner'), source_head=self.reference['head'], world_budget=300,
            target_clients=target_clients, reference_host_id='windows', seed_start=20260930, partitions=partitions,
            registered_at_reference_ms=(BASE - 30) * 1000,
            window_start_ms=(BASE + 300) * 1000, window_end_ms=(BASE + 900) * 1000)
        if stronger_population:
            self.spec.update(target_online_clients=60, workload_profile='full-native60-for50active')
        if global_surplus:
            self.spec.update(target_online_clients=60, workload_profile='full-native60-global50-win35-cloud25',
                             authority_transition_policy=AUTHORITY_TRANSITION_POLICY)
        if aggregate:
            self.spec.update(target_online_clients=50, native_supply_clients=60, workload_profile=GLOBAL50_AGGREGATE_PROFILE,
                authority_transition_policy=CAPACITY_RECOVERY_POLICY_V2, latency_profile=AGGREGATE_LATENCY_PROFILE,
                latency_warning_budget_fraction=.05, prior_capacity_worlds=253, combined_capacity_world_cap=300, world_budget=47)
        if three_host100:
            self.spec.update(workload_profile=THREE_HOST100_PROFILE, target_online_clients=100,
                authority_transition_policy=CAPACITY_RECOVERY_POLICY_V2, latency_profile=AGGREGATE_LATENCY_PROFILE,
                latency_warning_budget_fraction=.05, prior_capacity_worlds=301, world_budget=100)
            helper='tools/pr13_three_host_windows.py'
            self.reference['controllers']={helper:hashlib.sha256((Path(__file__).resolve().parents[2]/helper).read_bytes()).hexdigest()}
            for partition in partitions:
                if partition['platform']=='windows':partition['machine_name']='SJH' if partition['host_id']=='sjh' else 'other-windows'
        if latency_profile is not None:
            self.spec['latency_profile'] = latency_profile
        self.report_names, self.files, self.roots, self.native_names, self.users = {}, {}, {}, {}, []
        for p in partitions:
            self.build_host(p)
        self.before = dict(app_id='a' * 64, app_image=SERVER_IMAGE, app_started_at='fixture-start',
            environment_sha256='4' * 64, pg_id='b' * 64, database='ready_stop_unit',
            study_id=self.spec['study_id'], owner=self.spec['owner'], read_only_app=True,
            initial_humans=0, initial_matches=0, settled_user_ids=[])
        self.after = dict(self.before, final_humans=0, pending_holds=0, matches=15 if aggregate else 13, settled_user_ids=list(self.users))

    def write(self, host, name, data):
        p = self.roots[host] / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)
        self.files[host][name] = dict(path=name, bytes=len(data), sha256=hashlib.sha256(data).hexdigest())

    def put(self, host, name, value):
        self.write(host, name, json_bytes(value))

    def get(self, host, name):
        return json.loads((self.roots[host] / name).read_text(encoding='utf-8'))

    def report(self, host):
        return self.get(host, self.report_names[host])

    def put_report(self, host, value):
        self.put(host, self.report_names[host], value)

    def bind_spec(self):
        for host in self.roots:
            m = self.get(host, 'host-capture.original.json')
            m['spec_sha256'] = hashlib.sha256(canonical(self.spec)).hexdigest()
            self.put(host, 'host-capture.original.json', m)

    def change_native(self, host, index, change):
        name = self.native_names[host][index]
        n = self.get(host, name)
        change(n)
        raw = json_bytes(n)
        self.write(host, name, raw)
        r = self.report(host)
        row = r['native_final_reports'][index]
        row['_primary_report_sha256'] = hashlib.sha256(raw).hexdigest()
        row['_primary_report_bytes'] = len(raw)
        self.put_report(host, r)

    def build_host(self, p):
        host = p['host_id']; platform = p['platform']; skew = 0 if host == 'windows' else 5
        count = p['clients']
        mono = 2_000_000 if host == 'windows' else 1_000_000
        start = BASE + skew; run = identifier(host)
        self.roots[host] = self.root / host; self.roots[host].mkdir()
        self.files[host] = {}; self.native_names[host] = []
        directory = 'coordinator/run'; self.report_names[host] = directory + '/report.json'
        contract = dict(profile='active-hold', hero_class='Guardian', strategy='baseline_all_hand',
            strategy_seed=p['seed_start'], client_max_fps=None, client_runtime='editor',
            target_online=p.get('target_online',count), target_active=p.get('target_active', count), maximum_run_seconds=960,
            minimum_window=720, minimum_continuous=120, minimum_coverage=.95,
            maximum_gap=20.0, minimum_command_rate=1, **latency_policy(self.spec),
            minimum_generator_memory_bytes=p['memory_floor_bytes'],
            minimum_cloud_memory_bytes=500000000, minimum_cloud_disk_percent=5.0,
            cycle_limit_seconds=240, http_transport='reusable', resource_source='preregistered_prometheus')
        if self.spec.get('authority_transition_policy'):
            contract['authority_transition_policy']=self.spec['authority_transition_policy']
        identity_sources=dict(self.reference['controls']);identity_sources.update(self.reference['client'])
        identity = workload_profile_identity(contract, identity_sources)
        contract.update(workload_profile_id=identity['workload_profile_id'], workload_profile_qualified=True,
                        workload_profile_missing_reason=None)
        receipts, native_summaries, finals, inspections, frame_rows = [], [], [], [], []
        all_events, tail_events = [], []
        command = [p['engine_path'], '--headless', '--audio-driver', 'Dummy', '--path', p['project_path'],
                   'res://tests/gameplay_load_client.tscn']
        for index in range(count):
            cid = host + '-client-' + str(index); epoch = identifier(cid); pid = 1001 + index
            seed = p['seed_start'] + index; name = directory + '/' + cid + '.json'
            self.native_names[host].append(name)
            frame = dict(engine_max_fps=0, process_frames=100000, observed_ms=960000)
            frame_rows.append(dict(frame, client_id=cid, pid=pid))
            receipt = dict(client_id=cid, pid=pid, process_epoch=epoch, run_id=run,
                hero_class='Guardian', strategy='baseline_all_hand', strategy_seed=seed,
                started_at_ms=start * 1000 + index * 1000, started_at_monotonic_ms=mono + index * 1000,
                report_file=cid + '.json', command=command, client_max_fps=None,
                server_origin=p['server_origin'], client_runtime='editor')
            receipts.append(receipt)
            events = [dict(type='realtime', duration_ms=self.command_ms, result='success', at_unix_ms=(start + j * 10 - .5) * 1000)
                      for j in range(6, 97)]
            events.append(dict(type='http', duration_ms=self.http_ms, status=200, ok=True, result='success', phase='playing',
                               route='/api/v1/bootstrap', at_unix_ms=(start + 99.1) * 1000))
            events.sort(key=lambda x:x['at_unix_ms'])
            for seq, event in enumerate(events, 1):
                event.update(run_id=run, client_id=cid, process_epoch=epoch, event_seq=seq,
                             cycle_id=cid+':1', match_id=identifier('match-'+host), event_type=event['type'])
            audit = b''.join(json_bytes(e) for e in events)
            all_events.extend(events); tail_events.extend(e for e in events if e['at_unix_ms'] > (start + 950) * 1000)
            storage = dict(version=1, max_segments=8, record_limit_bytes=65536, segment_limit_bytes=16777216,
                segment_count=1, segment_bytes=[len(audit)], events_written=len(events), bytes_written=len(audit),
                buffer_count=0, buffer_serialized_bytes=0, last_error='')
            self.write(host, name + '.telemetry.jsonl', audit)
            user = identifier('user-' + cid); self.users.append(user)
            native = dict(pid=pid, client_id=cid, process_epoch=epoch, run_id=run, user_id=user,
                hero_class='Guardian', strategy='baseline_all_hand', strategy_seed=seed,
                load_profile='active-hold', cycle_limit_seconds=240, outcome='cancelled', ok=False,
                errors=[], audit_lost_count=0, event_seq_max=len(events), cycles_completed=0,
                cleanup=dict(state='Passed'), audit_storage=storage, generator_frame_clock=frame,
                checks=[dict(name=n, passed=True) for n in ['realtime_connected', 'login_and_bootstrap', 'hero_class_confirmed', 'room_started']])
            raw = json_bytes(native); self.write(host, name, raw)
            native_summaries.append(dict(client_id=cid, _primary_report_sha256=hashlib.sha256(raw).hexdigest(), _primary_report_bytes=len(raw)))
            finals.append(copy.deepcopy(native))
            finals[-1].pop('user_id',None)  # Real heartbeats intentionally omit login identity.
            env = dict(FANTASYCARD_LOAD_CLIENT_ID=cid, FANTASYCARD_LOAD_RUN_ID=run,
                FANTASYCARD_LOAD_PROCESS_EPOCH=epoch, FANTASYCARD_LOAD_PROFILE='active-hold',
                FANTASYCARD_LOAD_MAX_CYCLES='0', FANTASYCARD_LOAD_SEED=str(seed),
                FANTASYCARD_LOAD_HERO_CLASS='Guardian', FANTASYCARD_LOAD_STRATEGY='baseline_all_hand',
                FANTASYCARD_LOAD_HOLD_SECONDS='720', FANTASYCARD_LOAD_RUN_SECONDS='960',
                FANTASYCARD_LOAD_CYCLE_LIMIT_SECONDS='240', FANTASYCARD_LOAD_HTTP_TRANSPORT='reusable',
                FANTASYCARD_SERVER_URL='http://127.0.0.1:' + str(p['server_origin']['port']))
            inspections.append(dict(pid=pid, exe=p['engine_path'], command=command, load_environment=env,
                                    priority_class=0x4000, cpu_affinity=[12,13,14,15]))
        samples = []
        for second in range(0, 960, 10):
            selected = [e for e in all_events if (start + second - 10) * 1000 < e['at_unix_ms'] <= (start + second) * 1000]
            window = aggregate_window([dict(operations=[e for e in selected if e['type']=='http'],
                                           telemetry=[e for e in selected if e['type']=='realtime'])], observed_seconds=10)
            window.update(lost_event_count=0, audit_lost_count=0, command_error_rate=0)
            active_count = count if self.spec.get('workload_profile') in ('full-native60-global50-win35-cloud25',GLOBAL50_AGGREGATE_PROFILE) else p.get('target_active', count)
            active = active_count if second >= 60 else 0; alive = min(count, second)
            samples.append(dict(at=start+second, sample_monotonic_ms=mono+second*1000,
                run_id=run, online=alive, active_in_room=active, alive_processes=alive, fresh_status_clients=alive,
                server_confirmed_in_room=self.spec['target_clients'] if active else 0,
                command_rate=None if second==0 else window['realtime']['count']/10,
                workload_failure=False, reasons=[], failed_processes=[], stale_clients=[], stalled_clients=[],
                missing_clients=[], invalid_clients=[], window=window,
                generator=dict(available=True, host_memory_available_bytes=14000000000,
                               native_frame_observations=frame_rows if active else []),
                resources=dict(cpu=20, actor_wait=1, disk_available=20, memory_available_bytes=2000000000),
                health=dict(ok=True, duration_ms=10)))
        tail = aggregate_window([dict(operations=[e for e in tail_events if e['type']=='http'],
                                      telemetry=[e for e in tail_events if e['type']=='realtime'])])
        report = dict(clients=count, group_size=count, groups=1, stop_reason='duration_limit',
            outcome=dict(passed=True, exit_code=0), started=start, stop_issued_ms=(start+960)*1000,
            cutoff_clock_quality=dict(qualified=True,evidence_errors=[],cutoffs_unix_ms=dict(
                start=start*1000,stop=(start+960)*1000,final=(start+970)*1000)),started_monotonic_ms=mono,
            stop_issued_monotonic_ns=(mono+960000)*1000000,
            final_cutoff_monotonic_ns=(mono+970000)*1000000,
            result_dimensions=dict(applicable=['execution','evidence','load','performance','cleanup'],
                dimensions={k:'Passed' for k in ['execution','evidence','load','performance','cleanup']}),
            load_window_verified=True, process_cleanup_complete=True, business_cleanup_verified=True,
            audit_read_errors=[], final_status_read_errors=[], native_final_report_errors=[], forced_termination_pids=[],
            final_audit_lost_count=0, final_read_errors=0, tail_lost_event_count=0,
            post_stop_failure=False, final_audit_count_invalid=False,
            source=dict(git_commit=self.reference['head'], sha256=self.reference['controls'],
                        active_client_project=dict(path=p['project_path'], input_hashes=self.reference['client'])),
            load_contract=contract, samples=samples, tail_window=tail, launch_receipts=receipts,
            native_final_reports=native_summaries, final_clients=finals,
            process_exits=[dict(client_id=r['client_id'], before_stop=None, after_stop=0) for r in receipts])
        if self.spec.get('authority_transition_policy'):
            primary=[self.get(host,name) for name in self.native_names[host]]
            report['authority_transition_review']=review_authority_refusals(all_events,primary,
                policy=self.spec['authority_transition_policy'],cutoff_clock_qualified=True)
        self.put_report(host, report)
        self.put(host, 'engine.json', dict(before_sha256=OFFICIAL_ENGINE[platform], after_sha256=OFFICIAL_ENGINE[platform],
            version=ENGINE_VERSION, requested_path=p['engine_path'], real_path=p['engine_path'],
            source_controls_after=self.reference['controls'], client_inputs_after=self.reference['client'],
            after_hash_scope='same_engine_file_after_run' if platform=='windows' else 'same_readonly_image_after_run',
            readonly_image_root=platform=='linux'))
        self.put(host, 'processes.json', dict(processes=inspections, observed_unix_ms=(start+80)*1000,
                                             observed_monotonic_ms=mono+80000))
        self.put(host, 'clocks.json', [probe(host, -10, 'before', skew=skew, mono_origin=mono),
                                      probe(host, 980, 'after', skew=skew, mono_origin=mono)])
        self.put(host, 'supervisor.json', dict(terminal=dict(ok=True, guard_stop=None), resources=[
            dict(monotonic_ms=mono+t*1000, memory_available_bytes=(20000000000 if platform=='windows' else 3000000000) if self.spec.get('workload_profile') in (GLOBAL50_AGGREGATE_PROFILE,THREE_HOST100_PROFILE) else 14000000000, root_disk_free_bytes=5000000000, root_disk_available_percent=20)
            for t in range(0, 975, 5)]))
        self.put(host, 'host-capture.original.json', dict(host_id=host,
            spec_sha256=hashlib.sha256(canonical(self.spec)).hexdigest(), report_file=self.report_names[host],
            engine_file='engine.json', process_file='processes.json', clock_file='clocks.json', supervisor_file='supervisor.json',
            **({'machine_name':p['machine_name'],'controller_sha256':self.reference['controllers']['tools/pr13_three_host_windows.py']}
               if self.spec.get('workload_profile')==THREE_HOST100_PROFILE and platform=='windows' else {})))

    def assess(self):
        captures = {h:Capture(self.roots[h], list(self.files[h].values())) for h in self.roots}
        return assess_captures(self.spec, captures, self.reference, self.before, self.after)


class CapacityEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.parent = Path(tempfile.gettempdir()).resolve()
        self.temp = tempfile.TemporaryDirectory(prefix='pr13-distributed-evidence-')
        self.root = Path(self.temp.name).resolve()
        self.assertTrue(self.root.is_relative_to(self.parent))
        self.study = SyntheticStudy(self.root)

    def tearDown(self):
        self.assertTrue(self.root.is_relative_to(self.parent) and self.root.name.startswith('pr13-distributed-evidence-'))
        self.temp.cleanup()

    def reject(self):
        result = self.study.assess()
        self.assertFalse(result['capacity_accepted'], result)
        return result

    def test_synthetic_complete_evidence_passes_only_capacity_not_project(self):
        result = self.study.assess()
        self.assertTrue(result['capacity_accepted'], result)
        self.assertFalse(result['whole_project_accepted'])
        self.assertEqual(50, result['participants'])

    def test_changed_native_bytes_not_repaired_by_good_summary(self):
        p = self.study.roots['cloud'] / self.study.native_names['cloud'][0]
        p.write_bytes(p.read_bytes()+b' ')
        self.reject()

    def test_lite_or_unknown_executable_digest_rejected(self):
        e = self.study.get('cloud','engine.json'); e['before_sha256']='f'*64
        self.study.put('cloud','engine.json',e); self.reject()

    def test_binary_changed_during_run_rejected(self):
        e = self.study.get('cloud','engine.json'); e['after_sha256']='f'*64
        self.study.put('cloud','engine.json',e); self.reject()

    def test_source_changed_after_start_rejected(self):
        e=self.study.get('cloud','engine.json');e['source_controls_after'][SOURCE_FILES[0]]='f'*64
        self.study.put('cloud','engine.json',e);self.reject()

    def test_after_image_hash_requires_readonly_runtime_root(self):
        e=self.study.get('cloud','engine.json');e['readonly_image_root']=False
        self.study.put('cloud','engine.json',e);self.reject()

    def test_source_byte_override_rejected(self):
        r=self.study.report('cloud'); r['source']['sha256']=dict(r['source']['sha256']);r['source']['sha256'][SOURCE_FILES[0]]='f'*64
        self.study.put_report('cloud',r);self.reject()

    def test_missing_frozen_client_resource_rejected(self):
        r=self.study.report('cloud');r['source']['active_client_project']['input_hashes'].pop('client/project.godot')
        self.study.put_report('cloud',r);self.reject()

    def test_added_executable_client_code_rejected(self):
        r=self.study.report('cloud');r['source']['active_client_project']['input_hashes']['client/lite.gd']='f'*64
        self.study.put_report('cloud',r);self.reject()

    def test_observed_FPS_cap_rejected(self):
        r=self.study.report('cloud');r['samples'][30]['generator']['native_frame_observations'][0]['engine_max_fps']=30
        self.study.put_report('cloud',r);self.reject()

    def test_OS_process_owner_environment_rejected(self):
        x=self.study.get('cloud','processes.json');x['processes'][0]['load_environment']['FANTASYCARD_LOAD_PROCESS_EPOCH']='foreign'
        self.study.put('cloud','processes.json',x);self.reject()

    def test_missing_OS_native_inspection_rejected(self):
        x=self.study.get('cloud','processes.json');x['processes'].pop()
        self.study.put('cloud','processes.json',x);self.reject()

    def test_native_window_argument_override_rejected(self):
        r=self.study.report('windows');r['launch_receipts'][0]['command']=r['launch_receipts'][0]['command']+['--max-fps','1']
        self.study.put_report('windows',r);self.reject()

    def test_omitted_audit_segment_does_not_become_valid_report(self):
        name=self.study.native_names['cloud'][0]+'.telemetry.jsonl'
        (self.study.roots['cloud']/name).unlink();self.study.files['cloud'].pop(name)
        self.reject()

    def test_duplicate_foreign_user_with_resealed_primary_rejected(self):
        user=self.study.get('windows',self.study.native_names['windows'][0])['user_id']
        self.study.change_native('cloud',0,lambda n:n.update(user_id=user));self.reject()

    def test_failure_on_either_original_cohort_preserved(self):
        r=self.study.report('cloud');r['outcome']['passed']=False
        self.study.put_report('cloud',r);self.reject()

    def test_unknown_cleanup_not_promoted(self):
        r=self.study.report('cloud');r['business_cleanup_verified']=False
        self.study.put_report('cloud',r);self.reject()

    def test_forced_termination_not_hidden(self):
        r=self.study.report('windows');r['forced_termination_pids']=[1001]
        self.study.put_report('windows',r);self.reject()

    def test_reduced_local_memory_reserve_rejected(self):
        self.study.spec['partitions'][0]['memory_floor_bytes']=1000000000
        self.study.bind_spec();self.reject()

    def test_private_backend_changed_rejected(self):
        self.study.after['app_id']='c'*64;self.reject()

    def test_unexpected_server_participant_rejected(self):
        self.study.after['settled_user_ids'].append(identifier('foreign'));self.reject()

    def test_pending_asset_holds_rejected(self):
        self.study.after['pending_holds']=1;self.reject()

    def test_world_count_cannot_exceed_user_budget(self):
        self.study.after['matches']=301;self.reject()

    def test_boolean_cleanup_count_not_treated_as_zero(self):
        self.study.after['pending_holds']=False;self.reject()

    def test_duplicate_exit_row_cannot_hide_previous_failure(self):
        r=self.study.report('cloud');r['process_exits'].insert(0,dict(r['process_exits'][0],after_stop=1))
        self.study.put_report('cloud',r);self.reject()

    def test_sustained_CPU_redline_is_replayed_despite_passed_summary(self):
        r=self.study.report('cloud')
        for row in r['samples'][30:33]:row['resources']['cpu']=90
        self.study.put_report('cloud',r);self.reject()

    def test_resource_watch_gap_cannot_be_repaired_by_final_memory(self):
        s=self.study.get('windows','supervisor.json');s['resources']=s['resources'][:30]+s['resources'][34:]
        self.study.put('windows','supervisor.json',s);self.reject()

    def test_actual_nested_cutoff_schema_and_contradictory_secondary_rejected(self):
        r=self.study.report('cloud')
        self.assertNotIn('final_cutoff_ms',r)
        r['cycle_cutoffs']=dict(stop_ms=r['stop_issued_ms'],final_ms=r['stop_issued_ms']+999999)
        self.study.put_report('cloud',r);self.reject()

    def test_process_inspection_after_window_rejected(self):
        s=self.study.get('cloud','processes.json');s['observed_unix_ms']=(BASE+400)*1000
        self.study.put('cloud','processes.json',s);self.reject()

    def test_unsealed_spec_change_rejected(self):
        self.study.spec['seed_start']+=1;self.reject()

    def test_two_valid_partitions_cannot_repeat_same25_strategy_seeds(self):
        root=self.root/'seed-overlap';root.mkdir()
        s=SyntheticStudy(root,cloud_seed_start=20260930)
        result=s.assess()
        self.assertFalse(result['capacity_accepted'])
        self.assertIn('not_original_full50_seed_distribution',result['evidence_errors'])

    def test_registered_after_cohort_start_rejected(self):
        self.study.spec['registered_at_reference_ms']=(BASE+30)*1000
        self.study.bind_spec();self.reject()

    def test_manifest_path_traversal_rejected(self):
        with self.assertRaises(ValueError):
            Capture(self.root,[dict(path='../foreign.json',bytes=1,sha256='f'*64)])

    def test_strict_JSON_rejects_duplicate_keys_and_nonfinite_values(self):
        for raw in [b'{"x":1,"x":2}',b'{"x":NaN}']:
            with self.subTest(raw=raw),self.assertRaises(ValueError):strict_json(raw)

    def test_frozen_reference_hashes_real_Git_blobs_and_ignores_worktree_edits(self):
        repo=self.root/'reference';repo.mkdir()
        def git(*args):
            r=subprocess.run(['git','-c','user.name=UnitTest','-c','user.email=unit@example.invalid',
                              '-c','core.autocrlf=false','-c','core.eol=lf',*args],cwd=repo,capture_output=True)
            self.assertEqual(0,r.returncode,r.stderr.decode(errors='replace'));return r.stdout
        git('init','-q')
        files=set(SOURCE_FILES)|{'client/project.godot','client/full-resource.bin'}
        for name in files:
            p=repo/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(('original:'+name).encode())
        git('add','.');git('commit','-qm','Synthetic frozen reference')
        head=git('rev-parse','HEAD').decode().strip()
        (repo/'client/full-resource.bin').write_bytes(b'changed after commit')
        ref=load_git_reference(repo,head)
        self.assertEqual(hashlib.sha256(b'original:client/full-resource.bin').hexdigest(),ref['client']['client/full-resource.bin'])
        self.assertEqual(set(SOURCE_FILES),set(ref['controls']))


class LatencyProfileTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='pr13-latency-profile-')
        self.addCleanup(self.temp.cleanup)

    def study(self, **kwargs):
        return SyntheticStudy(self.temp.name, **kwargs)

    def test_omitted_profile_keeps_default_limits_and_explicit_default_verdict(self):
        s = self.study()
        result = s.assess()
        self.assertTrue(result['capacity_accepted'], result)
        self.assertTrue(result['default_latency_capacity_accepted'])
        self.assertEqual('default', result['latency_profile'])
        self.assertEqual(1500, result['latency_limits']['http_p95_limit_ms'])
        self.assertEqual(3, result['latency_limits']['monitor_timeout_seconds'])

    def test_documented_WAN_boundary_pass_is_only_the_explicit_scoped_verdict(self):
        s = self.study(latency_profile=NORTH_AMERICA_LATENCY_PROFILE, http_ms=5000, command_ms=8000)
        for host in s.roots:
            r = s.report(host)
            for sample in r['samples']:
                sample['health']['duration_ms'] = 10000
            s.put_report(host, r)
        result = s.assess()
        self.assertTrue(result['capacity_accepted'], result)
        self.assertFalse(result['default_latency_capacity_accepted'])
        self.assertFalse(result['whole_project_accepted'])
        self.assertEqual(NORTH_AMERICA_LATENCY_PROFILE, result['latency_profile'])
        self.assertEqual(5000, result['pooled_running_latency']['http']['p95_ms'])
        self.assertEqual(8000, result['pooled_running_latency']['realtime']['p95_ms'])

    def test_default_does_not_accept_WAN_contract_without_spec_opt_in(self):
        s = self.study(latency_profile=NORTH_AMERICA_LATENCY_PROFILE)
        s.spec.pop('latency_profile'); s.bind_spec()
        result = s.assess()
        self.assertFalse(result['capacity_accepted'])
        self.assertIn('changed_native_workload_contract', result['evidence_errors'])

    def test_spec_opt_in_cannot_relax_a_cohort_run_under_default_contract(self):
        s = self.study()
        s.spec['latency_profile'] = NORTH_AMERICA_LATENCY_PROFILE; s.bind_spec()
        self.assertIn('changed_native_workload_contract', s.assess()['evidence_errors'])

    def test_unknown_or_structured_policy_cannot_supply_arbitrary_limits(self):
        s = self.study()
        for value in ['anything', None, True, {'http_p95_limit_ms': 60000}]:
            with self.subTest(profile=value):
                s.spec['latency_profile'] = value; s.bind_spec()
                self.assertIn('unknown_latency_profile', s.assess()['evidence_errors'])

    def test_WAN_monitor_budget_is_bound_to_actual_cohort_contract(self):
        s = self.study(latency_profile=NORTH_AMERICA_LATENCY_PROFILE)
        r = s.report('windows'); r['load_contract']['monitor_timeout_seconds'] = 60
        s.put_report('windows', r)
        self.assertIn('changed_native_workload_contract', s.assess()['evidence_errors'])

    def test_WAN_HTTP_one_ms_over_boundary_still_fails_raw_pooled_gate(self):
        s = self.study(latency_profile=NORTH_AMERICA_LATENCY_PROFILE, http_ms=5001)
        result = s.assess()
        self.assertFalse(result['capacity_accepted'])
        self.assertIn('pooled_raw_latency_redline', result['evidence_errors'])

    def test_WAN_command_one_ms_over_boundary_still_fails_window_replay(self):
        s = self.study(latency_profile=NORTH_AMERICA_LATENCY_PROFILE, command_ms=8001)
        self.assertIn('original_sustained_redline_replay_failed', s.assess()['evidence_errors'])

    def test_WAN_health_one_ms_over_boundary_still_fails(self):
        s = self.study(latency_profile=NORTH_AMERICA_LATENCY_PROFILE)
        r = s.report('cloud')
        for sample in r['samples'][30:33]:
            sample['health']['duration_ms'] = 10001
        s.put_report('cloud', r)
        self.assertIn('original_sustained_redline_replay_failed', s.assess()['evidence_errors'])

    def test_WAN_profile_does_not_waive_memory_or_failed_execution(self):
        s = self.study(latency_profile=NORTH_AMERICA_LATENCY_PROFILE)
        r = s.report('cloud'); r['outcome']['passed'] = False
        s.put_report('cloud', r)
        self.assertIn('original_cohort_did_not_pass', s.assess()['evidence_errors'])
        r['outcome']['passed'] = True; s.put_report('cloud', r)
        supervisor = s.get('cloud', 'supervisor.json')
        supervisor['resources'][50]['memory_available_bytes'] = 499999999
        s.put('cloud', 'supervisor.json', supervisor)
        self.assertIn('host_memory_reserve_breached', s.assess()['evidence_errors'])

    def test_WAN_profile_does_not_accept_49_active_players(self):
        s = self.study(latency_profile=NORTH_AMERICA_LATENCY_PROFILE)
        for host in s.roots:
            r = s.report(host)
            for sample in r['samples']:
                sample['server_confirmed_in_room'] = 49
            s.put_report(host, r)
        self.assertFalse(s.assess()['capacity_accepted'])


class HundredPlayerEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='pr13-full100-evidence-')
        self.addCleanup(self.temp.cleanup)

    def study(self, **kwargs):
        return SyntheticStudy(self.temp.name, target_clients=100, **kwargs)

    def test_full100_synthetic_evidence_can_only_award_registered_capacity(self):
        s = self.study()
        result = s.assess()
        self.assertTrue(result['capacity_accepted'], result)
        self.assertEqual(100, result['participants'])
        self.assertEqual(100, result['target_active'])
        self.assertTrue(result['default_latency_capacity_accepted'])
        self.assertFalse(result['whole_project_accepted'])

    def test_100_WAN_profile_still_is_not_default_latency_acceptance(self):
        s = self.study(latency_profile=NORTH_AMERICA_LATENCY_PROFILE, http_ms=5000, command_ms=8000)
        result = s.assess()
        self.assertTrue(result['capacity_accepted'], result)
        self.assertEqual(100, result['participants'])
        self.assertFalse(result['default_latency_capacity_accepted'])
        self.assertFalse(result['whole_project_accepted'])

    def test_50_participant_evidence_cannot_be_relabelled100(self):
        s = SyntheticStudy(self.temp.name)
        s.spec['target_clients'] = 100; s.bind_spec()
        self.assertIn('wrong_full100_partitions', s.assess()['evidence_errors'])

    def test_stronger60_for50_evidence_cannot_be_relabelled100(self):
        s = SyntheticStudy(self.temp.name, stronger_population=True)
        s.spec['target_clients'] = 100; s.bind_spec()
        self.assertIn('unregistered_online_population', s.assess()['evidence_errors'])

    def test_arbitrary_joint_target_is_not_enabled_by100_support(self):
        s = self.study()
        for target in [True, 99, 200]:
            with self.subTest(target=target):
                s.spec['target_clients'] = target; s.bind_spec()
                self.assertIn('wrong_registered_study', s.assess()['evidence_errors'])

    def test_99_actual_launches_fail_despite_good_summary(self):
        s = self.study()
        r = s.report('cloud'); r['clients'] = 49; s.put_report('cloud', r)
        self.assertIn('cohort_count_mismatch', s.assess()['evidence_errors'])

    def test_global_server_gauge99_cannot_prove100(self):
        s = self.study()
        for host in s.roots:
            r = s.report(host)
            for sample in r['samples']:
                sample['server_confirmed_in_room'] = 99
            s.put_report(host, r)
        self.assertIn('shared_full100_window_not_verified', s.assess()['evidence_errors'])

    def test_one_partition49_active_is_not100_active(self):
        s = self.study()
        r = s.report('cloud')
        for sample in r['samples']:
            sample['active_in_room'] = min(sample['active_in_room'], 49)
        s.put_report('cloud', r)
        self.assertIn('original_load_coverage_replay_failed', s.assess()['evidence_errors'])

    def test_100_strategy_seeds_must_still_be_disjoint_full_population(self):
        s = self.study(cloud_seed_start=20260955)
        self.assertIn('not_original_full100_seed_distribution', s.assess()['evidence_errors'])

    def test_100_still_refuses_resource_below_current_cloud_floor(self):
        s = self.study(latency_profile=NORTH_AMERICA_LATENCY_PROFILE)
        supervisor = s.get('cloud', 'supervisor.json')
        supervisor['resources'][50]['memory_available_bytes'] = 499999999
        s.put('cloud', 'supervisor.json', supervisor)
        self.assertIn('host_memory_reserve_breached', s.assess()['evidence_errors'])

    def test_100_actual_users_cannot_reuse_an_authenticated_identity(self):
        s = self.study()
        user = s.get('cloud', s.native_names['cloud'][0])['user_id']
        s.change_native('cloud', 1, lambda n: n.update(user_id=user))
        self.assertIn('duplicate_or_empty_server_user', s.assess()['evidence_errors'])


class StrongerPopulationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='pr13-stronger-population-')
        self.addCleanup(self.temp.cleanup)
        self.study = SyntheticStudy(self.temp.name, stronger_population=True)

    def test_all60_authenticated_natives_with50_active_can_pass_only_scoped_capacity(self):
        result = self.study.assess()
        self.assertTrue(result['capacity_accepted'], result)
        self.assertEqual(60, result['participants'])
        self.assertEqual(50, result['target_active'])
        self.assertFalse(result['whole_project_accepted'])

    def test_60online_but49globally_active_fails(self):
        for host in self.study.roots:
            report = self.study.report(host)
            for row in report['samples']:
                row['server_confirmed_in_room'] = 49
            self.study.put_report(host, report)
        self.assertFalse(self.study.assess()['capacity_accepted'])

    def test_60online_but_one_partition_below_active_requirement_fails(self):
        report = self.study.report('cloud')
        for row in report['samples']:
            row['active_in_room'] = min(row['active_in_room'], 22)
        self.study.put_report('cloud', report)
        self.assertFalse(self.study.assess()['capacity_accepted'])

    def test_extra_producers_require_explicit_profile_and_do_not_relax_targets(self):
        self.study.spec.pop('workload_profile')
        self.study.bind_spec()
        self.assertIn('stronger_population_profile_not_declared', self.study.assess()['evidence_errors'])
        self.study.spec['workload_profile'] = 'full-native60-for50active'
        self.study.spec['partitions'][1]['target_active'] = 22
        self.study.bind_spec()
        self.assertIn('wrong_full50_partitions', self.study.assess()['evidence_errors'])

    def test_duplicate_strategy_seeds_on_stronger_population_still_fail(self):
        self.study.spec['partitions'][1]['seed_start'] = self.study.spec['partitions'][0]['seed_start']
        self.study.bind_spec()
        self.assertFalse(self.study.assess()['capacity_accepted'])

    def test_stronger_population_does_not_waive_resource_floor(self):
        supervisor = self.study.get('cloud', 'supervisor.json')
        supervisor['resources'][50]['memory_available_bytes'] = 499999999
        self.study.put('cloud', 'supervisor.json', supervisor)
        self.assertIn('host_memory_reserve_breached', self.study.assess()['evidence_errors'])

    def test_stronger_population_does_not_allow_reused_authenticated_identity(self):
        user = self.study.get('cloud', self.study.native_names['cloud'][0])['user_id']
        self.study.change_native('cloud', 1, lambda n:n.update(user_id=user))
        self.assertIn('duplicate_or_empty_server_user', self.study.assess()['evidence_errors'])

    def test_impossible_global_gauge_above_all60_producers_fails(self):
        for host in self.study.roots:
            report = self.study.report(host)
            for row in report['samples']:
                row['server_confirmed_in_room'] = 61
            self.study.put_report(host, report)
        self.assertFalse(self.study.assess()['capacity_accepted'])


if __name__=='__main__':unittest.main()
