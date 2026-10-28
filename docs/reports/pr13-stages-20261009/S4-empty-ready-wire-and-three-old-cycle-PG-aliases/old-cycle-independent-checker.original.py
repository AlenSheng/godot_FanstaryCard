"""Independent custody and actual-source/READY/SQL predicates; no experiments locally."""
import gzip,hashlib,json,subprocess
from pathlib import Path
B=Path(__file__).parent;R=B.parents[1];OUT=B/'three-old-cycle-existing-native-PG-alias-independent-G-check-r1'
assert not OUT.exists()
def read(p):return json.loads(p.read_bytes())
def sha(p):
    h=hashlib.sha256()
    with p.open('rb') as f:
        for block in iter(lambda:f.read(1024**2),b''):h.update(block)
    return h.hexdigest()
receipt=read(B/'A042-old-started-PG-r2-complete-original-G-backup/complete-original-G-receipt.original.json')
assert receipt['ok'] and receipt['all_original_members_SHA_verified'] and receipt['archive_gzip_CRC_verified']
G=Path(receipt['local_directory']);archive=Path(receipt['local_archive'])
assert archive.stat().st_size==receipt['archive_bytes'] and sha(archive)==receipt['archive_sha256']
with gzip.open(archive,'rb') as stream:
    while stream.read(1024**2):pass
assert sha(G/'complete-original-manifest.json')==receipt['manifest_sha256']
manifest=read(G/'complete-original-manifest.json')
for row in manifest['files']:
    p=G/row['path'];assert p.stat().st_size==row['bytes'] and sha(p)==row['sha256']
plan=read(G/'work/plan.original.json')
head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=R,text=True).strip()
assert len(plan['source_files'])==328 and len(plan['runtime_files'])==146 and len(plan['client_files'])==66
overrides={'client/tests/run_ready_stop_faults.py':plan['override_runner_sha256'], 'client/tests/run_ready_stop_faults.gd':plan['override_gd_sha256']}
for row in plan['source_files']+plan['client_files']:
    raw=subprocess.check_output(['git','show',head+':'+row['path']],cwd=R)
    assert len(raw)==row['bytes'] and hashlib.sha256(raw).hexdigest()==row['sha256']
    if row in plan['source_files']:assert sha(G/'input-source'/row['path'])==row['sha256']
    else:assert sha(G/'evidence/parent-client-originals'/row['path'])==row['sha256']
    p=G/'work/source'/row['path'];assert sha(p)==overrides.get(row['path'],row['sha256'])
for row in plan['runtime_files']:assert sha(G/'input-runtime'/row['path'])==row['sha256']
assert sha(G/'input-runtime/FantasyCard.Domain.dll')=='844065af3158b40787699752915ed95befbd3c660c2b10dce501f9f4fc29e352'
terminal=read(G/'evidence/terminal-state.original.json');assert terminal['MainPID']=='0' and terminal['ActiveState']=='inactive' and terminal['ExecMainStatus']=='0'
result=read(G/'evidence/result.original.json');assert result['ok'] and result['exit_code']==0 and not result['oom_killed']
assert result['actual_native_job_exit_code']==0 and result['actual_native_PG_rows']==2
assert result['owned_containers_removed'] and result['private_environment_removed_after_owned_containers_ended']
assert result['isolated_PG_schemas_before']==result['isolated_PG_schemas_after']==0
native=G/'evidence/persistent-output/native';report=read(native/'report.json')
assert report['ok'] and report['case_count']==report['passed_case_count']==report['planned_case_count']==2
assert not report['source_dirty'] and report['owned_fixture_databases_removed'] and report['owned_server_stopped']
assert report['source_sha']==read(G/'evidence/prepared.original.json')['owned_projection_commit']
prebuilt=read(native/'actual-prebuilt-server.json');assert prebuilt['source_rebuilt'] is False and prebuilt['server_assembly_sha256']==plan['actual_server_assembly_sha256']
assert sha(native/'server-frozen/FantasyCard.Server.dll')==plan['actual_server_assembly_sha256']
for command in read(native/'commands.json'):
    assert command['exit_code']==0
    if command['label'].endswith('-godot'):assert command['deadline_seconds']==95
cases={row['case']:row for row in report['cases']}
assert set(cases)=={'normal_ready','second_cycle_old_original_started'}
for case in cases.values():
    c=case['actual'];pg=case['postgres']
    assert case['passed'] and case['postgres_passed'] and case['transport_passed'] and case['exit_code']==0
    assert c['passed'] and c['local_terminal'] and c['route_probe_clear'] and c['cleanup']['state']=='Passed' and c['ready_send_after_stop']==0
    expected=2 if case['case']=='second_cycle_old_original_started' else 1
    assert pg['matches']==pg['rooms']==expected and pg['ready_deadline_seconds']==[15]*expected
    assert pg['locked_equipment']==pg['pending_settlement_holds']==0 and pg['equipment_locks']==1
    assert len(pg['match_rows'])==expected and c['observed_match_id']==c['active_match_id']
    assert any(r['match_id']==c['observed_match_id'] and r['room_id']==c['observed_room_id'] for r in pg['match_rows'])
