from pathlib import Path
import json,subprocess,ctypes,time,re,hashlib,os
b=Path(__file__).parent
private=Path(r'G:\PR13Evidence\private\season-balance-20261102-f03-google-r1')
data=private/'pgdata'
pg=Path(r'G:\Program Files\GodotFiles\godot_FanstaryCard\tools\engine-local\protected\postgres\pgsql\bin')
out=b/'f01-support-week-db-audit-r1'
control=private/'f01-support-week-r1/control.private.json'
original=control.read_bytes();state=json.loads(original)
assert state['Status']=='Completed' and state['NextIndex']==42 and state['CurrentCase'] is None and len(state['Finished'])==42
assert re.fullmatch('f01_calendar_[a-f0-9]{32}',state['Schema'])
assert not out.exists() and not (data/'postmaster.pid').exists();out.mkdir()
class Memory(ctypes.Structure):
 _fields_=[('length',ctypes.c_ulong),('load',ctypes.c_ulong)]+[(n,ctypes.c_ulonglong) for n in ('total','available','total_page','available_page','total_virtual','available_virtual','extended')]
def available():
 m=Memory();m.length=ctypes.sizeof(m);assert ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m));return m.available
samples=[]
for _ in range(3):samples.append(available());time.sleep(1)
assert min(samples)>=3*1024**3
(out/'admission.original.json').write_text(json.dumps({'available':samples,'reserve_GiB':2,'startup_GiB':1})+'\n')
flags=subprocess.CREATE_NO_WINDOW|subprocess.BELOW_NORMAL_PRIORITY_CLASS
try:
 with (private/'f01-support-week-audit-start.private.log').open('wb') as log:
  child=subprocess.Popen([str(pg/'pg_ctl.exe'),'-D',str(data),'-l',str(private/'f01-support-week-audit-pg.private.log'),'-o','-h 127.0.0.1 -p 8295 -c shared_buffers=64MB -c max_connections=20','-w','start'],stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,creationflags=flags)
  began=time.monotonic()
  while child.poll() is None:
   if available()<2*1024**3 or time.monotonic()-began>60:child.kill();child.wait();raise RuntimeError('Owned reconciliation startup guard')
   time.sleep(.25)
 assert child.returncode==0
 sql=f"""SET search_path TO {state['Schema']}; BEGIN READ ONLY;
 SELECT json_build_object(
 'season_wallet_mismatches',COALESCE((SELECT json_agg(x) FROM(
 SELECT w.player_id,w.gold,w.equipment_fragments,w.blueprint_marks,w.orange_blueprint_marks,
 COALESCE(sum(l.delta) FILTER(WHERE l.currency='Gold'),0) gold_sum,
 COALESCE(sum(l.delta) FILTER(WHERE l.currency='EquipmentFragments'),0) fragment_sum,
 COALESCE(sum(l.delta) FILTER(WHERE l.currency='BlueprintMarks'),0) blueprint_sum,
 COALESCE(sum(l.delta) FILTER(WHERE l.currency='OrangeBlueprintMarks'),0) orange_sum
 FROM player_season_wallets w LEFT JOIN economy_ledger l ON l.player_id=w.player_id AND l.season_id=w.season_id
 WHERE w.season_id='f01-support-current17' GROUP BY w.player_id,w.gold,w.equipment_fragments,w.blueprint_marks,w.orange_blueprint_marks
 HAVING w.gold<>COALESCE(sum(l.delta) FILTER(WHERE l.currency='Gold'),0)
 OR w.equipment_fragments<>COALESCE(sum(l.delta) FILTER(WHERE l.currency='EquipmentFragments'),0)
 OR w.blueprint_marks<>COALESCE(sum(l.delta) FILTER(WHERE l.currency='BlueprintMarks'),0)
 OR w.orange_blueprint_marks<>COALESCE(sum(l.delta) FILTER(WHERE l.currency='OrangeBlueprintMarks'),0))x),'[]'::json),
 'permanent_soul_mismatches',COALESCE((SELECT json_agg(x) FROM(
 SELECT m.player_id,m.warrior_soul,m.priest_soul,m.mage_soul,m.guardian_soul,
 COALESCE(sum(l.delta) FILTER(WHERE l.currency='WarriorSoul'),0) warrior_sum,
 COALESCE(sum(l.delta) FILTER(WHERE l.currency='PriestSoul'),0) priest_sum,
 COALESCE(sum(l.delta) FILTER(WHERE l.currency='MageSoul'),0) mage_sum,
 COALESCE(sum(l.delta) FILTER(WHERE l.currency='GuardianSoul'),0) guardian_sum
 FROM player_materials m LEFT JOIN economy_ledger l ON l.player_id=m.player_id
 GROUP BY m.player_id,m.warrior_soul,m.priest_soul,m.mage_soul,m.guardian_soul
 HAVING m.warrior_soul<>COALESCE(sum(l.delta) FILTER(WHERE l.currency='WarriorSoul'),0)
 OR m.priest_soul<>COALESCE(sum(l.delta) FILTER(WHERE l.currency='PriestSoul'),0)
 OR m.mage_soul<>COALESCE(sum(l.delta) FILTER(WHERE l.currency='MageSoul'),0)
 OR m.guardian_soul<>COALESCE(sum(l.delta) FILTER(WHERE l.currency='GuardianSoul'),0))x),'[]'::json),
 'activity_accounts',COALESCE((SELECT json_agg(a) FROM(SELECT player_id,event_id,earned,spent,version FROM player_season_activity_accounts ORDER BY player_id,event_id)a),'[]'::json),
 'activity_receipts',COALESCE((SELECT json_agg(r) FROM(SELECT player_id,event_id,rule_id,quantity,token_cost,reward_kind,reward_amount,state FROM season_activity_redemptions ORDER BY player_id,event_id,created_at)r),'[]'::json),
 'match_statuses',(SELECT json_object_agg(status,n) FROM(SELECT status,count(*) n FROM matches GROUP BY status)t),
 'human_settlements',(SELECT count(*) FROM match_settlements),
 'equipment_source_counts',(SELECT json_agg(q) FROM(SELECT source_kind,location,count(*) n FROM equipments GROUP BY source_kind,location ORDER BY source_kind,location)q),
 'ledger_rows',(SELECT count(*) FROM economy_ledger),
 'pending_holds',(SELECT count(*) FROM settlement_asset_holds WHERE state='Pending'),
 'active_preparations',(SELECT count(*) FROM preparations WHERE status IN('Active','Queued')),
 'card_count',(SELECT count(*) FROM player_cards),
 'db_schema','{state['Schema']}'); ROLLBACK;"""
 result=subprocess.run([str(pg/'psql.exe'),'-h','127.0.0.1','-p','8295','-U','branch_test','-d','postgres','-XAt','-v','ON_ERROR_STOP=1','-c',sql],capture_output=True,text=True,creationflags=flags,timeout=30)
 (out/'readonly-audit.original.sql').write_text(sql,encoding='utf-8')
 (out/'readonly-audit.original.log').write_text(result.stdout+result.stderr,encoding='utf-8');assert result.returncode==0
 facts,_=json.JSONDecoder().raw_decode(result.stdout[result.stdout.index('{'):])
 (out/'facts.original.json').write_text(json.dumps(facts,indent=2)+'\n')
 assert not facts['season_wallet_mismatches'] and not facts['permanent_soul_mismatches']
 assert facts['human_settlements']==42 and facts['pending_holds']==0 and facts['active_preparations']==0
 assert all(0<=row['spent']<=row['earned']<=12 for row in facts['activity_accounts'])
 assert facts['match_statuses']=={'Completed':42}
 old_state=json.loads((private/'f01-calendar-r1/control.private.json').read_bytes());old_schema=old_state['Schema']
 assert re.fullmatch('f01_calendar_[a-f0-9]{32}',old_schema) and old_schema!=state['Schema']
 original_audit=json.loads((b/'f01-calendar-evidence-audit-r2.derived.json').read_bytes())
 expected={p['final']['wallet']['PlayerId']:{k:p['final']['wallet'].get(k,0) for k in ['Gold','EquipmentFragments','BlueprintMarks','OrangeBlueprintMarks']} for p in original_audit['profiles']}
 old_sql=f"""BEGIN READ ONLY; SELECT json_build_object('wallets',(SELECT json_agg(w) FROM(
 SELECT player_id::text AS "PlayerId",gold AS "Gold",equipment_fragments AS "EquipmentFragments",blueprint_marks AS "BlueprintMarks",orange_blueprint_marks AS "OrangeBlueprintMarks"
 FROM {old_schema}.player_season_wallets WHERE season_id='f01-calendar-current17' ORDER BY player_id)w),
 'completed_matches',(SELECT count(*) FROM {old_schema}.matches WHERE status='Completed'),
 'settlements',(SELECT count(*) FROM {old_schema}.match_settlements),
 'ledger_rows',(SELECT count(*) FROM {old_schema}.economy_ledger)); ROLLBACK;"""
 old_result=subprocess.run([str(pg/'psql.exe'),'-h','127.0.0.1','-p','8295','-U','branch_test','-d','postgres','-XAt','-v','ON_ERROR_STOP=1','-c',old_sql],capture_output=True,text=True,creationflags=flags,timeout=30)
 (out/'old-main-readonly.original.sql').write_text(old_sql,encoding='utf-8');(out/'old-main-readonly.original.log').write_text(old_result.stdout+old_result.stderr,encoding='utf-8');assert old_result.returncode==0
 old_facts,_=json.JSONDecoder().raw_decode(old_result.stdout[old_result.stdout.index('{'):]);observed={w['PlayerId']:{k:w[k] for k in ['Gold','EquipmentFragments','BlueprintMarks','OrangeBlueprintMarks']} for w in old_facts['wallets']}
 assert observed==expected and old_facts['completed_matches']==old_facts['settlements']==252 and old_facts['ledger_rows']==1374
 (out/'old-main-unchanged.derived.json').write_text(json.dumps(dict(original_9_wallets_exactly_unchanged=True,old252matches_and_settlements_unchanged=True,old1374ledger_count_unchanged=True,old_and_new_schemas_separate=True),indent=2)+'\n')

 proof={'actual_synthetic_schema':state['Schema'],'wallet_and_soul_ledger_sums_match':True,'human_settlements':42,'pending_holds':0,'active_preparations':0,'schema_intentionally_retained':True,'no_new_gameplay_starts':True}
 (out/'result.json').write_text(json.dumps(proof,indent=2)+'\n');print(json.dumps(proof))
finally:
 if (data/'postmaster.pid').exists():
  with (private/'f01-support-week-audit-stop.private.log').open('wb') as log:
   stopped=subprocess.run([str(pg/'pg_ctl.exe'),'-D',str(data),'-m','fast','-w','stop'],stdout=log,stderr=subprocess.STDOUT,creationflags=flags,timeout=60);assert stopped.returncode==0
 assert not (data/'postmaster.pid').exists()
