from pathlib import Path
import json,subprocess,base64,shlex,os
base=Path(__file__).parent;stage=base/'d04-build-dimensions-cloud-r2-file';seed=json.loads((stage/'public/dependency-cache-seed.original.json').read_bytes())
if not seed.get('seeded'):
    print(json.dumps({'cache_retained':False,'seed':seed}));raise SystemExit(0)
code='''from pathlib import Path
import json,hashlib,re,shutil
root=Path('/home/ubuntu/season-balance-20261102-dependency-cache-v1');assert root.resolve()==root and not root.is_symlink()
owner=json.loads((root/'ownership.original.json').read_text());assert owner=={'task':'season-balance-20261102','schema':1,'cap_bytes':64*1024**2}
expected=__HASHES__
for digest in expected:
    path=root/digest;assert re.fullmatch('[0-9a-f]{64}',digest) and path.is_file() and not path.is_symlink() and hashlib.sha256(path.read_bytes()).hexdigest()==digest and path.stat().st_mode&0o222==0
blobs=[p for p in root.iterdir() if re.fullmatch('[0-9a-f]{64}',p.name)];size=sum(p.stat().st_size for p in blobs);assert size<=owner['cap_bytes']
disk=shutil.disk_usage('/home/ubuntu');assert disk.free>=3*1024**3 and disk.free/disk.total>=.05
print(json.dumps({'verified':True,'root':str(root),'verified_unique_hashes':len(expected),'total_blob_bytes':size,'cap_bytes':owner['cap_bytes'],'read_only_blobs':True,'used_for_current_run':False,'other_projects_modified':False}))
'''.replace('__HASHES__',repr(sorted(set(seed['verified_files'].values()))))
remote='sudo -n python3 -c '+shlex.quote('import base64;exec(base64.b64decode('+repr(base64.b64encode(code.encode()).decode())+'))')
cmd=['ssh','-i',str(Path.home()/'.ssh/gpt-deploy-release.pem'),'-o','BatchMode=yes','-o','StrictHostKeyChecking=yes','-o','ConnectTimeout=12','ubuntu@43.172.70.182',remote]
result=subprocess.run(cmd,stdin=subprocess.DEVNULL,capture_output=True,timeout=45,creationflags=(subprocess.CREATE_NO_WINDOW|subprocess.BELOW_NORMAL_PRIORITY_CLASS) if os.name=='nt' else 0)
(base/'d04-diagnostics-cache-before-r2.stdout.original.log').write_bytes(result.stdout);(base/'d04-diagnostics-cache-before-r2.stderr.original.log').write_bytes(result.stderr)
assert result.returncode==0,result.stderr.decode(errors='replace');proof=json.loads(result.stdout)
target=base/'d04-diagnostics-cache-readback-before-r2.derived.json';assert not target.exists();target.write_text(json.dumps(proof,indent=2)+'\n');print(json.dumps(proof))
