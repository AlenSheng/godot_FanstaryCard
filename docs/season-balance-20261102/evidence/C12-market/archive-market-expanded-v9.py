from pathlib import Path
import hashlib,json,subprocess,shutil,tarfile,os,sys
os.nice(10)
base=Path('/home/ubuntu');root=base/'season-balance-20261102-a03-storage-r76';work=root/'input';archive=root/'ended-expanded-inputs-v9.tar.gz';proof_path=root/'ended-expanded-inputs-v9.json'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def unused():
 assert root.resolve()==root and root.parent==base and work.resolve()==work and work.parent==root and work.name=='input' and work.is_dir() and not work.is_symlink()
 for cid in subprocess.check_output(['docker','ps','-q'],text=True).split():
  row=json.loads(subprocess.check_output(['docker','inspect',cid]))[0]
  for mount in row['Mounts']:
   source=Path(mount['Source']).resolve()
   if row['Name']=='/fantasycard-cloud-node-exporter-1' and source==Path('/') and mount['Destination']=='/host' and mount['RW'] is False:continue
   assert not source.is_relative_to(work) and not work.is_relative_to(source),'A running container uses the exact expanded input.'
def streaming_verify(expected):
 seen=set()
 with tarfile.open(archive,mode='r|gz') as z:
  for member in z:
   assert member.isfile() or member.isdir()
   if member.isfile():
    assert member.name in expected and member.name not in seen
    assert hashlib.sha256(z.extractfile(member).read()).hexdigest()==expected[member.name]
    seen.add(member.name)
 assert seen==set(expected)
mode=sys.argv[1]
if mode=='prepare':
 unused();assert not archive.exists() and not proof_path.exists()
 manifest=json.loads((root/'input-manifest.json').read_text());assert sha(root/'source.tar.gz')==manifest['archive_sha256']
 for n,h in manifest['files'].items():assert sha(work/n)==h
 assert (root/'public-evidence.tar.gz').is_file() and not (root/'sdk.env').exists()
 assert json.loads((root/'guard-terminal.original.json').read_text())['state']=='exited'
 files={};total=0
 for p in work.rglob('*'):
  assert not p.is_symlink()
  if p.is_file():files[p.relative_to(base).as_posix()]=sha(p);total+=p.stat().st_size
 d=shutil.disk_usage(base);assert d.free-total>=3*1024**3 and (d.free-total)/d.total>=.05
 with tarfile.open(archive,'w:gz',compresslevel=1) as z:z.add(work,arcname=root.name+'/input',recursive=True)
 streaming_verify(files);archive.chmod(0o600);os.chown(archive,1000,1000)
 proof={'archive_sha256':sha(archive),'archive_bytes':archive.stat().st_size,'expanded_bytes':total,'files':files,'source_sha256':sha(root/'source.tar.gz'),'public_sha256':sha(root/'public-evidence.tar.gz'),'expanded_retired':False,'snapshot_offloaded':False,'retained_local_snapshot':'G:/PR13Evidence/season-balance-20261102-r1/cloud-build-archives/ended-expanded-inputs-v9.tar.gz'}
 proof_path.write_text(json.dumps(proof,indent=2)+'\n');print(json.dumps({k:v for k,v in proof.items() if k!='files'}))
elif mode=='retire':
 unused();proof=json.loads(proof_path.read_text());assert not proof['expanded_retired'] and sys.argv[2]==proof['archive_sha256']==sha(archive)
 streaming_verify(proof['files']);assert sha(root/'source.tar.gz')==proof['source_sha256'] and sha(root/'public-evidence.tar.gz')==proof['public_sha256']
 for n,h in proof['files'].items():assert sha(base/n)==h
 before=shutil.disk_usage(base).free;assert work.resolve()==root/'input' and work.resolve().parent==root
 shutil.rmtree(work)
 proof['expanded_retired']=True;proof['freed_bytes']=shutil.disk_usage(base).free-before;proof_path.write_text(json.dumps(proof,indent=2)+'\n')
 (root/'expanded-input-location.json').write_text(json.dumps({'snapshot_sha256':proof['archive_sha256'],'local':proof['retained_local_snapshot'],'complete_snapshot_cloud_retained':str(archive),'source_and_public_archives_retained':True},indent=2)+'\n');print(json.dumps({'expanded_retired':True,'freed_bytes':proof['freed_bytes'],'complete_snapshot_retained':True}))
elif mode=='offload':
 proof=json.loads(proof_path.read_text());assert proof['expanded_retired'] and not proof['snapshot_offloaded'] and sys.argv[2]==proof['archive_sha256']==sha(archive)
 assert not work.exists() and sha(root/'source.tar.gz')==proof['source_sha256'] and sha(root/'public-evidence.tar.gz')==proof['public_sha256']
 location=root/'expanded-input-location.json';entry=json.loads(location.read_text());assert entry['snapshot_sha256']==proof['archive_sha256']
 entry['original_cloud_snapshot_path']=str(archive);entry['complete_snapshot_cloud_retained']=False;entry['snapshot_offloaded']=True;entry['complete_snapshot']=proof['retained_local_snapshot'];location.write_text(json.dumps(entry,indent=2)+'\n')
 archive.unlink();proof['snapshot_offloaded']=True;proof_path.write_text(json.dumps(proof,indent=2)+'\n')
 print(json.dumps({'offloaded':True,'sha256':proof['archive_sha256'],'free_disk':shutil.disk_usage(base).free,'source_and_public_archives_retained':True}))
else:raise ValueError(mode)
