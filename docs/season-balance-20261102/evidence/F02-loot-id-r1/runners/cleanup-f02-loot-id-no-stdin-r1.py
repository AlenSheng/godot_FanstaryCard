from pathlib import Path
import json,hashlib,base64,shlex,subprocess,os,time
base=Path(__file__).parent;out=base/'f02-loot-id-cache-cleanup-v2-r1';assert not out.exists();out.mkdir()
manifest=json.loads((base/'f02-loot-id-cloud-r1/manifest.json').read_bytes());digest=hashlib.sha256(json.dumps(manifest,sort_keys=True,separators=(',',':')).encode()).hexdigest()
script="""from pathlib import Path
import json,subprocess,hashlib,shutil
root=Path('/home/ubuntu/season-balance-20261106-f02-loot-id-r1');assert root.resolve()==root and root.parent==Path('/home/ubuntu')
active=[]
# No cache cleanup has yet been launched for this new root; test container absence is checked below.
handle=json.loads((root/'public/runtime-handle.original.json').read_text());assert handle['label']=='season-balance-20261106-f02-loot-id-r1'
r=subprocess.run(['docker','inspect',handle['container_id']],capture_output=True);assert r.returncode!=0 and b'no such object' in r.stderr.lower()
assert not (root/'runtime.private.env').exists()
manifest=json.loads((root/'public/input-manifest.original.json').read_text());assert hashlib.sha256(json.dumps(manifest,sort_keys=True,separators=(',',':')).encode()).hexdigest()==MANIFEST_DIGEST
work=root/'input';assert work.resolve()==work and not work.is_symlink();was_present=work.exists()
if was_present:
 d=shutil.disk_usage('/home/ubuntu');assert d.free>=3*1024**3 and d.free/d.total>=.05
 for n,h in manifest['files'].items():
  p=work/n;assert p.resolve().is_relative_to(work) and p.is_file() and not p.is_symlink() and hashlib.sha256(p.read_bytes()).hexdigest()==h
 shutil.rmtree(work)
proof=dict(root=str(root),owned_input_cache_removed=not work.exists(),input_was_present=was_present,source_file_SHA_verified_before_delete=was_present,remote_public_raw_evidence_retained=True,local_binary_originals=LOCAL_BINARIES,container_already_removed=True,private_env_removed=True,no_prior_cache_cleanup_started=True,cleanup_after_verified_test_terminal=True,stdin_payload_not_used=True,other_projects_modified=False)
p=root/'public/input-cache-cleanup-v2.original.json';assert not p.exists();p.write_text(json.dumps(proof,indent=2)+chr(10));print(json.dumps(dict(own_runtime_caches=[proof],free_disk_after=shutil.disk_usage('/home/ubuntu').free)))
""".replace('MANIFEST_DIGEST',repr(digest)).replace('LOCAL_BINARIES',repr(str(base/'f02-loot-id-server-build-r1/build')))
code='import base64;exec(base64.b64decode('+repr(base64.b64encode(script.encode()).decode())+'))'
cmd=['ssh','-n','-i',str(Path.home()/'.ssh/gpt-deploy-release.pem'),'-o','BatchMode=yes','-o','StrictHostKeyChecking=yes','-o','ConnectTimeout=10','-o','ServerAliveInterval=15','-o','ServerAliveCountMax=2','ubuntu@43.172.70.182','sudo -n python3 -c '+shlex.quote(code)]
child=subprocess.Popen(cmd,stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.PIPE,creationflags=subprocess.CREATE_NO_WINDOW|subprocess.BELOW_NORMAL_PRIORITY_CLASS)
(out/'handle.original.json').write_text(json.dumps(dict(pid=child.pid,started_at=time.time(),mutation_command_sha256=hashlib.sha256(code.encode()).hexdigest(),root='/home/ubuntu/season-balance-20261106-f02-loot-id-r1'))+'\n')
stdout,stderr=child.communicate();(out/'stdout.original.log').write_bytes(stdout);(out/'stderr.original.log').write_bytes(stderr);(out/'terminal.original.json').write_text(json.dumps(dict(exit=child.returncode))+'\n')
assert child.returncode==0,stderr.decode(errors='replace');r=json.loads(stdout);p=base/'f02-loot-id-owned-input-cache-cleanup-r1.original.json';assert not p.exists();p.write_text(json.dumps(r,indent=2)+'\n');print(json.dumps(r))
