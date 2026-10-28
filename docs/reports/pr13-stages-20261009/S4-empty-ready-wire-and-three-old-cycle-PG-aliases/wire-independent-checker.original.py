"""Independent custody and actual-source/READY/SQL predicates; no experiments locally."""
import gzip,hashlib,json,subprocess
from pathlib import Path
B=Path(__file__).parent;R=B.parents[1];OUT=B/'Empty-ready-wire-PG-r1-independent-G-check-r2'
assert not OUT.exists()
def read(p):return json.loads(p.read_bytes())
def sha(p):
    h=hashlib.sha256()
    with p.open('rb') as f:
        for block in iter(lambda:f.read(1024**2),b''):h.update(block)
    return h.hexdigest()
receipt=read(B/'Empty-ready-wire-PG-r1-complete-original-G-backup/complete-original-G-receipt.original.json')
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
overrides={'client/tests/run_ready_stop_faults.py':plan['override_runner_sha256'], 'client/tests/run_ready_stop_faults.gd':plan['override_gd_sha256'],'client/network/gateway.gd':plan['override_gateway_sha256']}
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
assert result['actual_native_job_exit_code']==0 and result['actual_native_PG_rows']==1
assert result['owned_containers_removed'] and result['private_environment_removed_after_owned_containers_ended']
assert result['isolated_PG_schemas_before']==result['isolated_PG_schemas_after']==0
native=G/'evidence/persistent-output/native';report=read(native/'report.json')
assert report['ok'] and report['case_count']==report['passed_case_count']==report['planned_case_count']==1
assert not report['source_dirty'] and report['owned_fixture_databases_removed'] and report['owned_server_stopped']
assert report['source_sha']==read(G/'evidence/prepared.original.json')['owned_projection_commit']
prebuilt=read(native/'actual-prebuilt-server.json');assert prebuilt['source_rebuilt'] is False and prebuilt['server_assembly_sha256']==plan['actual_server_assembly_sha256']
assert sha(native/'server-frozen/FantasyCard.Server.dll')==plan['actual_server_assembly_sha256']
for command in read(native/'commands.json'):
    assert command['exit_code']==0
    if command['label'].endswith('-godot'):assert command['deadline_seconds']==95
cases={row['case']:row for row in report['cases']};assert set(cases)=={'normal_ready'}
case=cases['normal_ready'];c=case['actual'];pg=case['postgres']
assert case['passed'] and case['postgres_passed'] and case['exit_code']==0 and c['passed']
assert c['local_terminal'] and c['route_probe_clear'] and c['cleanup']['state']=='Passed' and c['ready_send_after_stop']==0
assert pg['matches']==pg['rooms']==1 and pg['ready_deadline_seconds']==[15]
assert pg['locked_equipment']==pg['pending_settlement_holds']==0 and pg['equipment_locks']==1
assert c['observed_match_id']==c['active_match_id']==pg['match_rows'][0]['match_id'] and c['observed_room_id']==pg['match_rows'][0]['room_id']
root=native/'normal_ready';captures=sorted(root.glob('actual-ready-wire-*.original.json'));assert captures and len(captures)==c['actual_load_ready_successful_sends']==c['ready_send_count']
rows=[]
for p in captures:
 info=read(p);binary=p.with_suffix('.bin')
 assert binary.is_file() and binary.stat().st_size==info['packet_bytes'] and info['actual_socket_put_packet_returned_OK']
 assert info['protocol_version']==1 and info['type']=='room.ready' and info['request_id']
 assert info['payload_bytes']==0 and info['decoded_ready_payload']=={} and info['decoder_error']==''
 # Decoder fills optional non-wire defaults; raw tags below decide actual presence.
 assert set(info['actual_envelope_keys'])<= {'protocol_version','type','request_id','payload','room_id','match_id','expected_revision'}
 assert info['envelope_match_id']==info['envelope_room_id']=='' and info['envelope_expected_revision']==0
 rows.append({'metadata_file':p.name,'actual_socket_binary_file':binary.name,'actual_socket_binary_sha256':sha(binary),'packet_bytes':binary.stat().st_size,'empty_command_payload_bytes':0,'actual_envelope_keys':info['actual_envelope_keys']})
# Inspect actual Protobuf wire fields, without schema decoder dropping unknown tags.
# Byte-level canonical verification is metadata only, no numerical experiment/statistics.
def varint(data,pos):
 value=0;shift=0
 while True:
  assert pos<len(data) and shift<70;b=data[pos];pos+=1;value|=(b&127)<<shift
  if not b&128:return value,pos
  shift+=7
for row in rows:
 data=(root/row['actual_socket_binary_file']).read_bytes();pos=0;fields=[]
 while pos<len(data):
  key,pos=varint(data,pos);field=key>>3;wire=key&7;assert field in [1,2,3,5] and wire in [0,2];fields.append(field)
  if wire==0:_,pos=varint(data,pos)
  else:
   length,pos=varint(data,pos);assert pos+length<=len(data)
   if field==5:assert length==0
   pos+=length
 assert pos==len(data) and len(fields)==len(set(fields))
 row['raw_wire_field_numbers']=fields
proof={'ok':True,'integration_source_sha':head,'compiled_source_sha':plan['compiled_source_sha'],'actual_fixture_projection_sha':report['source_sha'],'fixture_projection_is_release_HEAD':False,
 'actual_native_cases_passed':1,'actual_original_socket_ready_buffers_verified':rows,'actual_empty_RoomReadyCommand_payload':True,'no_undocumented_payload_or_match_room_revision_envelope_fields':True,
 'raw_wire_unknown_tags_rejected':True,'decoded_default_fields_not_wire_presence_proof':True,'actual_server_acceptance_room_and_Postgres_verified':True,'actual_route_and_asset_postconditions_clear':True,
 'all_original_G_members_rehashed':len(manifest['files']),'archive_SHA_CRC_rechecked':True,'production_source_and_runtime_unchanged':True,'observation_only_owned_gateway_copy':True,
 'canonical_case':'LOAD-04.1-T03','supported_profile':'POSTGRES','LIVE_not_closed':True,'MAIN_accepted':False}
OUT.mkdir();(OUT/'independent-G-check.original.json').write_bytes((json.dumps(proof,indent=2)+'\n').encode());print(json.dumps(proof))
