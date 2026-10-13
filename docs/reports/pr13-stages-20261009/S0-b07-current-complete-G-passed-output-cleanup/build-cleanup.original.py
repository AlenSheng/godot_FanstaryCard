SPEC={'target': '/home/ubuntu/pr13-acceptance-20261009/work/B07-current-table-sequences-r1-20261013', 'members': 34, 'rows_sha256': 'a3525a1bcf64d80c4f12325822024db57528480970dbc42fe21fee6de9e3531b', 'G_all_originals_rehashed': 142, 'G_archive_SHA_and_CRC_reverified': True, 'receipt': {'ok': True, 'native_ok': True, 'attempt': 'B07-current-table-sequences-r1-20261013', 'local_directory': 'G:\\PR13Evidence\\B07-current-table-sequences-r1-20261013', 'archive_bytes': 380838874, 'archive_sha256': 'c123b9812491afc75bbb46bb61b9a38ee85c7092013302cf14989448be361790', 'manifest_sha256': 'a34095b6f4642ae906cc5724649476592035c55a6408df9a1ebc1a147bb917cc', 'new_original_members': 140, 'shared_existing_G_members_rehashed': 2, 'all_original_members_SHA_verified': True, 'archive_gzip_CRC_verified': True, 'original_failed_execution_not_reclassified_as_pass': True, 'MAIN_accepted': False}}

import hashlib,json,os,shutil,subprocess
from pathlib import Path
B=Path('/home/ubuntu/pr13-acceptance-20261009');A='B07-current-table-sequences-r1-20261013';E=B/'evidence'/A;root=B/'work'/A;assert root.resolve(strict=True)==root and str(root)==SPEC['target'];state=dict(l.split('=',1) for l in subprocess.check_output(['systemctl','show','pr13-cap-'+A,'--property=MainPID,ActiveState,ExecMainStatus'],text=True).splitlines());r=json.loads((E/'result.original.json').read_bytes());assert state['MainPID']=='0' and state['ActiveState']=='inactive' and state['ExecMainStatus']=='0' and r['ok'] and r['owned_container_removed'];assert json.loads((E/'independent-terminal-source-validation.original.json').read_bytes())['ok'];ids=subprocess.check_output(['docker','ps','-q'],text=True).split();cs=json.loads(subprocess.check_output(['docker','inspect',*ids])) if ids else []
for c in cs:
 for bind in c['Mounts']:
  if bind['Type']!='bind':continue
  p=Path(bind['Source']).resolve()
  if c['Id']=='2734235cbfa1f9d8f1352cd9a925251f6356021d86ede341f80c6196e799149a' and p==Path('/') and bind['RW'] is False:continue
  assert not (p==root or p.is_relative_to(root) or root.is_relative_to(p))
actual=[]
for p in root.rglob('*'):
 assert not p.is_symlink()
 if p.is_file():actual.append({'source':str(p),'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()})
 else:assert p.is_dir()
actual.sort(key=lambda r:r['source']);assert len(actual)==SPEC['members'] and hashlib.sha256(json.dumps(actual,sort_keys=True,separators=(',',':')).encode()).hexdigest()==SPEC['rows_sha256'];intent=E/'passed-owned-build-cleanup-intent.original.json';assert not intent.exists();intent.write_bytes((json.dumps(SPEC,indent=2)+'\n').encode());before=os.statvfs('/');shutil.rmtree(root);after=os.statvfs('/');v={'ok':True,'target':str(root),'members':len(actual),'actual_root_bytes_reclaimed':(after.f_bavail-before.f_bavail)*after.f_frsize,'all_original_G_SHA_and_archive_CRC_reverified':True,'native_raw_outputs_kept':True,'failed_R1_and_shared_source_runtime_packages_preserved':True,'MAIN_accepted':False};(E/'passed-owned-build-cleanup.original.json').write_bytes((json.dumps(v,indent=2)+'\n').encode());print(json.dumps(v))
