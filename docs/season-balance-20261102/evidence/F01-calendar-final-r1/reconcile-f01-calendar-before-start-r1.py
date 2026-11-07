from pathlib import Path
import json,subprocess,ctypes,time,re,hashlib,os
b=Path(__file__).parent
private=Path(r'G:\PR13Evidence\private\season-balance-20261102-f03-google-r1')
data=private/'pgdata'
pg=Path(r'G:\Program Files\GodotFiles\godot_FanstaryCard\tools\engine-local\protected\postgres\pgsql\bin')
out=b/'f01-calendar-before-start-reconcile-r1'
control=private/'f01-calendar-r1/control.private.json'
original=control.read_bytes();state=json.loads(original)
case='F01-novice-Guardian-D01-A1'
assert state['CurrentCase']==case and state['NextIndex']==0 and not state['Finished']
assert re.fullmatch('f01_calendar_[a-f0-9]{32}',state['Schema'])
player=next(a['Player'] for a in state['Actors'] if a['Id']=='F01-novice-Guardian')
assert re.fullmatch('[a-f0-9-]{36}',player)
budget=json.loads(Path('docs/season-balance-20261102/F01-BUDGET.json').read_bytes())
entries=[json.loads(x) for x in Path(budget['journal']).read_text(encoding='utf-8').splitlines()]
assert not any(r['payload']['caseId']==case for r in entries)
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
 with (private/'f01-reconcile-start.private.log').open('wb') as log:
  child=subprocess.Popen([str(pg/'pg_ctl.exe'),'-D',str(data),'-l',str(private/'f01-reconcile-pg.private.log'),'-o','-h 127.0.0.1 -p 8295 -c shared_buffers=64MB -c max_connections=20','-w','start'],stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,creationflags=flags)
  began=time.monotonic()
  while child.poll() is None:
   if available()<2*1024**3 or time.monotonic()-began>60:child.kill();child.wait();raise RuntimeError('Owned reconciliation startup guard')
   time.sleep(.25)
 assert child.returncode==0
 sql=f"""SET search_path TO {state['Schema']}; BEGIN READ ONLY;
 SELECT json_build_object(
 'card_nonzero_levels',(SELECT count(*) FROM player_cards WHERE player_id='{player}' AND level<>0),
 'weapon_nonzero_levels',(SELECT count(*) FROM class_weapons WHERE player_id='{player}' AND level<>0),
 'permanent_wallet',(SELECT gold+diamond FROM player_wallets WHERE player_id='{player}'),
 'permanent_materials',(SELECT warrior_soul+priest_soul+mage_soul+guardian_soul+equipment_fragments FROM player_materials WHERE player_id='{player}'),
 'consumables',(SELECT health_potion_count+advanced_bag_count+top_bag_count FROM player_consumables WHERE player_id='{player}'),
 'season_balance',(SELECT gold+equipment_fragments+challenge_marks+blueprint_marks+orange_blueprint_marks FROM player_season_wallets WHERE player_id='{player}' AND season_id='f01-calendar-current17'),
 'owned_equipment',(SELECT count(*) FROM equipments WHERE owner_id='{player}'),
 'preparations',(SELECT count(*) FROM preparations WHERE player_id='{player}'),
 'economy_ledger',(SELECT count(*) FROM economy_ledger WHERE player_id='{player}'),
 'movements',(SELECT count(*) FROM inventory_movements WHERE player_id='{player}'));
 ROLLBACK;"""
 result=subprocess.run([str(pg/'psql.exe'),'-h','127.0.0.1','-p','8295','-U','branch_test','-d','postgres','-XAt','-v','ON_ERROR_STOP=1','-c',sql],capture_output=True,text=True,creationflags=flags,timeout=30)
 (out/'readonly-query.original.sql').write_text(sql,encoding='utf-8')
 (out/'readonly-query.original.log').write_text(result.stdout+result.stderr,encoding='utf-8');assert result.returncode==0
 facts=json.loads(next(line for line in result.stdout.splitlines() if line.startswith('{')))
 assert all(value==0 for value in facts.values()),facts
 assert (b/'f01-calendar-r1/observations'/case/'lobby.original.jsonl').stat().st_size==0
 (out/'control.before.original.json').write_bytes(original)
 state.update(CurrentCase=None,Status='ManuallyReconciledBeforeStart',ManualLobbyResumeCase=case)
 with (control.with_suffix('.reconciled-next')).open('wb') as stream:
  stream.write((json.dumps(state,ensure_ascii=False,indent=2)+'\n').encode());stream.flush();os.fsync(stream.fileno())
 os.replace(control.with_suffix('.reconciled-next'),control)
 proof={'case':case,'same_schema':state['Schema'],'same_player':player,'actual_no_started_journal':True,'read_only_actual_db_zero_facts':facts,
  'original_control_sha256':hashlib.sha256(original).hexdigest(),'same_case_resume_subdirectory':'reconciled-before-start-r1','no_account_or_capital_reset':True,'new_gameplay_starts':0}
 (out/'result.json').write_text(json.dumps(proof,indent=2)+'\n');print(json.dumps(proof))
finally:
 if (data/'postmaster.pid').exists():
  with (private/'f01-reconcile-stop.private.log').open('wb') as log:
   stopped=subprocess.run([str(pg/'pg_ctl.exe'),'-D',str(data),'-m','fast','-w','stop'],stdout=log,stderr=subprocess.STDOUT,creationflags=flags,timeout=60);assert stopped.returncode==0
 assert not (data/'postmaster.pid').exists()
