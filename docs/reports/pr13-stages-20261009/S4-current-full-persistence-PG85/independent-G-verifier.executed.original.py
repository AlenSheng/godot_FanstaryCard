import gzip
import hashlib
import json
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path
B=Path(__file__).parent;R=B.parents[1];OUT=B/'Persistence-full-PG-r1-independent-G-check'
assert not OUT.exists()
def sha(path):
    h=hashlib.sha256()
    with path.open('rb') as stream:
        for data in iter(lambda:stream.read(1024**2),b''):h.update(data)
    return h.hexdigest()
def read(path):return json.loads(path.read_bytes())
receipt=read(B/'Persistence-full-PG-r1-complete-original-G-backup/complete-original-G-receipt.original.json')
G=Path(receipt['local_directory']);archive=Path(receipt['local_archive'])
assert receipt['ok'] and receipt['all_original_members_SHA_verified'] and receipt['archive_gzip_CRC_verified']
assert archive.stat().st_size==receipt['archive_bytes'] and sha(archive)==receipt['archive_sha256']
with gzip.open(archive,'rb') as stream:
    while stream.read(1024**2):pass
assert sha(G/'complete-original-manifest.json')==receipt['manifest_sha256']
manifest=read(G/'complete-original-manifest.json');assert len(manifest['files'])==receipt['original_members']
for row in manifest['files']:
    p=G/row['path'];assert p.stat().st_size==row['bytes'] and sha(p)==row['sha256']
plan=read(G/'work/plan.original.json')
head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=R,text=True).strip()
assert len(plan['source_files'])==328 and len(plan['runtime_files'])==146
for row in plan['source_files']:
    raw=subprocess.check_output(['git','-c','core.longpaths=true','show',head+':'+row['path']],cwd=R)
    p=G/'input-source'/row['path'];assert len(raw)==p.stat().st_size==row['bytes'] and hashlib.sha256(raw).hexdigest()==sha(p)==row['sha256']
for row in plan['runtime_files']:
    p=G/'input-runtime'/row['path'];assert p.stat().st_size==row['bytes'] and sha(p)==row['sha256']
assert sha(G/'input-runtime/FantasyCard.Server.Tests.dll')==plan['test_assembly_sha256']
assert sha(G/'input-runtime/FantasyCard.Domain.dll')=='844065af3158b40787699752915ed95befbd3c660c2b10dce501f9f4fc29e352'
config=read(G/'input-runtime/xunit.runner.json');assert config['maxParallelThreads']==1
result=read(G/'evidence/result.original.json')
assert result['ok'] and result['exit_code']==result['actual_native_job_exit_code']==0 and not result['oom_killed']
assert result['owned_containers_removed'] and result['private_environment_removed_after_owned_containers_ended']
assert result['isolated_PG_schemas_before']==result['isolated_PG_schemas_after']==0
assert result['original_source_runtime_and_work_inputs_unchanged']
terminal=read(G/'evidence/terminal-state.original.json');assert terminal['MainPID']=='0' and terminal['ActiveState']=='inactive' and terminal['ExecMainStatus']=='0'
output=G/'evidence/persistent-output';discovery=read(output/'actual-discovered-required-tests.original.json');report=read(output/'full-persistence-result.original.json')
names=discovery['actual_discovered_names'];assert len(names)==len(set(names))==discovery['expected_native_rows']==85
assert discovery['discovered_before_execution'] and discovery['post_execution_target_changes_allowed'] is False
assert discovery['selector']==plan['selector']=='Category=PostgresIntegration&FullyQualifiedName~FantasyCard.Server.Tests.Persistence'
listed=[line.strip() for line in (output/'actual-discovery.stdout.original.log').read_text().splitlines() if line.strip().startswith('FantasyCard.Server.Tests.Persistence.')]
assert listed==names
tree=ET.parse(output/'results/all-persistence.original.trx')
counts={k:int(v) for k,v in tree.find('.//{*}Counters').attrib.items()}
rows=tree.findall('.//{*}UnitTestResult');assert len(rows)==85 and set(r.attrib['testName'] for r in rows)==set(names)
assert counts['total']==counts['executed']==counts['passed']==85 and counts['failed']==counts['notExecuted']==0
assert all(r.attrib['outcome']=='Passed' for r in rows)
assert report['ok'] and report['all_selected_rows_unskipped_passed'] and report['native_counters']==counts
assert report['missing_actual_names']==report['unexpected_actual_names']==[]
assert all(p['exit_code']==0 for p in report['phases']) and report['phases'][0]['name']=='actual-discovery'
proof={'ok':True,'native_clean':True,'owned_container_removed':True,'source_inputs_match_git':True,
    'implementation_source_sha':head,'compiled_source_sha':plan['compiled_source_sha'],
    'scope':report['scope'],'fixed_selector':plan['selector'],'actual_pre_execution_discovered_rows':85,
    'actual_unskipped_native_PG_passed_rows':85,'actual_failed_rows':0,'actual_skipped_rows':0,
    'original_source_members_current_Git_equivalent':328,'all_original_runtime_members_verified':146,
    'production_domain_assembly_unchanged':True,'source_or_runtime_edits':0,
    'all_complete_G_original_members_rehashed':len(manifest['files']),'G_archive_SHA_and_CRC_rechecked':True,
    'canonical_profile_cells_closed':0,'MAIN_accepted':False}
OUT.mkdir();(OUT/'independent-G-check.original.json').write_bytes((json.dumps(proof,indent=2)+'\n').encode())
print(json.dumps(proof))
