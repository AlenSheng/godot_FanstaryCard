from pathlib import Path
import hashlib,json,os,shutil,subprocess,sys,tarfile
os.nice(10)
home=Path('/home/ubuntu')
control=home/'season-balance-20261102-a03-storage-r57'
archive=control/'ended-expanded-inputs-v1.tar.gz'
proof_path=control/'ended-expanded-inputs-v1.json'
roots=[home/f'season-balance-20261102-a03-storage-r{n}' for n in range(13,21)]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def require_unused(work):
 assert work.resolve()==work and work.parent in roots and work.name=='input' and work.is_dir() and not work.is_symlink()
 ids=subprocess.check_output(['docker','ps','-q'],text=True).split()
 for cid in ids:
  info=json.loads(subprocess.check_output(['docker','inspect',cid]))[0]
  for mount in info['Mounts']:
   source=Path(mount['Source']).resolve()
   assert not work.is_relative_to(source) and not source.is_relative_to(work), 'A running container uses this directory.'
mode=sys.argv[1]
if mode=='prepare':
 assert not archive.exists() and not proof_path.exists()
 rows=[];total=0;files={}
 for root in roots:
  assert root.resolve()==root and root.parent==home
  work=root/'input';require_unused(work)
  manifest=json.loads((root/'input-manifest.json').read_text())
  assert sha(root/'source.tar.gz')==manifest['archive_sha256']
  assert (root/'public-evidence.tar.gz').is_file()
  for name,h in manifest['files'].items():assert sha(work/name)==h
  for p in work.rglob('*'):
   assert not p.is_symlink()
   if p.is_file():
    name=p.relative_to(home).as_posix();files[name]=sha(p);total+=p.stat().st_size
  rows.append({'root':root.name,'source_archive_sha256':sha(root/'source.tar.gz'),'public_archive_sha256':sha(root/'public-evidence.tar.gz')})
 disk=shutil.disk_usage(home)
 assert disk.free-total>=3*1024**3 and disk.free/disk.total>=.05
 with tarfile.open(archive,'w:gz',compresslevel=1) as z:
  for root in roots:z.add(root/'input',arcname=root.name+'/input',recursive=True)
 archive.chmod(0o600);os.chown(archive,1000,1000)
 with tarfile.open(archive) as z:
  assert {m.name for m in z.getmembers() if m.isfile()}==set(files)
  assert all(m.isfile() or m.isdir() for m in z.getmembers())
  for name,h in files.items():assert hashlib.sha256(z.extractfile(name).read()).hexdigest()==h
 proof={'archive_sha256':sha(archive),'archive_bytes':archive.stat().st_size,'expanded_bytes':total,'files':files,'stages':rows,
        'original_source_archives_and_public_results_retained_on_cloud':True,'expanded_copies_retired':False}
 proof_path.write_text(json.dumps(proof,indent=2)+'\n')
 print(json.dumps({k:v for k,v in proof.items() if k!='files'}))
elif mode=='retire':
 proof=json.loads(proof_path.read_text());expected=sys.argv[2]
 assert expected==proof['archive_sha256']==sha(archive) and not proof['expanded_copies_retired']
 for root,row in zip(roots,proof['stages']):
  work=root/'input';require_unused(work)
  assert root.name==row['root'] and sha(root/'source.tar.gz')==row['source_archive_sha256']
  assert sha(root/'public-evidence.tar.gz')==row['public_archive_sha256']
  for name,h in proof['files'].items():
   p=home/name
   if p.is_relative_to(work):assert sha(p)==h
 before=shutil.disk_usage(home).free
 for root in roots:
  work=root/'input';require_unused(work)
  assert work.resolve().parent==root and work.resolve().name=='input'
  shutil.rmtree(work)
 proof['expanded_copies_retired']=True
 proof['retained_local_snapshot']='G:/PR13Evidence/season-balance-20261102-r1/cloud-build-archives/ended-expanded-inputs-v1.tar.gz'
 proof['freed_expanded_bytes']=shutil.disk_usage(home).free-before
 proof_path.write_text(json.dumps(proof,indent=2)+'\n')
 print(json.dumps({'retained_archive_sha256':expected,'files_byte_verified':len(proof['files']),'freed_bytes':proof['freed_expanded_bytes'],
                   'source_archives_public_results_and_complete_snapshot_retained':True}))
else:raise ValueError(mode)

