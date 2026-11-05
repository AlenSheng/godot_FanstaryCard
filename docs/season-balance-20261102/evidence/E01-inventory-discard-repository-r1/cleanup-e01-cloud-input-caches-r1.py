from pathlib import Path
import base64, json, shlex, subprocess

base=Path(__file__).parent; entries=[]
for number in [1,2,3]:
    local=base/f'e01-discard-cloud-runtime-r{number}'
    entries.append(dict(root=f'/home/ubuntu/season-balance-20261102-e01-discard-runtime-r{number}',
        label=f'season-balance-20261102-e01-discard-runtime-r{number}',manifest=json.loads((local/'manifest.json').read_bytes()),
        local_binary_originals=str(base/('e01-discard-build-r2' if number==3 else 'e01-discard-build-r1')/'build')))
script='''from pathlib import Path
import json,subprocess,shutil,hashlib,sys
entries=json.load(sys.stdin);d=shutil.disk_usage('/home/ubuntu');assert d.free>=3*1024**3 and d.free/d.total>=.05
result=[]
for e in entries:
 root=Path(e['root']);assert root.is_absolute() and root.parent==Path('/home/ubuntu') and root.name.startswith('season-balance-20261102-e01-discard-runtime-r') and root.resolve()==root
 handle=json.loads((root/'public/runtime-handle.original.json').read_text());assert handle['label']==e['label']
 current=subprocess.run(['docker','inspect',handle['container_id']],capture_output=True);assert current.returncode!=0 and b'No such object' in current.stderr
 manifest=json.loads((root/'public/input-manifest.original.json').read_text());assert manifest==e['manifest']
 work=root/'input';assert work.resolve()==root/'input' and not work.is_symlink()
 for n,h in manifest['files'].items():
  p=work/n;assert p.resolve().is_relative_to(work) and p.is_file() and not p.is_symlink() and hashlib.sha256(p.read_bytes()).hexdigest()==h
 assert not (root/'runtime.private.env').exists()
 shutil.rmtree(work)
 proof=dict(root=str(root),owned_input_cache_removed=not work.exists(),remote_public_raw_evidence_retained=True,local_binary_originals=e['local_binary_originals'],container_already_removed=True,private_env_removed=True,other_projects_modified=False)
 (root/'public/input-cache-cleanup.original.json').write_text(json.dumps(proof,indent=2)+'\\n');result.append(proof)
print(json.dumps(dict(own_runtime_caches=result,free_disk_after=shutil.disk_usage('/home/ubuntu').free)))
'''
command='sudo -n python3 -c '+shlex.quote('import base64;exec(base64.b64decode('+repr(base64.b64encode(script.encode()).decode())+'))')
result=subprocess.run(['ssh','-i',str(Path.home()/'.ssh/gpt-deploy-release.pem'),'-o','BatchMode=yes','-o','ConnectTimeout=15','ubuntu@43.172.70.182',command],input=json.dumps(entries).encode(),capture_output=True,timeout=45,creationflags=subprocess.CREATE_NO_WINDOW|subprocess.BELOW_NORMAL_PRIORITY_CLASS)
assert result.returncode==0,result.stderr.decode('utf-8',errors='replace')
proof=json.loads(result.stdout);output=base/'e01-cloud-owned-input-cache-cleanup-r1.original.json';assert not output.exists();output.write_text(json.dumps(proof,indent=2)+'\n')
print('Verified threeowned inputcaches cleaned; publicraw/localbinaries retained. Free disk:',proof['free_disk_after'])
