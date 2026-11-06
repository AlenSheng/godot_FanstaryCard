from pathlib import Path
import json,hashlib,base64,shlex,subprocess,os,time
base=Path(__file__).parent;out=base/'d03-cache-cleanup-v2-r2';assert not out.exists();out.mkdir()
manifest=json.loads((base/'d03-maintenance-cloud-r3/manifest.json').read_bytes());digest=hashlib.sha256(json.dumps(manifest,sort_keys=True,separators=(',',':')).encode()).hexdigest()
script="""from pathlib import Path
import json,subprocess,hashlib,shutil
root=Path('/home/ubuntu/season-balance-20261106-d03-maintenance-r3');assert root.resolve()==root and root.parent==Path('/home/ubuntu')
active=[]
for p in Path('/proc').glob('[0-9]*/cmdline'):
 try:
  if any(hashlib.sha256(x).hexdigest()=='c65e395088c759208bc26c3cce1ce5b44fde25cbbf9047c8bf8931a5802d19c0' for x in p.read_bytes().split(bytes([0]))):active.append(int(p.parent.name))
 except (OSError,PermissionError):pass
assert not active
handle=json.loads((root/'public/runtime-handle.original.json').read_text());assert handle['label']=='season-balance-20261106-d03-maintenance-r3'
r=subprocess.run(['docker','inspect',handle['container_id']],capture_output=True);assert r.returncode!=0 and b'no such object' in r.stderr.lower()
assert not (root/'runtime.private.env').exists()
manifest=json.loads((root/'public/input-manifest.original.json').read_text());assert hashlib.sha256(json.dumps(manifest,sort_keys=True,separators=(',',':')).encode()).hexdigest()==MANIFEST_DIGEST
work=root/'input';assert work.resolve()==work and not work.is_symlink();was_present=work.exists()
if was_present:
 d=shutil.disk_usage('/home/ubuntu');assert d.free>=3*1024**3 and d.free/d.total>=.05
 for n,h in manifest['files'].items():
  p=work/n;assert p.resolve().is_relative_to(work) and p.is_file() and not p.is_symlink() and hashlib.sha256(p.read_bytes()).hexdigest()==h
 shutil.rmtree(work)
proof=dict(root=str(root),owned_input_cache_removed=not work.exists(),input_was_present=was_present,source_file_SHA_verified_before_delete=was_present,remote_public_raw_evidence_retained=True,local_binary_originals=LOCAL_BINARIES,container_already_removed=True,private_env_removed=True,original_cleanup_pids_absent=True,old_observation_timeout_preserved=True,stdin_payload_not_used=True,other_projects_modified=False)
p=root/'public/input-cache-cleanup-v2.original.json';assert not p.exists();p.write_text(json.dumps(proof,indent=2)+chr(10));print(json.dumps(dict(own_runtime_caches=[proof],free_disk_after=shutil.disk_usage('/home/ubuntu').free)))
""".replace('MANIFEST_DIGEST',repr(digest)).replace('LOCAL_BINARIES',repr(str(base/'d03-maintenance-preflight-r5/build')))
code='import base64;exec(base64.b64decode('+repr(base64.b64encode(script.encode()).decode())+'))'
cmd=['ssh','-n','-i',str(Path.home()/'.ssh/gpt-deploy-release.pem'),'-o','BatchMode=yes','-o','StrictHostKeyChecking=yes','-o','ConnectTimeout=10','-o','ServerAliveInterval=15','-o','ServerAliveCountMax=2','ubuntu@43.172.70.182','sudo -n python3 -c '+shlex.quote(code)]
child=subprocess.Popen(cmd,stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.PIPE,creationflags=subprocess.CREATE_NO_WINDOW|subprocess.BELOW_NORMAL_PRIORITY_CLASS)
(out/'handle.original.json').write_text(json.dumps(dict(pid=child.pid,started_at=time.time(),mutation_command_sha256=hashlib.sha256(code.encode()).hexdigest(),root='/home/ubuntu/season-balance-20261106-d03-maintenance-r3'))+'\n')
stdout,stderr=child.communicate();(out/'stdout.original.log').write_bytes(stdout);(out/'stderr.original.log').write_bytes(stderr);(out/'terminal.original.json').write_text(json.dumps(dict(exit=child.returncode))+'\n')
assert child.returncode==0,stderr.decode(errors='replace');r=json.loads(stdout);p=base/'d03-maintenance-owned-input-cache-cleanup-r3.original.json';assert not p.exists();p.write_text(json.dumps(r,indent=2)+'\n');print(json.dumps(r))
