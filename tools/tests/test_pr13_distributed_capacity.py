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
    SERVER_IMAGE, SOURCE_FILES, assess_captures, canonical, load_git_reference, strict_json)
from tools.gameplay_load_validation import aggregate_window, workload_profile_identity
from tools.tests.test_pr13_distributed_load import BASE, probe


def identifier(text):
    return uuid.uuid5(uuid.NAMESPACE_URL, text).hex


def json_bytes(value):
    return (json.dumps(value, allow_nan=False, sort_keys=True) + '\n').encode()


class SyntheticStudy:
    def __init__(self, root, *, cloud_seed_start=None, stronger_population=False):
        self.root = Path(root)
        self.reference = dict(head='1' * 40,
            controls={p:hashlib.sha256(p.encode()).hexdigest() for p in SOURCE_FILES},
            client={'client/project.godot':'2' * 64, 'client/tests/gameplay_load_client.gd':'3' * 64})
        partitions = []
        for host, platform, offset in [('windows', 'windows', 0), ('cloud', 'linux', 32 if stronger_population else 25)]:
            count = (32 if host == 'windows' else 28) if stronger_population else 25
            partitions.append(dict(host_id=host, platform=platform, clients=count,
                seed_start=20260930 + offset, memory_floor_bytes=6442450944 if offset == 0 else 500000000,
                engine_path='G:\\engine\\godot.exe' if offset == 0 else '/usr/local/bin/godot',
                project_path='G:\\fixture\\client' if offset == 0 else '/fixture/client',
                server_origin=dict(scheme='http', host='127.0.0.1', port=18641 if offset == 0 else 18541),
                cpu_affinity=[12, 13, 14, 15]))
            if stronger_population:
                partitions[-1]['target_active'] = 27 if host == 'windows' else 23
        if cloud_seed_start is not None:
            partitions[1]['seed_start'] = cloud_seed_start
        self.spec = dict(study_id=identifier('study'), owner=identifier('owner'), source_head=self.reference['head'], world_budget=300,
            target_clients=50, reference_host_id='windows', seed_start=20260930, partitions=partitions,
            registered_at_reference_ms=(BASE - 30) * 1000,
            window_start_ms=(BASE + 300) * 1000, window_end_ms=(BASE + 900) * 1000)
        if stronger_population:
            self.spec.update(target_online_clients=60, workload_profile='full-native60-for50active')
        self.report_names, self.files, self.roots, self.native_names, self.users = {}, {}, {}, {}, []
        for p in partitions:
            self.build_host(p)
        self.before = dict(app_id='a' * 64, app_image=SERVER_IMAGE, app_started_at='fixture-start',
            environment_sha256='4' * 64, pg_id='b' * 64, database='ready_stop_unit',
            study_id=self.spec['study_id'], owner=self.spec['owner'], read_only_app=True,
            initial_humans=0, initial_matches=0, settled_user_ids=[])
        self.after = dict(self.before, final_humans=0, pending_holds=0, matches=13, settled_user_ids=list(self.users))

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
            target_online=count, target_active=p.get('target_active', count), maximum_run_seconds=960,
            minimum_window=720, minimum_continuous=120, minimum_coverage=.95,
            maximum_gap=20.0, minimum_command_rate=1, http_p95_limit_ms=1500,
            command_p95_limit_ms=2000, health_limit_ms=5000,
            minimum_generator_memory_bytes=p['memory_floor_bytes'],
            minimum_cloud_memory_bytes=500000000, minimum_cloud_disk_percent=5.0,
            cycle_limit_seconds=240, http_transport='reusable', resource_source='preregistered_prometheus')
        identity = workload_profile_identity(contract, self.reference['controls'])
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
            events = [dict(type='realtime', duration_ms=10, result='success', at_unix_ms=(start + j * 10 - .5) * 1000)
                      for j in range(6, 97)]
            events.append(dict(type='http', duration_ms=10, status=200, ok=True, result='success', phase='playing',
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
            active = p.get('target_active', count) if second >= 60 else 0; alive = min(count, second)
            samples.append(dict(at=start+second, sample_monotonic_ms=mono+second*1000,
                run_id=run, online=alive, active_in_room=active, alive_processes=alive, fresh_status_clients=alive,
                server_confirmed_in_room=50 if active else 0,
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
            dict(monotonic_ms=mono+t*1000, memory_available_bytes=14000000000, root_disk_free_bytes=5000000000)
            for t in range(0, 975, 5)]))
        self.put(host, 'host-capture.original.json', dict(host_id=host,
            spec_sha256=hashlib.sha256(canonical(self.spec)).hexdigest(), report_file=self.report_names[host],
            engine_file='engine.json', process_file='processes.json', clock_file='clocks.json', supervisor_file='supervisor.json'))

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