target=cases['second_cycle_old_original_started'];c=target['actual'];trace=c['trace']
def events(name):return [e for e in trace if e['event']==name]
first=events('first_original_started_captured');second=events('real_second_started_seen');exit_events=events('first_cycle_legal_exit_sent')
assert len(first)==len(second)==len(exit_events)==1
assert first[0]['match_id']!=second[0]['match_id']==c['observed_match_id']
assert exit_events[0]['match_id']==first[0]['match_id'] and exit_events[0]['action']=='battle.abandon'
assert c['actual_completed_cycles']==1 and c['first_legal_exit_sent'] is True
assert sum(x['name']=='settlement_acknowledged' and x['passed'] for x in c['checks'])==1
observations=[events(n) for n in ['old_started_before','old_started_immediate_after','old_started_stable_after']]
assert all(len(e)==1 for e in observations)
before,immediate,after=[e[0] for e in observations]
assert first[0]['sequence']<before['gateway_last_sequence']
assert first[0]['at_ms']<=exit_events[0]['at_ms']<second[0]['at_ms']<before['at_ms']<=immediate['at_ms']<after['at_ms']
assert after['at_ms']-immediate['at_ms']>=1000
for e in [before,immediate,after]:
 assert e['load_ready_accepted'] is True and e['cycles_completed']==1
 for key in ['load_ready_attempts','load_successful_sends','gateway_ready_sends','room_id','match_id','load_active_match','ready_prompt']:
  assert e[key]==before[key]
 assert e['room_id']==c['observed_room_id'] and e['match_id']==e['load_active_match']==c['observed_match_id']
assert c['ready_send_count']==after['gateway_ready_sends'] and c['actual_load_ready_attempts']==after['load_ready_attempts']
assert c['actual_load_ready_successful_sends']==after['load_successful_sends']>=1
root=native/'second_cycle_old_original_started';held_file=root/'first-started.original.bin';delivered_file=root/'delivered-first-started.original.bin'
assert held_file.stat().st_size==delivered_file.stat().st_size==first[0]['bytes'] and sha(held_file)==sha(delivered_file)
assert {r['match_id'] for r in target['postgres']['match_rows']}=={first[0]['match_id'],second[0]['match_id']}
assert len({r['room_id'] for r in target['postgres']['match_rows']})==2
pg=target['postgres'];seed=read(root/'fixture-seeded.json')
assert len(pg['non_bot_player_ids'])==2 and set(pg['non_bot_player_ids'])=={seed['player_id']}=={c['own_user_id']}
item=next(e for e in pg['equipment_states'] if e['instance_id']==seed['equipment_id']);assert item['location']=='RelicPile'
assert pg['death_equipment_movements']==1 and pg['equipment_locks']==1
proof={'ok':True,'integration_source_sha':head,'compiled_source_sha':plan['compiled_source_sha'],
 'actual_fixture_projection_sha':report['source_sha'],'fixture_projection_is_release_HEAD':False,
 'native_baseline_and_target_cases_passed':2,'actual_completed_first_cycle_with_legal_exit_and_ACK':True,
 'real_second_distinct_room_before_original_first_started_replay':True,'same_real_player_in_both_Postgres_matches':True,'original_seeded_armor_death_disposition_RelicPile_verified':True,'correct_single_preparation_lock_and_single_death_movement':True,
 'first_and_delivered_original_started_binary_SHA_equal':True,'original_packet_sha256':sha(held_file),
 'first_match_id':first[0]['match_id'],'second_match_id':second[0]['match_id'],
 'second_room_ready_prompt_attempt_send_success_and_cycle_counts_stable':True,
 'stable_after_replay_observation_ms':after['at_ms']-immediate['at_ms'],
 'both_real_matches_and_distinct_rooms_verified_in_Postgres':True,'actual_Godot_route_probe_clear':True,
 'actual_postgres_asset_and_hold_postconditions_clear':True,'original_95s_case_15s_READY_deadlines_preserved':True,
 'all_original_G_members_rehashed':len(manifest['files']),'archive_SHA_CRC_rechecked':True,
 'current_production_source_and_runtime_unchanged':True,'controlled_test_overrides':2,
 'canonical_case':'PR13-A04.2-T03','canonical_aliases':['LOAD-04.1-T02','LOAD-05.2-T01','PR13-A04.4-T03'],'native_reexecution_count':0,'same_actual_two_cycle_execution_reused_without_extra_samples':True,'supported_profile':'POSTGRES','LIVE_not_closed':True,'MAIN_accepted':False}
OUT.mkdir();(OUT/'independent-G-check.original.json').write_bytes((json.dumps(proof,indent=2)+'\n').encode());print(json.dumps(proof))
