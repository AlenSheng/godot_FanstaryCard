from pathlib import Path
import json,hashlib,shutil,xml.etree.ElementTree as ET
repo=Path.cwd();b=Path(__file__).parent;e=repo/'docs/season-balance-20261102/evidence/C15-reward-entitlements-r1';assert not e.exists();e.mkdir()
def copy(source,name):
    target=e/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source,target)
for stage in ['local-journey-entitlements-build-r1','local-journey-entitlements-build-r2']:
    for name in ['source-pin.json','result.json','build.original.log']:copy(b/stage/name,stage+'/'+name)
ns={'t':'http://microsoft.com/schemas/VisualStudio/TeamTest/2010'};runs={};external={}
for stage in ['runtime-r106','runtime-r107']:
    root=b/stage;audit=json.loads((root/'collection-audit.json').read_text('utf-8'))
    assert hashlib.sha256((root/'public-evidence.tar.gz').read_bytes()).hexdigest()==audit['public_archive_sha256']
    for name,h in audit['files'].items():assert hashlib.sha256((root/'public'/name).read_bytes()).hexdigest()==h
    for p in (root/'public').rglob('*'):
        if p.is_file():copy(p,stage+'/public/'+p.relative_to(root/'public').as_posix())
    for p in root.iterdir():
        if p.is_file() and p.suffix in ['.json','.py','.log','.batch'] and 'checkpoint' not in p.name and p.name!='dictionary-transfer-estimate.json':copy(p,stage+'/'+p.name)
    external[stage]={p.name:dict(bytes=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest(),original_path=str(p)) for p in root.iterdir() if p.is_file() and p.suffix in ['.gz','.bin']}
    tree=ET.parse(root/'public/results/season-archive-runtime.trx').getroot();classes={}
    for result in tree.findall('t:Results/t:UnitTestResult',ns):
        name=result.get('testName').split('(')[0].rsplit('.',1)[0];values=classes.setdefault(name,dict(passed=0,failed=0));values['passed' if result.get('outcome')=='Passed' else 'failed']+=1
    resources=[json.loads(line) for line in (root/'public/resource-guard.original.jsonl').read_text('utf-8').splitlines()]
    assert all(r['available_ram']>=500*1024**2 and r['free_disk']>=3*1024**3 and r['disk_fraction']>=.05 for r in resources)
    runs[stage]=dict(counts=audit['counts'],classes=classes,public_archive_sha256=audit['public_archive_sha256'],source_binary_unchanged=audit['binary_payload_unchanged'],oom_killed=audit['oom_killed'],minimum_ram_bytes=min(r['available_ram'] for r in resources),minimum_disk_bytes=min(r['free_disk'] for r in resources),minimum_disk_fraction=min(r['disk_fraction'] for r in resources),owned_runtime_and_private_environment_removed=True)
helpers=['run-local-journey-entitlements-build-r1.py','run-local-journey-entitlements-build-r2.py','prepare-preparation-client-runtime-bundle-r1.py','preflight-journey-entitlements-r106.py','prepare-journey-entitlement-delta-r106.py','prepare-journey-entitlement-delta-r107.py','start-journey-entitlements-runtime-r106.py','start-journey-entitlements-runtime-r106-retry1.py','inspect-journey-entitlement-start-r106.py','inspect-r106-receiver-progress.py','stop-r106-disconnected-receiver.py','setup-r106-resumable-file-transfer.py','transfer-r106-stream-sftp.py','inspect-r106-file-prefix.py','stop-r106-disconnected-sftp-writer.py','verify-r106-complete-stream.py','start-r106-from-verified-file.py','observe-journey-entitlements-runtime-r106.py','collect-journey-entitlements-runtime-r106.py','setup-journey-entitlement-r107-file-transfer.py','transfer-r107-stream-sftp.py','inspect-r107-file-prefix.py','stop-r107-disconnected-sftp-writer.py','verify-r107-prefix-fast.py','verify-r107-complete-stream.py','verify-r107-complete-stream-r7.py','start-r107-from-verified-file.py','observe-journey-entitlements-runtime-r107.py','collect-journey-entitlements-runtime-r107.py','retire-verified-runtime-inputs-r3.py','retire-verified-success-public-duplicates-r107.py']
for name in helpers:copy(b/name,'drivers/'+name)
for name in ['runtime-r104-input-retirement-r3.original.log','runtime-r105-input-retirement-r3.original.log']:copy(b/name,'verified-input-retirement/'+name)
proof=dict(status='durable_pending_journey_entitlements_and_frozen_packs_verified_claims_still_open',overall_completed_items=20,C15_complete=False,formal_config='season-v1-config-14',migration='V050__season_journey_reward_entitlements.sql',actual_final_passed=21,actual_final_failed=0,actual_final_skipped=0,initial_passed=20,initial_failed=1,initial_missing_archive_fixture_retained=True,initial_declared_count_20_corrected_to_actual_21=True,assertions_or_game_acceptance_relaxed=False,pending_entitlements_only=True,claims_and_asset_minting_implemented=False,cosmetic_selection_verified=False,high_level_storage_tests_use_declared_seed_aggregates_not_completed_routes=True,runs=runs,full_binary_and_transport_originals_external=external,driver_versions_latest_with_per_attempt_settings_preserved_in_runtime_records=True,new_full_routes=0,new_encounters=0,B05_total=291,C16_total=121,capacity100_retest=False,production_activated=False,production_restarted=False,cloud_SDK_started=False)
(e/'result.json').write_text(json.dumps(proof,indent=2)+'\n',encoding='utf-8');m={p.relative_to(e).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in e.rglob('*') if p.is_file()};(e/'manifest.json').write_text(json.dumps(dict(files=m),indent=2)+'\n',encoding='utf-8');print(json.dumps(dict(files=len(m),final_passed=21,initial_failed=1,whole_C15_complete=False)))
