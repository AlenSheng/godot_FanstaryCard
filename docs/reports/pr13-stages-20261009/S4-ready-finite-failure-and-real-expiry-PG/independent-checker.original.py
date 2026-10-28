"""Independent custody and actual-source/READY/SQL predicates; no experiments locally."""
import gzip,hashlib,json,subprocess
from pathlib import Path
B=Path(__file__).parent;R=B.parents[1];OUT=B/'Ready-terminal-PG-r2-independent-G-check'
assert not OUT.exists()
def read(p):return json.loads(p.read_bytes())
def sha(p):
    h=hashlib.sha256()
    with p.open('rb') as f:
        for block in iter(lambda:f.read(1024**2),b''):h.update(block)
    return h.hexdigest()
receipt=read(B/'Ready-terminal-PG-r2-complete-original-G-backup/complete-original-G-receipt.original.json')
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
assert result['actual_native_job_exit_code']==0 and result['actual_native_PG_rows']==3
assert result['owned_containers_removed'] and result['private_environment_removed_after_owned_containers_ended']
assert result['isolated_PG_schemas_before']==result['isolated_PG_schemas_after']==0
native=G/'evidence/persistent-output/native';report=read(native/'report.json')
assert report['ok'] and report['case_count']==report['passed_case_count']==report['planned_case_count']==3
assert not report['source_dirty'] and report['owned_fixture_databases_removed'] and report['owned_server_stopped']
assert report['source_sha']==read(G/'evidence/prepared.original.json')['owned_projection_commit']
prebuilt=read(native/'actual-prebuilt-server.json');assert prebuilt['source_rebuilt'] is False and prebuilt['server_assembly_sha256']==plan['actual_server_assembly_sha256']
assert sha(native/'server-frozen/FantasyCard.Server.dll')==plan['actual_server_assembly_sha256']
for command in read(native/'commands.json'):
    assert command['exit_code']==0
    if command['label'].endswith('-godot'):assert command['deadline_seconds']==95
cases={row['case']:row for row in report['cases']}
assert set(cases)=={'normal_ready','all_three_sends_false','matched_reply_after_actual_deadline'}
for name,case in cases.items():
 c=case['actual'];pg=case['postgres']
 assert case['passed'] and case['postgres_passed'] and case['exit_code']==0
 assert c['passed'] and c['local_terminal'] and c['route_probe_clear'] and c['cleanup']['state']=='Passed' and c['ready_send_after_stop']==0
 assert pg['matches']==pg['rooms']==1 and pg['ready_deadline_seconds']==[15]
 assert pg['locked_equipment']==pg['pending_settlement_holds']==0 and pg['equipment_locks']==1
 if name=='normal_ready':
  assert c['observed_match_id']==c['active_match_id']==pg['match_rows'][0]['match_id'] and c['observed_room_id']==pg['match_rows'][0]['room_id']
 else:
  assert c['original_finish_ok'] is False and not c['observed_room_id']
  assert pg['human_match_states']==[{'state':'Removed'}] and pg['equipment_releases']==1 and pg['settlements']==0
  assert pg['match_rows'][0]['observed_at_unix_ms']>=pg['match_rows'][0]['ready_deadline_unix_ms']
c=cases['all_three_sends_false']['actual'];false=[e for e in c['trace'] if e['event']=='controlled_all_send_false']
assert c['ready_send_count']==c['actual_load_ready_attempts']==3 and c['actual_load_ready_successful_sends']==0
assert [e['attempt'] for e in false]==[1,2,3] and all(e['socket_write_performed'] is False for e in false)
assert sum(x['name']=='ready_send_exhausted' and not x['passed'] for x in c['checks'])==1
c=cases['matched_reply_after_actual_deadline']['actual'];pg=cases['matched_reply_after_actual_deadline']['postgres']
assert c['ready_send_count']==c['actual_load_ready_attempts']==c['actual_load_ready_successful_sends']==0
assert sum(x['name'] in ['ready_ticket_terminal','ready_ticket_missing','room_start_timeout'] and not x['passed'] for x in c['checks'])==1
held=[e for e in c['trace'] if e['event']=='real_matched_response_held'];delivered=[e for e in c['trace'] if e['event']=='real_matched_response_delivered_after_deadline']
assert held and len(held)==len(delivered)
by={e['request_read_no']:e for e in held};assert len(by)==len(held)
for e in delivered:
 h=by[e['request_read_no']];assert h['observed_unix_ms']<h['actual_deadline_unix_ms']<e['observed_unix_ms']
 assert h['actual_deadline_unix_ms']==e['actual_deadline_unix_ms'] and abs(h['actual_deadline_unix_ms']-pg['match_rows'][0]['ready_deadline_unix_ms'])<2
 p=native/'matched_reply_after_actual_deadline'/('held-real-matched-response-read-%d.original.json'%e['request_read_no']);original=read(p)
 assert original['ok'] and original['data']['status']=='Matched' and original['data']['matchId']==pg['match_rows'][0]['match_id']
responses=[e for e in c['trace'] if e['event']=='ticket_response'];assert 2<=len(responses)<=32
assert any(e['status']=='Queued' for e in responses)
assert not any(e['event']=='room.ready.attempt' for e in c['trace'])
removed=[e for e in c['trace'] if e['event']=='actual_server_envelope' and e['kind']=='room.ready_removed']
assert removed and all(e['match_id']==pg['match_rows'][0]['match_id'] for e in removed)
assert not any(e['kind']=='room.ready_accepted' for e in c['trace'] if e['event']=='actual_server_envelope')
failed_terminal=[e for e in c['checks'] if e['name'] in ['ready_ticket_terminal','ready_ticket_missing','room_start_timeout'] and not e['passed']]
assert failed_terminal and pg['match_rows'][0]['observed_at_unix_ms']>=pg['match_rows'][0]['ready_deadline_unix_ms']
proof={'ok':True,'integration_source_sha':head,'compiled_source_sha':plan['compiled_source_sha'],'actual_fixture_projection_sha':report['source_sha'],'fixture_projection_is_release_HEAD':False,
 'actual_native_cases_passed':3,'all_three_actual_send_attempts_failed_with_zero_writes':True,'bounded_explicit_exhausted_terminal_verified':True,
 'matched_response_unmodified_and_real_deadline_SQL_matched':True,'matched_response_delivery_after_actual_ready_deadline':True,'zero_READY_sent_after_actual_deadline':True,
 'bounded_real_queued_to_removed_membership_ticket_queries':len(responses),'explicit_terminal_code':failed_terminal[0]['name'],'stored_ticket_may_remain_matched_not_fabricated_expired':True,'concurrent_delayed_matched_response_count':len(delivered),
 'original_95s_case_15s_READY_30s_botfill_preserved':True,'real_membership_removed_asset_release_and_route_clear':True,
 'all_original_G_members_rehashed':len(manifest['files']),'archive_SHA_CRC_rechecked':True,'current_production_source_and_runtime_unchanged':True,
 'canonical_cases_supported':['LOAD-04.2-T01','LOAD-04.2-T03','PR13-A04.1-T02','PR13-A04.1-T03'],'supported_profile':'POSTGRES','LIVE_not_closed':True,'MAIN_accepted':False}
OUT.mkdir();(OUT/'independent-G-check.original.json').write_bytes((json.dumps(proof,indent=2)+'\n').encode());print(json.dumps(proof))
