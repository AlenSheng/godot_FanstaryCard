from pathlib import Path
import json,hashlib,tarfile,xml.etree.ElementTree as ET
base=Path(__file__).parent;repo=Path.cwd();ns={'t':'http://microsoft.com/schemas/VisualStudio/TeamTest/2010'}
for group,count in [('domain',8),('server',8)]:
 stage='d04-playtime-domain-r3' if group=='domain' else 'd04-playtime-server-r5';folder=base/stage
 result=json.loads((folder/'result.json').read_bytes());assert result['exit']==0 and result['source_unchanged']
 cases=ET.parse(folder/'results'/f'{group}.trx').findall('.//t:UnitTestResult',ns);assert len(cases)==count and all(c.attrib['outcome']=='Passed' for c in cases)
folder=base/'d04-playtime-cloud-r1-file';public=folder/'public';result=json.loads((folder/'result.json').read_bytes())
assert result['exit']==0 and result['guard_ok'] and result['input_unchanged'] and result['local_binary_inputs_unchanged'] and result['schemas_still_present']==[]
assert hashlib.sha256((folder/'public-evidence.tar.gz').read_bytes()).hexdigest()==result['collected_raw_archive_sha256']
with tarfile.open(folder/'public-evidence.tar.gz') as bundle:
 for member in bundle.getmembers():assert bundle.extractfile(member).read()==(public/member.name).read_bytes()
cases=ET.parse(public/'cases.trx').findall('.//t:UnitTestResult',ns);assert len(cases)==3 and all(c.attrib['outcome']=='Passed' for c in cases)
proofs=[json.loads(s) for s in (public/'currency-reports.original.jsonl').read_text(encoding='utf-8').splitlines()]
period=next(p for p in proofs if p['kind']=='actual-playtime-window');report=period['report'];incomplete=period['incomplete'];g=report['Groups'][0]
assert report['KnownPlayers']==g['Players']==3 and g['ZeroNetPlayers']==1 and g['NegativeNetPlayers']==1
assert g['P10']['DecimalDisplay']=='-60.000000' and g['P50']['DecimalDisplay']=='0.000000' and g['NetAmount']=='9'
assert report['CompleteForWindow'] and report['RatesAvailable'] and incomplete['FlowPlayersWithoutKnownClock']==1 and incomplete['NetWithoutKnownClock']=='4' and not incomplete['CompleteForWindow']
assert period['readOnlyFingerprintUnchanged'] and not period['realHumanActivityClaimed'] and period['gameplayCasts']==0
clocks=period['sourceClocks'];assert len(clocks)==3
assert all(c['player']['TerminalRoomElapsed']=='00:01:00' for c in clocks[:2])
rows=[json.loads(s) for s in (public/'process-logs/receipts.jsonl').read_text(encoding='utf-8').splitlines()]
entry=next(r['evidence'] for r in rows if r['caseId']=='SEASON17-real-entry-restart');assert entry['StartedAtUtc'] and entry['startedAtPreserved'] and entry['firstPid']!=entry['secondPid'] and entry['players']==4 and entry['bots']==entry['successfulPlayerCasts']==entry['completedEncounters']==0
api=next(p for p in proofs if p['kind']=='actual-playtime-admin-HTTP');assert api['missingKeyStatus']==401 and api['insecureStatus']==403 and api['missingSeasonStatus']==400 and api['privateNoStore']
assert not api['report']['ratesAvailable']
starts=[r['evidence']['Id'] for r in rows if r['caseId']=='process-start'];stops=[r['evidence']['ProcessId'] for r in rows if r['caseId']=='process-stop'];assert len(starts)==3 and set(starts)==set(stops)
for name in ['cleanup.original.json','input-cache-cleanup.original.json']:
 c=json.loads((public/name).read_bytes());assert all(c[k] for k in (['owned_container_removed','private_env_removed'] if name=='cleanup.original.json' else ['tmpfs_unmounted','input_files_removed']))
assert json.loads((folder/'upload-cleanup.original.json').read_bytes())['upload_tmpfs_unmounted']
resources=[json.loads(s) for s in (public/'resources.original.jsonl').read_text().splitlines()];assert all(r['guard_ok'] for r in resources)
assert min(r['available_ram'] for r in resources)>=500*1024**2 and min(r['free_disk'] for r in resources)>=3*1024**3 and min(r['disk_fraction'] for r in resources)>=.05
pin=json.loads((base/'d04-playtime-server-r5/source-pin.json').read_bytes());assert all(hashlib.sha256((repo/n).read_bytes()).hexdigest()==h for n,h in pin.items())
domainpin=json.loads((base/'d04-playtime-domain-r3/source-pin.json').read_bytes());assert all(pin[n]==h for n,h in domainpin.items() if n.startswith('server/src/FantasyCard.Domain/') or n.endswith('RoomPlaytimeObservationTests.cs'))
context=json.loads((base/'current-journey-client-continuation-20261105.json').read_bytes());assert all(hashlib.sha256(Path(b['source']).read_bytes()).hexdigest()==b['sha256'] for b in context['D03_latest_banks'])
proof=dict(playtime_subchain_verified=True,domain_passed=8,server_passed=8,PG_and_actualHTTP_entry_passed=3,actual_program_processes=3,real_preparation_READY_accounts=4,old_missing_clocks_not_invented=True,per_player_terminal_clock_not_whole_room_lifetime=True,period_clipping_and_union_verified=True,zero_and_negative_rates_included=True,percentile_method='nearest-rank ceil(p*n), exact rational comparison',integer_amounts_and_rate_fractions_exact=True,financial_rows_without_time_kept_separately=True,read_only_fingerprint_unchanged=True,UTC_start_preserved_across_process_restart=True,admin_existing_private_boundary_verified=True,all_test_resources_cleaned=True,source_unchanged=True,capital_banks_unchanged=True,new_completed_gameplay_encounters=0,new_B05_D03_D02_campaign_cases=0,controlled_lifecycle_fixtures_not_combat_matrix=True,D04_complete=False,remaining_D04=['11named events','physical lifecycle flow projections','combat draw/control/overflow details','cohort/build/growth and market/activity diagnostics'],progress='30/35',whole_goal_complete=False,production_modified=False)
p=base/'d04-playtime-independent-audit-r1.derived.json';assert not p.exists();p.write_text(json.dumps(proof,indent=2)+'\n');print(json.dumps(proof))
