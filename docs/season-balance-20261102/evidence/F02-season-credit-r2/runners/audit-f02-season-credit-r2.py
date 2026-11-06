from pathlib import Path
import json,hashlib,tarfile,xml.etree.ElementTree as ET
base=Path(__file__).parent;repo=Path.cwd();root=base/'f02-season-credit-cloud-r2';public=root/'public'
result=json.loads((root/'result.json').read_bytes());assert result['exit']==0 and result['guard_ok'] and result['input_unchanged'] and result['local_binary_inputs_unchanged'] and result['schemas_still_present']==[]
assert hashlib.sha256((root/'public-evidence.tar.gz').read_bytes()).hexdigest()==result['collected_raw_archive_sha256']
with tarfile.open(root/'public-evidence.tar.gz') as bundle:
 for member in bundle.getmembers():assert hashlib.sha256(bundle.extractfile(member).read()).digest()==hashlib.sha256((public/member.name).read_bytes()).digest()
ns={'t':'http://microsoft.com/schemas/VisualStudio/TeamTest/2010'};cases=ET.parse(public/'cases.trx').findall('.//t:UnitTestResult',ns)
assert len(cases)==4 and all(c.attrib['outcome']=='Passed' for c in cases)
rows=[json.loads(s) for s in (public/'process-logs/receipts.jsonl').read_text(encoding='utf-8').splitlines()]
def group(name):return [r['evidence'] for r in rows if r['caseId']==name]
starts=group('process-start');stops=group('process-stop');assert len(starts)==len(stops)==8
assert {s['Id'] for s in starts}=={s['ProcessId'] for s in stops} and len({s['Id'] for s in starts})==8
assert all(s['termination']=='Process.Kill(entireProcessTree:true)' for s in stops)
idle=group('SEASON17-credit-restart');assert len(idle)==3 and {r['archiveState'] for r in idle}=={'valid','missing','corrupt'}
for row in idle:assert row['firstPid']!=row['secondPid'] and row['credit']==.75 and row['rateBasisPoints']==500
wires=group('SEASON17-wire-snapshot');assert len(wires)==10
for row in wires:
 actual=row['actual'];numerical=actual['Player']['NumericalState']
 assert actual['Player']['Phase']=='ActionBar' and actual['Player']['Combat']['MaximumHp']==70
 if actual['ConfigVersion']=='season-v1-config-16':
  assert numerical['FenxianPolicy']=='SeasonBoundedRhythm' and numerical['FenxianReturnCredit'] is None and numerical['FenxianReturnRateBasisPoints'] is None
 else:
  assert actual['ConfigVersion']=='season-v1-config-17' and numerical['FenxianPolicy']=='SeasonRateBudgetedRhythm' and numerical['FenxianReturnCredit']=='0.75' and numerical['FenxianReturnRateBasisPoints']==500
entries=group('SEASON17-entry-wire');recovered=group('SEASON17-active-recovered-wire');final=group('SEASON17-real-entry-restart');assert len(entries)==len(recovered)==4 and len(final)==1
f=final[0];assert f['players']==4 and f['bots']==0 and f['successfulPlayerCasts']==f['completedEncounters']==0 and f['firstPid']!=f['secondPid']
assert {e['actual']['Player']['PlayerId'] for e in entries}=={e['actual']['Player']['PlayerId'] for e in recovered}
credits=[]
for row in recovered:
 a=row['actual'];n=a['Player']['NumericalState'];value=float(n['FenxianReturnCredit'])
 assert a['MatchId']==f['matchId'] and a['RoomId']==f['roomId'] and a['ConfigVersion']=='season-v1-config-17'
 assert a['Player']['HeroClass']=='Mage' and a['Player']['Combat']['MaximumHp']==70 and a['Player']['Combat']['Hp']>0
 assert n['FenxianPolicy']=='SeasonRateBudgetedRhythm' and n['FenxianReturnRateBasisPoints']==500 and 0<row['previousCredit']<=value<=2
 credits.append(dict(previous=row['previousCredit'],recovered=value))
resources=[json.loads(s) for s in (public/'resources.original.jsonl').read_text().splitlines()];assert all(r['guard_ok'] for r in resources)
cleanup=json.loads((public/'cleanup.original.json').read_bytes());cache=json.loads((public/'input-cache-cleanup.original.json').read_bytes())
assert cleanup['owned_container_removed'] and cleanup['private_env_removed'] and cache['tmpfs_unmounted'] and cache['input_files_removed']
pin=json.loads((base/'f02-season-credit-build-r3/source-pin.json').read_bytes());assert all(hashlib.sha256((repo/n).read_bytes()).hexdigest()==h for n,h in pin.items())
d=json.loads((base/'current-journey-client-continuation-20261105.json').read_bytes());assert all(hashlib.sha256(Path(b['source']).read_bytes()).hexdigest()==b['sha256'] for b in d['D03_latest_banks'])
proof=dict(passed=4,skipped=0,unique_actual_server_processes=8,abrupt_process_stops=8,idle_actual_wire_observations=10,live_entry_accounts=4,live_entry_wire_observations=4,recovered_active_wire_observations=4,actual_match_admissions=1,declared_checkpoint_match_records=6,live_entry_bots=0,successful_player_casts=0,completed_encounters=0,new_B05_encounters=0,new_D03_encounters=0,new_D02_encounters=0,credits=credits,minimum_cloud_RAM=min(r['available_ram'] for r in resources),minimum_cloud_disk=min(r['free_disk'] for r in resources),minimum_cloud_disk_fraction=min(r['disk_fraction'] for r in resources),schemas_removed=4,container_env_tmpfs_cleaned=True,source_unchanged=True,capital_banks_unchanged=True,scope='Current17 actual entry and new/old policy process recovery only; not native capacity or full settlement fault acceptance',raw_worker_field_erratum='Inherited raw result new_matches=0 means no completed/simulated gameplay workload; it is not a count of persisted match rows. Six declared idle checkpoint matches plus one actual four-account match were created across four disposable schemas.',raw_optional_library_diagnostic='Runtime printed missing libgssapi_krb5.so.2; password-auth PG and all4 tests passed. No Kerberos acceptance is claimed.',progress='29/35',F02_whole_complete=False,whole_goal_complete=False,production_modified=False)
p=base/'f02-season-credit-independent-audit-r2.derived.json';assert not p.exists();p.write_text(json.dumps(proof,indent=2)+'\n');print(json.dumps(proof))
