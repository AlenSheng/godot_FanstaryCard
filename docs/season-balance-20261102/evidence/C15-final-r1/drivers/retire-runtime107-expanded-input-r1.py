from pathlib import Path
import base64,hashlib,json,shlex,subprocess,tarfile

base=Path(__file__).parent;stage=base/'runtime-r107';out=stage/'input-retirement-verified-local-r1.original.json';assert not out.exists()
manifest=json.loads((stage/'manifest.json').read_text('utf-8'));assert hashlib.sha256((stage/'payload.tar.gz').read_bytes()).hexdigest()==manifest['payload_sha256']
with tarfile.open(stage/'payload.tar.gz') as archive:
 for name,digest in manifest['files'].items():assert hashlib.sha256(archive.extractfile(name).read()).hexdigest()==digest
audit=json.loads((stage/'collection-audit.json').read_text('utf-8'));assert audit['exit_code']==0 and audit['counts']['failed']=='0'
assert hashlib.sha256((stage/'public-evidence.tar.gz').read_bytes()).hexdigest()==audit['public_archive_sha256']
assert all(hashlib.sha256((stage/'public'/n).read_bytes()).hexdigest()==h for n,h in audit['files'].items())
meta={'manifest_sha256':hashlib.sha256((stage/'manifest.json').read_bytes()).hexdigest(),'local_payload_sha256':manifest['payload_sha256'],'local_public_sha256':audit['public_archive_sha256']}
code='''from pathlib import Path
import hashlib,json,shutil,subprocess
root=Path('/home/ubuntu/season-balance-20261102-a03-runtime-r107');work=root/'input';proof=root/'input-retirement.json';keep=Path('/home/ubuntu/season-balance-20261102-a03-runtime-r108')
expected=EXPECTED
assert root.resolve()==root and root.parent==Path('/home/ubuntu') and work.resolve().parent==root and work.name=='input' and not work.is_symlink() and not proof.exists()
assert hashlib.sha256((root/'manifest.json').read_bytes()).hexdigest()==expected['manifest_sha256']
m=json.loads((root/'manifest.json').read_text());live=json.loads((keep/'manifest.json').read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
assert {p.relative_to(work).as_posix() for p in work.rglob('*') if p.is_file()}==set(m['files'])
assert all(not (work/n).is_symlink() and sha(work/n)==h for n,h in m['files'].items())
assert all(sha(keep/'input'/n)==h for n,h in live['files'].items())
assert not subprocess.check_output(['docker','ps','-a','--filter','label=com.fantasycard.task=season-balance-20261102-a03-runtime-r107','--format','{{.ID}}']).strip()
for cid in subprocess.check_output(['docker','ps','-q'],text=True).split():
 row=json.loads(subprocess.check_output(['docker','inspect',cid]))[0]
 for mount in row['Mounts']:
  p=Path(mount['Source']).resolve()
  if row['Name']=='/fantasycard-cloud-node-exporter-1' and p==Path('/') and mount['Destination']=='/host' and not mount['RW']:continue
  assert not p.is_relative_to(work) and not work.is_relative_to(p)
before=shutil.disk_usage(root).free;logical=sum((work/n).stat().st_size for n in m['files']);unshared=sum((work/n).stat().st_size for n in m['files'] if (work/n).stat().st_nlink==1)
shutil.rmtree(work)
assert all(sha(keep/'input'/n)==h for n,h in live['files'].items())
data={'only_verified_expanded_input_removed':True,'logical_bytes':logical,'unshared_logical_bytes':unshared,'actual_free_increase':shutil.disk_usage(root).free-before,'complete_local_payload_sha256':expected['local_payload_sha256'],'complete_local_public_sha256':expected['local_public_sha256'],'original_cloud_results_manifests_and_handles_retained':True,'runtime108_next_base_unchanged':True,'local_original_directory':'G:/PR13Evidence/season-balance-20261102-r1/runtime-r107'}
proof.write_text(json.dumps(data,indent=2)+chr(10));print(json.dumps(data))
'''.replace('EXPECTED',repr(meta))
command='sudo -n python3 -c '+shlex.quote('import base64;exec(base64.b64decode('+repr(base64.b64encode(code.encode()).decode())+'))')
r=subprocess.run(['ssh','-i',r'C:\Users\SHENGJIAHAO\.ssh\gpt-deploy-release.pem','-o','BatchMode=yes','-o','StrictHostKeyChecking=yes','-o','ConnectTimeout=12','ubuntu@43.172.70.182',command],capture_output=True,text=True,timeout=50)
out.write_text(json.dumps({'returncode':r.returncode,'stdout':r.stdout,'stderr':r.stderr},indent=2)+'\n',encoding='utf-8');print(r.stdout+r.stderr);assert r.returncode==0
