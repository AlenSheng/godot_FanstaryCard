from pathlib import Path
import subprocess,base64,shlex,json
b=Path(r'G:\PR13Evidence\season-balance-20261102-r1');expected={}
for n in [81,82]:expected[str(n)]=json.loads((b/f'storage-r{n}/transport-proof.json').read_text(encoding='utf-8'))['transfer_sha256']
code='expected='+repr(expected)+'\n'+"""from pathlib import Path
import hashlib,json,subprocess,shutil
home=Path('/home/ubuntu');proof=[]
for n,h in expected.items():
 root=home/('season-balance-20261102-a03-storage-r'+n);duplicate=home/('season-season-shop-r'+n+'-transfer.tar.gz');canonical=root/'transfer.tar.gz'
 assert root.resolve()==root and root.parent==home and duplicate.resolve()==duplicate and duplicate.parent==home and not duplicate.is_symlink()
 assert canonical.is_file() and duplicate.is_file() and hashlib.sha256(canonical.read_bytes()).hexdigest()==h==hashlib.sha256(duplicate.read_bytes()).hexdigest()
 assert (root/'public-evidence.tar.gz').is_file() and not (root/'sdk.env').exists()
 handle=json.loads((root/'sdk-handle.json').read_text());assert not subprocess.check_output(['docker','ps','-aq','--filter','id='+handle['container_id']],text=True).strip()
 for cid in subprocess.check_output(['docker','ps','-q'],text=True).split():
  row=json.loads(subprocess.check_output(['docker','inspect',cid]))[0]
  assert all(Path(m['Source']).resolve()!=duplicate for m in row['Mounts'])
 stat=duplicate.stat();entry={'removed_redundant_path':str(duplicate),'retained_cloud_canonical':str(canonical),'retained_local_canonical':'G:/PR13Evidence/season-balance-20261102-r1/storage-r'+n+'/transfer.tar.gz','sha256':h,'bytes':stat.st_size,'mtime_ns':stat.st_mtime_ns,'unique_test_evidence_removed':False}
 (root/'duplicate-transfer-retirement.original.json').write_text(json.dumps(entry,indent=2)+'\\n');duplicate.unlink();proof.append(entry)
print(json.dumps({'files':proof,'free_disk':shutil.disk_usage(home).free}))
"""
cmd='sudo -n python3 -c '+shlex.quote('import base64;exec(base64.b64decode('+repr(base64.b64encode(code.encode()).decode())+'))')
r=subprocess.run(['ssh','-i',r'C:\Users\SHENGJIAHAO\.ssh\gpt-deploy-release.pem','-o','BatchMode=yes','-o','StrictHostKeyChecking=yes','-o','ConnectTimeout=12','ubuntu@43.172.70.182',cmd],capture_output=True,text=True,timeout=45)
(b/'retire-duplicate-shop-transfers.original.log').write_text(r.stdout+r.stderr,encoding='utf-8');print(r.stdout+r.stderr);assert r.returncode==0
