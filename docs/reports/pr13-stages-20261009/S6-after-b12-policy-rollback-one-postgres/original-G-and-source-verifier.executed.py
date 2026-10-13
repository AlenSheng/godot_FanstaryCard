import gzip,hashlib,json,subprocess,xml.etree.ElementTree as ET
from pathlib import Path
B=Path(__file__).parent;R=B.parents[1];S=R/'docs/reports/pr13-stages-20261009/S3-a07-current-numerical-postgres-nine';OUT=B/'B12-config-policy-rollback-pg9-G-audit-r1';assert not OUT.exists();OUT.mkdir()
def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(1024**2),b''):h.update(b)
 return h.hexdigest()
rec=json.loads((S/'complete-original-G-receipt.json').read_bytes());M=B/'current-PG-numerical-R10-complete-originals-on-G/delivery-manifest.json';manifest=json.loads(M.read_bytes());assert sha(M)==rec['manifest_sha256'];G=Path(rec['local_directory']);archive=Path(rec['local_archive']);assert len(manifest['files'])==2199 and archive.stat().st_size==rec['archive_bytes'] and sha(archive)==rec['archive_sha256']
with gzip.open(archive,'rb') as f:
 while f.read(1024**2):pass
for row in manifest['files']:
 p=G/row['path'];assert p.stat().st_size==row['bytes'] and sha(p)==row['sha256']
head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=R,text=True).strip();source_rows=[r for r in manifest['files'] if r['path'].startswith('frozen-source/')]
for row in source_rows:
 rel=row['path'][len('frozen-source/'):];raw=subprocess.check_output(['git','show',head+':'+rel],cwd=R);assert len(raw)==row['bytes'] and hashlib.sha256(raw).hexdigest()==row['sha256']
assert len(source_rows)==328
tree=ET.parse(S/'native-nine.original.trx');c={k:int(v) for k,v in tree.find('.//{*}Counters').attrib.items()};assert c['total']==c['executed']==c['passed']==9 and c['failed']==c['notExecuted']==0
methods={x.attrib['id']:x.find('{*}TestMethod').attrib['name'] for x in tree.findall('.//{*}UnitTest')};name='New_policy_source_changes_new_rooms_without_changing_current_persisted_room';rows=[x for x in tree.findall('.//{*}UnitTestResult') if methods[x.attrib['testId']]==name];assert len(rows)==1 and rows[0].attrib['outcome']=='Passed'
receipt=S/'receipts/PR13-B02.4-T01.json';a=json.loads(receipt.read_bytes())['actual'];assert len({a['oldRoom'],a['newRoom'],a['rollbackRoom']})==3 and a['oldSourceHash']==a['rollbackSourceHash']!=a['candidateSourceHash'] and a['oldBeforeHash']==a['oldAfterHash'] and a['databaseBeforeHash']==a['databaseAfterHash'] and all(a[k] is True for k in ['candidateFrozen','newRoomCandidateEnabled','rollbackNewRoomDefaults'])
result=json.loads((S/'native-result.original.json').read_bytes());assert result['ok'] and result['owned_containers_removed'] and result['remaining_owned_fixture_schemas']==0 and result['frozen_source_and_package_bytes_unchanged'] and not result['oom_killed']
report={'ok':True,'native_clean':True,'owned_container_removed':True,'source_inputs_match_git':True,'implementation_source_sha':head,'actual_native_frozen_source_sha':result['frozen_release_sha'],'exact_current_source_members':328,'original_native_run_methods':9,'actual_mapped_method':name,'selected_method_unskipped_passed':True,'original_TRX_sha256':sha(S/'native-nine.original.trx'),'original_database_receipt_sha256':sha(receipt),'actual':a,'all_G_originals_rehashed':2199,'G_archive_SHA_and_CRC_reverified':True,'mapping':'PR13-B02.4-T01 actual persisted policy rollback assertions also satisfy PR13-B12.3-T02 POSTGRES expected new room old, existing room frozen','no_native_reexecution_or_new_samples_claimed':True,'scope':'Exact isolated NumericalRules source rollback and current persisted room snapshots; no production deployment, arbitrary config bundles, LIVE or EXPERIMENT claim','MAIN_accepted':False}
(OUT/'independent-G-audit.original.json').write_bytes((json.dumps(report,indent=2)+'\n').encode());print(json.dumps({'ok':True,'G_members':2199,'source_members':328,'method':name,'mapping':'B12.3-T02 POSTGRES'}))
