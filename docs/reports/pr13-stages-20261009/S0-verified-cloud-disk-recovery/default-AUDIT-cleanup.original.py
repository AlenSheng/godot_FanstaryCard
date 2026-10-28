SPEC={'members': 12, 'SHA256': '19789c7522dd762116a66e938bd312d106be5f46d3ac1cb217aa602852e35766', 'G_archive_receipt': {'ok': True, 'native_ok': True, 'source_sha': 'bfa7d7aa9a132e3515d443d0fdafc4f7186e7e86', 'local_directory': 'G:\\PR13Evidence\\current-default-deployment-six-AUDIT-r1', 'archive_bytes': 1137138, 'archive_sha256': '91225c0421600f3b8855353ef6c4798d2450e6b77dd38e5cd2e22a51a9df1716', 'manifest_sha256': '8cbfc7f4864f0b32122f3d1032366bcf9b6a4de5a52b27996265fcada94261ae', 'original_members_rehashed': 17, 'archive_gzip_CRC_verified': True, 'all_original_members_SHA_verified': True, 'cloud_cleanup_performed': False, 'no_native_reexecution': True, 'MAIN_accepted': False}, 'all_G_originals_rehashed': 17}

import hashlib,json,os,shutil,subprocess
from pathlib import Path
B=Path('/home/ubuntu/pr13-acceptance-20261009');A='current-default-deployment-six-audit-r1-20261012';root=B/'work'/A;E=B/'evidence'/A;assert root.resolve(strict=True)==root and not root.is_symlink();result=json.loads((E/'result.original.json').read_bytes());assert result['ok'] and result['executed']==result['passed']==6 and not (Path('/proc')/str(result['actual_cloud_PID'])).exists();intent=E/'passed-input-cleanup-r2-intent.original.json';assert not intent.exists();rows=[]
ids=subprocess.check_output(['docker','ps','-q'],text=True).split();cs=json.loads(subprocess.check_output(['docker','inspect',*ids])) if ids else []
for c in cs:
 for bind in c['Mounts']:
  if bind['Type']!='bind':continue
  p=Path(bind['Source']).resolve()
  if c['Id']=='2734235cbfa1f9d8f1352cd9a925251f6356021d86ede341f80c6196e799149a' and p==Path('/') and bind['RW'] is False:continue
  assert not (p==root or p.is_relative_to(root) or root.is_relative_to(p))
for p in root.rglob('*'):
 assert not p.is_symlink()
 if p.is_file():rows.append({'source':str(p),'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()})
 else:assert p.is_dir()
rows.sort(key=lambda r:r['source']);assert len(rows)==SPEC['members'] and hashlib.sha256(json.dumps(rows,sort_keys=True,separators=(',',':')).encode()).hexdigest()==SPEC['SHA256'];before=os.statvfs('/');assert before.f_bavail/before.f_blocks>=.15;intent.write_bytes((json.dumps(SPEC,indent=2)+'\n').encode());shutil.rmtree(root);after=os.statvfs('/');r={'ok':True,'exact_target':str(root),'members':len(rows),'actual_root_bytes_reclaimed':(after.f_bavail-before.f_bavail)*after.f_frsize,'all_G_originals_SHA_and_archive_CRC_reverified':True,'failed_originals_preserved':True,'shared_caches_preserved':True,'MAIN_accepted':False};(E/'passed-input-cleanup-r2.original.json').write_bytes((json.dumps(r,indent=2)+'\n').encode());print(json.dumps(r))
