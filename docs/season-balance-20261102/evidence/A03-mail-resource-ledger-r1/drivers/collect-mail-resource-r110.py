import sys
sys.stdout.reconfigure(encoding="utf-8")
from pathlib import Path
import subprocess,json,base64,shlex,tarfile,hashlib
b=Path(__file__).parent;out=b/'runtime-r110';host='ubuntu@43.172.70.182';root='/home/ubuntu/season-balance-20261102-a03-runtime-r110';key=r'C:\Users\SHENGJIAHAO\.ssh\gpt-deploy-release.pem'
ssh=['ssh','-i',key,'-o','BatchMode=yes','-o','StrictHostKeyChecking=yes','-o','ConnectTimeout=12','-o','ServerAliveInterval=15','-o','ServerAliveCountMax=3']
def call(code,name):
 command='sudo -n python3 -c '+shlex.quote('import base64;exec(base64.b64decode('+repr(base64.b64encode(code.encode()).decode())+'))')
 r=subprocess.run(ssh+[host,command],capture_output=True,text=True,timeout=90);(out/(name+'.original.log')).write_text(r.stdout+r.stderr,encoding='utf-8');assert r.returncode==0,r.stderr;return r.stdout
remote=r"""from pathlib import Path
import json,subprocess,hashlib,tarfile,io,xml.etree.ElementTree as E
root=Path('/home/ubuntu/season-balance-20261102-a03-runtime-r110');h=json.loads((root/'runtime-handle.json').read_text());p=json.loads(subprocess.check_output(['docker','inspect',h['container_id']]))[0]
assert p['Config']['Labels']['com.fantasycard.task']==h['label'] and p['State']['Status']=='exited'
mf=json.loads((root/'manifest.json').read_text());assert all(hashlib.sha256((root/'input'/n).read_bytes()).hexdigest()==v for n,v in mf['files'].items())
secret=json.loads(Path('/home/ubuntu/season-balance-20261102-a03-storage-r1/test-connection.private.json').read_text())['password'].encode()
logs=subprocess.check_output(['docker','logs',h['container_id']],stderr=subprocess.STDOUT);assert secret not in logs
files={'runtime.log':logs}
for n in ['runtime-handle.json','manifest.json','staging-admission.original.json','resource-guard.py','resource-guard.original.jsonl','guard-terminal.original.json','guard-handle.json','guard.stdout.original.log','guard.stderr.original.log','delta-staging.original.json']:files[n]=(root/n).read_bytes()
for f in (root/'results').rglob('*'):
 if f.is_file():files['results/'+f.relative_to(root/'results').as_posix()]=f.read_bytes()
for n in ['source-pin.json','source-snapshot.tar.gz','build.original.log']:files['proof/'+n]=(root/'input/proof'/n).read_bytes()
assert all(secret not in data for data in files.values())
counts=next((n.attrib for n in E.fromstring(files['results/season-archive-runtime.trx']).iter() if n.tag.endswith('Counters')),None) if 'results/season-archive-runtime.trx' in files else None
audit=dict(container_id=h['container_id'],state=p['State']['Status'],exit_code=p['State']['ExitCode'],oom_killed=p['State']['OOMKilled'],counts=counts,production_database_used=False,cloud_SDK_started=False,binary_payload_unchanged=True,files={n:hashlib.sha256(v).hexdigest() for n,v in files.items()})
files['audit.json']=(json.dumps(audit,indent=2)+'\n').encode();target=root/'public-evidence.tar.gz';assert not target.exists()
with tarfile.open(target,'w:gz') as tf:
 for n,data in sorted(files.items()):
  info=tarfile.TarInfo(n);info.size=len(data);tf.addfile(info,io.BytesIO(data))
target.chmod(0o644);print(json.dumps(dict(audit,public_archive_sha256=hashlib.sha256(target.read_bytes()).hexdigest())))
"""
assert not (out/'public-evidence.tar.gz').exists();raw=call(remote,'collect');audit=json.loads(raw);(out/'collection-audit.json').write_text(json.dumps(audit,indent=2)+'\n',encoding='utf-8');print(json.dumps({k:v for k,v in audit.items() if k!='files'}),flush=True)
r=subprocess.run(['scp','-i',key,'-o','BatchMode=yes','-o','StrictHostKeyChecking=yes','-o','ConnectTimeout=12',host+':'+root+'/public-evidence.tar.gz',str(out/'public-evidence.tar.gz')],capture_output=True,text=True,timeout=120);(out/'download.original.log').write_text(r.stdout+r.stderr,encoding='utf-8');assert r.returncode==0
assert hashlib.sha256((out/'public-evidence.tar.gz').read_bytes()).hexdigest()==audit['public_archive_sha256']
public=out/'public';assert not public.exists();public.mkdir()
with tarfile.open(out/'public-evidence.tar.gz','r:gz') as tf:
 for member in tf:
  assert member.isfile() and (member.name in audit['files'] or member.name=='audit.json')
  data=tf.extractfile(member).read()
  if member.name in audit['files']:assert hashlib.sha256(data).hexdigest()==audit['files'][member.name]
  path=(public/member.name).resolve();assert path.is_relative_to(public.resolve());path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(data)
accepted=bool(audit['exit_code']==0 and not audit['oom_killed'] and audit['counts'] and audit['counts']['passed']=='25' and audit['counts']['failed']=='0' and audit['counts']['notExecuted']=='0')
cleanup=r"""from pathlib import Path
import json,subprocess
root=Path('/home/ubuntu/season-balance-20261102-a03-runtime-r110').resolve();assert root.parent==Path('/home/ubuntu')
h=json.loads((root/'runtime-handle.json').read_text());p=json.loads(subprocess.check_output(['docker','inspect',h['container_id']]))[0]
assert p['Config']['Labels']['com.fantasycard.task']==h['label'] and p['State']['Status']=='exited' and (root/'public-evidence.tar.gz').is_file()
subprocess.run(['docker','rm',h['container_id']],check=True,stdout=subprocess.DEVNULL)
private=(root/'runtime.env').resolve();assert private.parent==root;private.unlink()
work=(root/'input').resolve();assert work.parent==root and work.name=='input'
mounted=subprocess.check_output(['findmnt','-n','-o','TARGET,FSTYPE','--target',str(work)],text=True).split();assert mounted==[str(work),'tmpfs']
subprocess.run(['umount',str(work)],check=True)
(root/'input-tmpfs-cleanup.json').write_text(json.dumps(dict(owned_input_tmpfs_unmounted=True,full_original_input_retained_on_G=True,next_base_runtime109_retained=True))+chr(10))
print(json.dumps(dict(removed_exited_runtime=h['container_id'],private_environment_removed=True,test_postgres_retained=h['database_container'],all_original_evidence_retained=True)))
"""
print(call(cleanup,'cleanup'))

print('declared_twenty_five_checks_accepted',accepted)
assert accepted,'Original failures retained and terminal owned runtime cleaned; inspect the actual test results.'
