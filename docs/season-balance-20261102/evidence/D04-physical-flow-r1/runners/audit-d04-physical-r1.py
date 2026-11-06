from pathlib import Path
import json,hashlib,tarfile,xml.etree.ElementTree as ET
base=Path(__file__).parent;repo=Path.cwd();ns={'t':'http://microsoft.com/schemas/VisualStudio/TeamTest/2010'}
failed=json.loads((base/'d04-physical-flow-server-r1/result.json').read_bytes());assert failed['exit']!=0 and failed['source_unchanged'] and not list((base/'d04-physical-flow-server-r1/results').glob('*.trx'))
local=json.loads((base/'d04-physical-flow-server-r2/result.json').read_bytes());assert local['exit']==0 and local['source_unchanged']
rows=ET.parse(base/'d04-physical-flow-server-r2/results/server.trx').findall('.//t:UnitTestResult',ns);assert len(rows)==26 and all(r.attrib['outcome']=='Passed' for r in rows)
pin=json.loads((base/'d04-physical-flow-server-r2/source-pin.json').read_bytes());assert all(hashlib.sha256((repo/n).read_bytes()).hexdigest()==sha for n,sha in pin.items())
domainpin=json.loads((base/'d04-combat-measure-domain-r3/source-pin.json').read_bytes());assert all(hashlib.sha256((repo/n).read_bytes()).hexdigest()==sha for n,sha in domainpin.items() if n.startswith(('server/src/FantasyCard.Domain/','server/tests/FantasyCard.Domain.Tests/')))
folder=base/'d04-physical-flow-cloud-r1-file';public=folder/'public';result=json.loads((folder/'result.json').read_bytes())
assert result['exit']==0 and result['guard_ok'] and result['input_unchanged'] and result['local_binary_inputs_unchanged'] and result['schemas_still_present']==[]
assert hashlib.sha256((folder/'public-evidence.tar.gz').read_bytes()).hexdigest()==result['collected_raw_archive_sha256']
with tarfile.open(folder/'public-evidence.tar.gz') as bundle:
    for member in bundle.getmembers():assert bundle.extractfile(member).read()==(public/member.name).read_bytes()
