from pathlib import Path
import sys,tarfile,hashlib,json,subprocess,base64,shlex
b=Path(__file__).parent;stage=sys.argv[1];assert stage.startswith('runtime-r') and stage[9:].isdigit();o=b/stage
m=json.loads((o/'manifest.json').read_text(encoding='utf-8'));payload=o/'payload.tar.gz';assert hashlib.sha256(payload.read_bytes()).hexdigest()==m['payload_sha256']
with tarfile.open(payload,'r:gz') as tf:
 seen=set()
 for e in tf:
  assert e.isfile() and e.name in m['files'] and e.name not in seen;assert hashlib.sha256(tf.extractfile(e).read()).hexdigest()==m['files'][e.name];seen.add(e.name)
assert seen==set(m['files']);assert json.loads((o/'collection-audit.json').read_text())['exit_code']==0
code="""from pathlib import Path
import subprocess,json,hashlib,shutil,sys
stage=sys.argv[1];assert stage.startswith('runtime-r') and stage[9:].isdigit()
root=Path('/home/ubuntu/season-balance-20261102-a03-'+stage).resolve();assert root.parent==Path('/home/ubuntu')
m=json.loads((root/'manifest.json').read_text());h=json.loads((root/'runtime-handle.json').read_text());assert h['payload_sha256']==m['payload_sha256']
assert not subprocess.check_output(['docker','ps','-a','--filter','label=com.fantasycard.task='+h['label'],'--format','{{.ID}}']).strip()
work=(root/'input').resolve();assert work.parent==root and work.name=='input' and not (root/'input').is_symlink()
files={p.relative_to(work).as_posix():p for p in work.rglob('*') if p.is_file()};assert set(files)==set(m['files'])
for n,p in files.items():assert p.resolve().is_relative_to(work) and not p.is_symlink() and hashlib.sha256(p.read_bytes()).hexdigest()==m['files'][n]
before=shutil.disk_usage(root).free;shutil.rmtree(work)
proof=dict(only_verified_runtime_input_removed=True,payload_sha256=m['payload_sha256'],verified_members=len(files),free_disk_before=before,free_disk_after=shutil.disk_usage(root).free,original_binary_payload_verified_and_retained_on_local=True,source_and_public_proof_retained=True,PG_unchanged=True)
(root/'input-retirement.json').write_text(json.dumps(proof,indent=2)+'\n');print(json.dumps(proof))
"""
cmd='sudo -n python3 -c '+shlex.quote('import base64;exec(base64.b64decode('+repr(base64.b64encode(code.encode()).decode())+'))')+' '+shlex.quote(stage)
r=subprocess.run(['ssh','-i',r'C:\Users\SHENGJIAHAO\.ssh\gpt-deploy-release.pem','-o','BatchMode=yes','-o','StrictHostKeyChecking=yes','-o','ConnectTimeout=12','ubuntu@43.172.70.182',cmd],capture_output=True,text=True,timeout=45)
p=b/(stage+'-input-retirement.original.log');assert not p.exists();p.write_text(r.stdout+r.stderr,encoding='utf-8');print(r.stdout+r.stderr);assert r.returncode==0
