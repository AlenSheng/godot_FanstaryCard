from pathlib import Path
import json,hashlib,shutil,xml.etree.ElementTree as ET
repo=Path.cwd();b=Path(__file__).parent;e=repo/'docs/season-balance-20261102/evidence/C15-claim-backend-r1';assert not e.exists();e.mkdir()
def copy(source,name):
    target=e/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source,target)
for stage in ['journey-claims-local-r1','journey-claims-local-r2','journey-claims-local-r3']:
    for name in ['source-pin.json','result.json','interrupted.original.json','admission-rejected.original.json','build-and-tests.original.log','results/encoding.trx']:
        if (b/stage/name).is_file():copy(b/stage/name,stage+'/'+name)
root=b/'runtime-r108';audit=json.loads((root/'collection-audit.json').read_text('utf-8'));assert audit['exit_code']==0 and audit['counts']['passed']=='46' and audit['counts']['failed']=='0' and audit['counts']['notExecuted']=='0'
assert hashlib.sha256((root/'public-evidence.tar.gz').read_bytes()).hexdigest()==audit['public_archive_sha256']
for name,h in audit['files'].items():assert hashlib.sha256((root/'public'/name).read_bytes()).hexdigest()==h
for p in (root/'public').rglob('*'):
    if p.is_file():copy(p,'runtime-r108/public/'+p.relative_to(root/'public').as_posix())
for p in root.iterdir():
    if p.is_file() and p.suffix in ['.json','.py','.log','.batch'] and 'checkpoint' not in p.name:copy(p,'runtime-r108/'+p.name)
drivers=['run-journey-claims-local-r1.py','run-journey-claims-local-r2.py','run-journey-claims-local-r3.py','prepare-journey-claims-runtime-bundle-r1.py','runtime_dictionary_delta.py','prepare-runtime-dictionary-delta.py','setup-journey-claims-r108-file-transfer.py','transfer-r108-stream-sftp.py','verify-r108-complete-stream.py','start-r108-from-verified-file.py','observe-journey-claims-runtime-r108.py','collect-journey-claims-runtime-r108.py','package-journey-claim-backend-evidence-r1.py']
for name in drivers:copy(b/name,'drivers/'+name)
copy(b/'dictionary-delta-codec-validation-r1.json','transport/dictionary-delta-codec-validation-r1.json');copy(b/'runtime-r106-input-retirement-r3.original.log','transport/runtime-r106-input-retirement-r3.original.log')
for p in b.glob('journey-claims-resource-recheck-r*.json'):copy(p,'admission/'+p.name)
ns={'t':'http://microsoft.com/schemas/VisualStudio/TeamTest/2010'};tree=ET.parse(root/'public/results/season-archive-runtime.trx').getroot();classes={}
for result in tree.findall('t:Results/t:UnitTestResult',ns):
    name=result.get('testName').split('(')[0].rsplit('.',1)[0];classes[name]=classes.get(name,0)+1;assert result.get('outcome')=='Passed'
resources=[json.loads(line) for line in (root/'public/resource-guard.original.jsonl').read_text('utf-8').splitlines()];assert all(r['available_ram']>=500*1024**2 and r['free_disk']>=3*1024**3 and r['disk_fraction']>=.05 for r in resources)
external={p.name:dict(bytes=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest(),original_path=str(p)) for p in root.iterdir() if p.is_file() and p.suffix in ['.gz','.bin']}
proof=dict(status='backend_claims_permanent_cosmetics_selection_and_real_HTTP_verified_native_UI_still_open',overall_completed_items=20,C15_complete=False,migration='V051__journey_claims_and_permanent_cosmetics.sql',local_encoding_passed=11,actual_cloud_passed=46,actual_cloud_failed=0,actual_cloud_skipped=0,classes=classes,actual_authenticated_HTTP_network=True,actual_native_HTTP_network=False,native_UI_verified=False,actual_HTTP_original_files=8,old97_HTTP_schemas_and59_routes_preserved=True,new_HTTP_messages=8,new_routes=4,realtime_source_unchanged_except_preexisting_worktree_CRLF=True,high_level_claim_cases_use_declared_seed_aggregates_not_real_level30_routes=True,full_payload_and_base_input_byte_hashes_verified=True,lossless_staging_validated_on_all222_members_and194_original_members=True,application_bytes_changed_by_transport=False,minimum_cloud_ram_bytes=min(r['available_ram'] for r in resources),minimum_cloud_disk_bytes=min(r['free_disk'] for r in resources),minimum_cloud_disk_fraction=min(r['disk_fraction'] for r in resources),owned_runtime_and_private_env_removed=True,cloud_SDK_started=False,full_binary_originals_external=external,remaining='Godot consumer/controller, actual cosmetics application, all11 languages x3 widths real UI; distinct journey economy model; other A/D/E/F gates.',new_full_routes=0,new_encounters=0,B05_total=291,C16_total=121,capacity100_retest=False,production_activated=False,production_restarted=False)
(e/'result.json').write_text(json.dumps(proof,indent=2)+'\n',encoding='utf-8');m={p.relative_to(e).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in e.rglob('*') if p.is_file()};(e/'manifest.json').write_text(json.dumps(dict(files=m),indent=2)+'\n',encoding='utf-8');print(json.dumps(dict(files=len(m),actual_passed=46,classes=classes,whole_C15_complete=False)))
