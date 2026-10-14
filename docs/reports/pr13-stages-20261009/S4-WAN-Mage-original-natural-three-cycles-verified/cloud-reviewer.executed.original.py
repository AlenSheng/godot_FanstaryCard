import ast, hashlib, json, math, statistics, subprocess, uuid
from pathlib import Path

E=Path('/home/ubuntu/pr13-acceptance-20261009/evidence/WAN-Mage-natural3-r3-original-review')
manifest=json.loads((E/'input-manifest.original.json').read_bytes())
assert manifest['source']=='OriginalGBytesOnly'
for row in manifest['files']:
 p=E/'originals'/row['path']; assert p.stat().st_size==row['bytes'] and hashlib.sha256(p.read_bytes()).hexdigest()==row['sha256']
report=json.loads((E/'originals/player.original.json').read_bytes())
driver=json.loads((E/'originals/driver-result.original.json').read_bytes())
raw=(E/'originals/player.original.json.telemetry.jsonl').read_bytes(); assert raw.endswith(b'\n')
rows=[json.loads(l) for l in raw.splitlines()]
assert [r['event_seq'] for r in rows]==list(range(1,report['event_seq_max']+1)) and report['audit_lost_count']==0
assert all(r['client_id']==report['client_id'] and r['run_id']==report['run_id'] and r['process_epoch']==report['process_epoch'] for r in rows)
uid=report['user_id']; assert str(uuid.UUID(uid))==uid
parts=["'player_id','"+uid+"'"]
for table,key,selection,order in [
 ('player_wallets','wallets','*','player_id'),
 ('economy_ledger','ledger','*','created_at,ledger_id'),
 ('match_settlements','settlements','settlement_id,match_id,player_id,result,created_at,acknowledged_at','created_at'),
 ('match_players','match_members','*','match_id'),
 ('preparations','preparations','preparation_id,status','preparation_id')]:
 parts.append("'"+key+"',(SELECT coalesce(json_agg(row_to_json(x)),'[]'::json) FROM (SELECT "+selection+" FROM "+table+" WHERE player_id='"+uid+"' ORDER BY "+order+") x)")
for table,key,condition in [('match_tickets','queued_tickets',"status='Queued'"),('settlement_asset_holds','pending_holds',"state='Pending'"),('match_players','active_members',"state IN ('Assigned','Ready','Active')")]:
 parts.append("'"+key+"',(SELECT count(*) FROM "+table+" WHERE player_id='"+uid+"' AND "+condition+")")
query="BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY; SET LOCAL statement_timeout='10s'; SELECT json_build_object("+','.join(parts)+"); ROLLBACK;"
out=subprocess.check_output(['docker','exec','fantasycard-cloud-postgres-1','psql','-X','-U','fantasycard','-d','fantasycard','-At','-v','ON_ERROR_STOP=1','-c',query],text=True)
db=next(json.loads(l) for l in out.splitlines() if l.startswith('{'))
assert not (E/'player-readonly-SQL.original.json').exists()
(E/'player-readonly-SQL.original.json').write_text(json.dumps(db,indent=2)+'\n')
source=subprocess.check_output(['git','-C','/opt/fantasycard-github','show','HEAD:tools/gameplay_load_validation.py'],text=True)
tree=ast.parse(source); fn=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='summarize')
exec(compile(ast.Module(body=[fn],type_ignores=[]),'<CurrentRegisteredSummarize>','exec'))
http=[r for r in rows if r.get('type')=='http']
durations=[r['duration_ms'] for r in http if isinstance(r.get('duration_ms'),(int,float)) and math.isfinite(r['duration_ms']) and r['duration_ms']>=0]
assert len(durations)==len(http)
ack=[{'cycle_id':r.get('cycle_id'),'match_id':r.get('match_id'),'completion_stage':r.get('completion_stage')} for r in rows if r.get('event_type')=='settlement.acknowledged']
samples=[json.loads(l) for l in (E/'originals/cloud-monitor.original.jsonl').read_bytes().splitlines()]
missing_actor=[{'at_unix_ms':s['at_unix_ms'],'client_stage':s.get('local_client_status',{}).get('stage'),'safety_windows':s.get('safety_windows')} for s in samples if s['resources'].get('actor_wait') is None]
v={'ok':True,'scope':'Postcollection canceled WAN originals and authoritative one-player SQL; no new gameplay or acceptance','all_original_G_input_SHA_verified':len(manifest['files']),'complete_raw_sequence_contiguous':True,'raw_events':len(rows),'audit_lost_count':report['audit_lost_count'],'real_login_bootstrap_and_room_start_observed':all(next(c['passed'] for c in report['checks'] if c['name']==n) for n in ['realtime_connected','login_and_bootstrap','room_started']),'reported_natural_cycles':report['cycles_completed'],'original_report_ok':report['ok'],'original_cancellation_preserved':driver['observation_stop_reason'],'ack_events':ack,'HTTP_all_originals_descriptive':summarize(durations),'HTTP_actual_non_success_rows':[{'path':r['path'],'status':r['status'],'result':r['result']} for r in http if not r['ok']],'actor_metric_missing_windows':missing_actor,'SQL_settlements':len(db['settlements']),'SQL_settlement_results':[r['result'] for r in db['settlements']],'SQL_all_existing_settlements_acknowledged':all(r['acknowledged_at'] is not None for r in db['settlements']),'SQL_pending_holds':db['pending_holds'],'SQL_active_members':db['active_members'],'SQL_queued_tickets':db['queued_tickets'],'SQL_preparation_states':[r['status'] for r in db['preparations']],'original_client_cleanup':report['cleanup'],'natural_cycle_or_performance_accepted':False,'MAIN_accepted':False}
assert not (E/'review.original.json').exists()
(E/'review.original.json').write_text(json.dumps(v,indent=2)+'\n')