rows=ET.parse(public/'cases.trx').findall('.//t:UnitTestResult',ns);assert len(rows)==6 and all(r.attrib['outcome']=='Passed' for r in rows)
proofs={r['kind']:r for line in (public/'currency-reports.original.jsonl').read_text(encoding='utf-8').splitlines() if (r:=json.loads(line))}
chain=proofs['actual-physical-equipment-chain'];r=chain['report'];mints=[e for e in r['Events'] if e['Kind']=='Mint'];assert len(mints)==1 and mints[0]['Source']=='equipment.craft' and mints[0]['ToOwnerId']==chain['originalCreator'] and chain['currentOwner']!=chain['originalCreator']
assert sum(e['DestroyedUnits'] for e in r['Events'])==sum(e['TransferredUnits'] for e in r['Events'])==1 and sum(e['EscrowEntries'] for e in r['Events'])==sum(e['EscrowReleases'] for e in r['Events'])==2
assert len(r['Supply'])==1 and r['Supply'][0]['Created']=='1' and r['Supply'][0]['Destroyed']=='1' and r['Supply'][0]['Closing']=='0' and r['Supply'][0]['Difference']=='0' and r['KnownSubsetBalanced'] and r['MissingCreationSources']==r['UnclassifiedMovements']==0 and chain['readOnlyFingerprintUnchanged']
holds=proofs['actual-committed-destruction-profile'];destroy=next(e for e in holds['report']['Events'] if e['EventName']=='item_destroyed');assert destroy['SourceHoldId']==holds['originalHold'] and destroy['Dimensions']['BuildType'] and destroy['Dimensions']['GrowthStage'] and holds['unrelatedItemRejected'] and holds['readOnlyFingerprintUnchanged']
gap=proofs['actual-physical-history-gaps'];b=gap['report']['Supply'][0];assert b['UnknownTerminalTimes']==b['DuplicateDestructionClaims']==b['Destroyed']=='1' and not gap['report']['KnownSubsetBalanced'] and gap['noCreationOwnerInference'] and gap['readOnlyFingerprintUnchanged']
archive=proofs['actual-wallet-recipe-archive-markers'];assert archive['before']==archive['after'] and archive['lateCreditDoesNotRewriteMarkers'] and archive['noArchiveAmountSnapshotClaimed'] and archive['readOnlyFingerprintUnchanged']
kinds=[e['AssetKind'] for e in archive['before']['Events']];assert all(kinds.count(k)==1 for k in ['Equipment','SeasonWallet','Recipe','CraftingWish','SavedLoadout'])
admission=proofs['actual-preparation-owner-observations'];assert admission['selfOwnershipStable'] and admission['cancelReleaseAndMatchStartExecuted'] and not admission['nativeCapacityClaimed']
api=proofs['actual-physical-equipment-admin-HTTP'];assert api['missingKeyStatus']==401 and api['insecureStatus']==403 and api['privateNoStore']
receipts=[json.loads(line) for line in (public/'process-logs/receipts.jsonl').read_text().splitlines()];starts=[r['evidence']['Id'] for r in receipts if r['caseId']=='process-start'];stops=[r['evidence']['ProcessId'] for r in receipts if r['caseId']=='process-stop'];assert len(starts)==1 and set(starts)==set(stops)
assert len(result['owned_schemas'])==6 and not result['schemas_still_present']
assert all(json.loads((public/'cleanup.original.json').read_bytes())[k] for k in ['owned_container_removed','private_env_removed'])
assert json.loads((public/'input-cache-cleanup.original.json').read_bytes())['tmpfs_unmounted'] and json.loads((folder/'upload-cleanup.original.json').read_bytes())['upload_tmpfs_unmounted']
assert all(json.loads(line)['guard_ok'] for line in (public/'resources.original.jsonl').read_text().splitlines())
cache=json.loads((public/'dependency-cache-reuse.original.json').read_bytes());assert cache['all_reused_hashes_verified'] and not cache['task_assemblies_reused'] and cache['reused_files']==122
context=json.loads((base/'current-journey-client-continuation-20261105.json').read_bytes());assert all(hashlib.sha256(Path(r['source']).read_bytes()).hexdigest()==r['sha256'] for r in context['D03_latest_banks'])
proof=dict(physical_equipment_subchain_verified=True,server_passed=26,actual_PG_HTTP_passed=6,domain_sources_unchanged=True,
    V055_nullable_ownership_no_backfill=True,original_creator_not_current_owner_or_source_kind=True,one_creation_one_mint=True,reforge_and_learning_no_new_units=True,
    transfer_and_escrow_not_mint_or_destroy=True,canonical_first_destruction_duplicate_claims_explicit=True,unknown_terminal_time_not_invented=True,
    known_subset_balance_verified_not_global_health=True,current_stocks_not_historical_opening=True,exact_hold_item_player_realm_receipt_build_verified=True,
    wallet_recipe_wish_referenced_loadout_archive_domain_only=True,late_credit_not_archive_amount_snapshot=True,
    actual_preparation_cancel_match_ownership_verified=True,read_only_fingerprints_unchanged=True,actual_program_processes=1,transient_resources_cleaned=True,
    thirdparty_cache_reused_files=122,task_assemblies_fresh=True,source_unchanged=True,capital_banks_unchanged=True,new_gameplay_campaign_cases=0,
    D04_complete=False,remaining_D04=['cohort-market-activity-red diagnostics','current-version integrated telemetry requirement audit'],progress='30/35',whole_goal_complete=False,production_modified=False,raw_archive_sha256=result['collected_raw_archive_sha256'])
path=base/'d04-physical-independent-audit-r1.derived.json';assert not path.exists();path.write_text(json.dumps(proof,indent=2)+'\n');print(json.dumps(proof))
