from pathlib import Path
import hashlib,json,base64,shlex,subprocess,os,time
base=Path(__file__).parent;out=base/'d04-currency-r2-owned-transfer-stop-r1';assert not out.exists();out.mkdir()
terminal=json.loads((base/'d04-currency-cloud-r2/owned-local-terminal.original.json').read_bytes());assert terminal['exit']!=0 and terminal['guard'] is None
src=(base/'start-d04-currency-cloud-r2.py').read_bytes();launch='import base64;exec(base64.b64decode('+repr(base64.b64encode(src).decode())+'))';digest=hashlib.sha256(launch.encode()).hexdigest()
script="""from pathlib import Path
import subprocess,json,hashlib,time,os,signal,tarfile
root=Path('/home/ubuntu/season-balance-20261106-d04-currency-r2');public=root/'public';assert root.resolve()==root and root.parent==Path('/home/ubuntu')
assert not (public/'runtime-handle.original.json').exists() and not (root/'runtime.private.env').exists() and not (root/'input').exists()
assert not subprocess.check_output(['docker','ps','-a','--filter','label=com.fantasycard.task=season-balance-20261106-d04-currency-r2','-q']).strip()
workers=[]
for p in Path('/proc').glob('[0-9]*/cmdline'):
 try:
  if any(hashlib.sha256(a).hexdigest()==DIGEST for a in p.read_bytes().split(bytes([0]))) and (p.parent/'comm').read_text().strip().startswith('python3'):workers.append(int(p.parent.name))
 except (OSError,PermissionError):pass
assert len(workers)==1,workers
pid=workers[0];assert any(hashlib.sha256(a).hexdigest()==DIGEST for a in Path('/proc',str(pid),'cmdline').read_bytes().split(bytes([0])))
os.kill(pid,signal.SIGINT)
for _ in range(40):
 if not Path('/proc',str(pid)).exists():break
 time.sleep(.25)
assert not Path('/proc',str(pid)).exists()
assert (public/'cleanup.original.json').exists() and not (root/'runtime.private.env').exists()
assert not (public/'runtime-handle.original.json').exists()
proof=dict(at=time.time(),only_owned_python_worker_signaled=pid,signal='SIGINT',exact_launcher_argument_SHA256=DIGEST,transport_already_terminal=True,remote_runtime_never_started=True,private_config_never_created=True,input_tmpfs_never_mounted=True,other_projects_modified=False)
p=public/'transfer-stop-reconciliation.original.json';assert not p.exists();p.write_text(json.dumps(proof,indent=2)+'\\n')
archive=root/'public-evidence.forensic.tar.gz';assert not archive.exists()
with tarfile.open(archive,'w:gz') as tar:
 for p in sorted(public.rglob('*')):
  if p.is_file():tar.add(p,arcname=p.relative_to(public).as_posix())
print(json.dumps(dict(proof=proof,evidence_path=str(archive),evidence_sha256=hashlib.sha256(archive.read_bytes()).hexdigest())))
""".replace('DIGEST',repr(digest))
remote='sudo -n python3 -c '+shlex.quote('import base64;exec(base64.b64decode('+repr(base64.b64encode(script.encode()).decode())+'))')
cmd=['ssh','-n','-i',str(Path.home()/'.ssh/gpt-deploy-release.pem'),'-o','BatchMode=yes','-o','StrictHostKeyChecking=yes','-o','ConnectTimeout=10','-o','ServerAliveInterval=15','-o','ServerAliveCountMax=2','ubuntu@43.172.70.182',remote]
child=subprocess.Popen(cmd,stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.PIPE,creationflags=subprocess.CREATE_NO_WINDOW|subprocess.BELOW_NORMAL_PRIORITY_CLASS)
(out/'handle.original.json').write_text(json.dumps(dict(pid=child.pid,parent_pid=os.getpid(),started_at=time.time(),action='SIGINT exact owned stale input worker only'))+'\n')
stdout,stderr=child.communicate();(out/'stdout.original.log').write_bytes(stdout);(out/'stderr.original.log').write_bytes(stderr);(out/'terminal.original.json').write_text(json.dumps(dict(pid=child.pid,exit=child.returncode))+'\n')
assert child.returncode==0,stderr.decode(errors='replace');r=json.loads(stdout);(out/'result.original.json').write_text(json.dumps(r,indent=2)+'\n');print(json.dumps(r))