assert report['ok'] and report['cycles_completed']==3 and report['elapsed_ms']<600000 and driver['observation_stop_reason'] is None
assert report['cleanup']['state']=='Passed' and report['cleanup']['active_preparation'] is None and report['cleanup']['unfinished_match'] is None and report['cleanup']['unfinished_settlement'] is None
completed=[r for r in rows if r.get('event_type')=='cycle.completed'];assert len(completed)==len(ack)==3 and len({r['match_id'] for r in completed})==3
assert all(r['phase']=='settlement' and r.get('completion_stage')!='drain_ack_only' for r in completed)
assert all(r['completion_stage']!='drain_ack_only' for r in ack)
assert {r['match_id'] for r in completed}=={r['match_id'] for r in ack}=={r['match_id'] for r in db['settlements']}
assert len(db['settlements'])==3 and all(r['result'] in ['Dead','Extracted'] and r['acknowledged_at'] is not None for r in db['settlements'])
assert db['pending_holds']==db['active_members']==db['queued_tickets']==0 and all(r['status']=='Settled' for r in db['preparations'])
forbidden=[r for r in rows if 'fallback' in r.get('event_type','') or 'abandon' in r.get('event_type','') or r.get('completion_stage')=='drain_ack_only'];assert not forbidden
realtime=[r for r in rows if r.get('type')=='realtime'];command_durations=[r['duration_ms'] for r in realtime if isinstance(r.get('duration_ms'),(int,float)) and math.isfinite(r['duration_ms']) and r['duration_ms']>=0];assert len(command_durations)==len(realtime)
actor_samples=[s['resources']['actor_wait'] for s in samples if s['resources'].get('actor_wait') is not None]
assert samples and all(s['current_metric_service_instance_id']=='d44e1a80-1a6a-4628-9ca3-21dbf81dea10' and s['actual_container_id']=='9300fdf0c8701ff2c03b232d4d29e58cfa80b6a5c8673979b7ba5fcccb9362e9' and s['actual_metric_export_interval_ms']==1000 and s['game_metrics_exporter_up']==1 for s in samples)
assert all(s['resources'][k] is not None for s in samples for k in ['cpu','memory_available_bytes','disk_available'])
assert all(s['resources']['memory_available_bytes']>=500000000 and s['health_status']==200 and s['health_elapsed_ms']<=10000 for s in samples)
assert all(n<3 for s in samples for n in s['safety_windows'].values())
by_cycle=[]
for c in completed:
 cohort=[r for r in rows if r['cycle_id']==c['cycle_id']];observations=[r for r in cohort if r.get('event_type')=='battle.observed'];assert observations
 rr=[r for r in cohort if r.get('type')=='realtime'];assert rr
 by_cycle.append({'cycle_id':c['cycle_id'],'match_id':c['match_id'],'raw_actual_battle_observations':len(observations),'actual_realtime_response_rows':len(rr),'normal_ACK_without_drain':True,'SQL_result':next(r['result'] for r in db['settlements'] if r['match_id']==c['match_id'])})
result={'ok':True,'scope':'Original single-Mage three-natural-cycle baseline only; current public protected runtime','complete_raw_events':len(rows),'audit_lost_count':0,'original_source_rows_and_sequential_identity_verified':True,'actual_original_HTTP_latency':summarize(durations),'actual_original_realtime_latency':summarize(command_durations),'HTTP_non_success_rows':v['HTTP_actual_non_success_rows'],'realtime_non_success_rows':[{'action':r.get('action'),'result':r.get('result'),'response_type':r.get('response_type'),'request_id':r.get('request_id')} for r in realtime if r.get('result')!='ok'],'raw_natural_cycles':by_cycle,'SQL_results':[r['result'] for r in db['settlements']],'SQL_all_three_ACK_and_no_pending_holds_active_members_or_tickets':True,'client_bootstrap_route_and_assets_clear':True,'natural_single_Mage_baseline_verified':True,'actor_monitor_samples':len(samples),'actor_finite_samples':len(actor_samples),'actor_metric_source_only_current_runtime':True,'cloud_CPU_max_percent':max(s['resources']['cpu'] for s in samples),'cloud_root_disk_min_percent':min(s['resources']['disk_available'] for s in samples),'cloud_memory_min_bytes':min(s['resources']['memory_available_bytes'] for s in samples),'original_three_window_STOP_policy_not_triggered':True,'old_R1_and_R2_failures_preserved':True,'all_other_classes_ten_users_faults_capacity_and_full_LIVE_matrix_unproven':True,'MAIN_accepted':False}
p=E/'natural-baseline-review.original.json';assert not p.exists();p.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))

