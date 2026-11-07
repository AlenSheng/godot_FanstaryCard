from pathlib import Path

b=Path(__file__).parent;source=(b/'audit-f01-calendar-private-db-r1.py').read_text('utf-8')
for old,new in [('f01-calendar-independent-db-audit-r1','f01-support-week-db-audit-r1'),('f01-calendar-r1/control.private.json','f01-support-week-r1/control.private.json'),('f01-final-audit','f01-support-week-audit'),('==252','==42'),("'human_settlements':252","'human_settlements':42"),("'f01-calendar-current17'","'f01-support-current17'")]:
    assert old in source;source=source.replace(old,new)
old="facts=json.loads(next(line for line in result.stdout.splitlines() if line.startswith('{')))"
new="facts,_=json.JSONDecoder().raw_decode(result.stdout[result.stdout.index('{'):])"
assert old in source;source=source.replace(old,new)
old=" assert all(0<=row['spent']<=row['earned']<=12 for row in facts['activity_accounts'])"
new=old+'''
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
 (out/'old-main-unchanged.derived.json').write_text(json.dumps(dict(original_9_wallets_exactly_unchanged=True,old252matches_and_settlements_unchanged=True,old1374ledger_count_unchanged=True,old_and_new_schemas_separate=True),indent=2)+'\\n')
'''
assert old in source;source=source.replace(old,new)
target=b/'audit-f01-support-week-db-r1.py';assert not target.exists();compile(source,str(target),'exec');target.write_text(source,encoding='utf-8');print(str(target))
