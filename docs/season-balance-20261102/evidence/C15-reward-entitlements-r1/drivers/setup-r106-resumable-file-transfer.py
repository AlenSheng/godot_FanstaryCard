from pathlib import Path
import subprocess,json,hashlib,base64,shlex,sys
sys.stdout.reconfigure(encoding='utf-8');b=Path(__file__).parent;o=b/'runtime-r106';out=o/'file-transfer-setup.original.json';assert not out.exists()
stop=json.loads((o/'disconnected-receiver-stop.original.json').read_text('utf-8'));assert stop['terminal'] and stop['no_runtime_container_or_PG_test_was_started']
old=b/'runtime-r104/transport-stream-r3.bin';oldhash=hashlib.sha256(old.read_bytes()).hexdigest();assert oldhash=='4f1fdd4076b7d988733d2e5e7de942cd3742f4d0e493654ab76f1d503c5f43b1'
mf=json.loads((o/'manifest.json').read_text('utf-8'));stream=json.loads((o/'file-stream-manifest.json').read_text('utf-8'));delta=json.loads((o/'delta-manifest.json').read_text('utf-8'))
control=dict(expanded=mf['expanded_bytes'],stream_bytes=stream['bytes'],stream_sha256=stream['sha256'],delta_bytes=delta['delta_bytes'],old_stream_sha256=oldhash)
code=r"""from pathlib import Path
import json,subprocess,shutil,hashlib,time
v=CONTROL;target=Path('/home/ubuntu/season-balance-20261102-a03-runtime-r106');root=Path('/home/ubuntu/season-balance-20261102-a03-runtime-r106-upload')
assert not target.exists();assert not subprocess.check_output(['sudo','-n','docker','ps','-a','--filter','label=com.fantasycard.task=season-balance-20261102-a03-runtime-r106','--format','{{.ID}}']).strip()
oldroot=Path('/home/ubuntu/season-balance-20261102-a03-runtime-r104-upload').resolve();assert oldroot.parent==Path('/home/ubuntu')
old=oldroot/'stream-r4.bin.part';retirement=oldroot/'stream-input-retirement.json'
if old.exists():
 assert not old.is_symlink() and old.resolve().parent==oldroot and hashlib.sha256(old.read_bytes()).hexdigest()==v['old_stream_sha256']
 assert not subprocess.check_output(['sudo','-n','docker','ps','-a','--filter','label=com.fantasycard.task=season-balance-20261102-a03-runtime-r104','--format','{{.ID}}']).strip()
 size=old.stat().st_size;old.unlink();retirement.write_text(json.dumps(dict(only_verified_old_upload_copy_removed=True,bytes=size,sha256=v['old_stream_sha256'],complete_identical_original_retained_locally=True,original_public_evidence_and_PG_unchanged=True))+chr(10))
else:assert retirement.exists() and json.loads(retirement.read_text())['sha256']==v['old_stream_sha256']
assert not root.exists();samples=[]
for _ in range(3):
 m=dict(l.split(':',1) for l in Path('/proc/meminfo').read_text().splitlines());d=shutil.disk_usage('/home/ubuntu');row=dict(available_ram=int(m['MemAvailable'].split()[0])*1024,free_disk=d.free,free_ratio=d.free/d.total);samples.append(row)
 assert row['available_ram']>=1800*1024**2 and d.free>=3*1024**3+v['expanded']+v['stream_bytes']+v['delta_bytes']+64*1024**2+2*1024**2 and d.free/d.total>=.05
 time.sleep(1)
root.mkdir(mode=0o700);proof=dict(samples=samples,expanded_bytes=v['expanded'],compressed_file_bytes=v['stream_bytes'],existing_delta_staging_reserve_bytes=v['delta_bytes'],both_compressed_copy_and_existing_staging_reserve_included=True,stream_sha256=v['stream_sha256'],minimum_disk_bytes=3*1024**3,minimum_free_fraction=.05,only_owned_upload_directory_created=True,old_upload_retirement=json.loads(retirement.read_text()),SDK_started=False)
(root/'admission.original.json').write_text(json.dumps(proof,indent=2)+chr(10));print(json.dumps(proof))
""".replace('CONTROL',repr(control))
cmd='python3 -c '+shlex.quote(code)
try:r=subprocess.run(['ssh','-n','-i',r'C:\Users\SHENGJIAHAO\.ssh\gpt-deploy-release.pem','-o','BatchMode=yes','-o','StrictHostKeyChecking=yes','-o','ConnectTimeout=12','ubuntu@43.172.70.182',cmd],capture_output=True,text=True,encoding='utf-8',timeout=45)
except subprocess.TimeoutExpired:
    (o/'file-transfer-setup-observation-timeout.original.json').write_text(json.dumps(dict(remote_outcome_unknown=True,follow_existing_upload_directory_before_retry=True))+'\n',encoding='utf-8');raise
out.write_text(r.stdout+r.stderr,encoding='utf-8');print(r.stdout+r.stderr);assert r.returncode==0
