from pathlib import Path
import subprocess,shlex,base64,json,hashlib
b=Path(__file__).parent;stage=b/'storage-r90';host='ubuntu@43.172.70.182';key=r'C:\Users\SHENGJIAHAO\.ssh\gpt-deploy-release.pem';flags=subprocess.CREATE_NO_WINDOW|subprocess.BELOW_NORMAL_PRIORITY_CLASS
ssh=['ssh','-i',key,'-o','BatchMode=yes','-o','StrictHostKeyChecking=yes','-o','ConnectTimeout=12','-o','ServerAliveInterval=10','-o','ServerAliveCountMax=3']
def remote_py(code,name,timeout=45):
 command='sudo -n python3 -c '+shlex.quote('import base64;exec(base64.b64decode('+repr(base64.b64encode(code.encode()).decode())+'))')
 try:r=subprocess.run(ssh+[host,command],capture_output=True,text=True,timeout=timeout,creationflags=flags)
 except subprocess.TimeoutExpired:
  (stage/(name+'.timeout.json')).write_text(json.dumps({'observation_timeout':True,'restart_authorized_by_timeout':False,'must_inspect_same_stage':True})+'\n');raise
 (stage/(name+'.original.log')).write_text(r.stdout+r.stderr,encoding='utf-8');print(r.stdout[-2500:]+r.stderr,flush=True);assert r.returncode==0;return r.stdout
remote_py("""from pathlib import Path
import subprocess,json,shutil
root=Path('/home/ubuntu/season-balance-20261102-a03-storage-r90');assert root.parent==Path('/home/ubuntu') and not root.exists()
rows=subprocess.check_output(['docker','ps','--format','{{.Names}}'],text=True).splitlines();assert not any(n.startswith('fc-season-a03-storage-') for n in rows)
assert not subprocess.check_output(['docker','ps','-aq','--filter','name=^fc-season-a03-storage-20261102-r90$'],text=True).strip()
m={l.split(':')[0]:int(l.split()[1])*1024 for l in Path('/proc/meminfo').read_text().splitlines() if len(l.split())>1 and l.split()[1].isdigit()};d=shutil.disk_usage('/home/ubuntu')
assert m['MemAvailable']>=1800*1024**2 and d.free>=3*1024**3+256*1024**2 and d.free/d.total>=.05
root.mkdir();print(json.dumps({'root_created':str(root),'available_ram':m['MemAvailable'],'free_disk':d.free,'SDK_started':False}))
""",'prepare-cloud')
target='/home/ubuntu/season-season-theme-r90-transfer.tar.gz'
try:
 r=subprocess.run(['scp','-i',key,'-o','BatchMode=yes','-o','StrictHostKeyChecking=yes','-o','ConnectTimeout=12','-o','ServerAliveInterval=10',str(stage/'transfer.tar.gz'),host+':'+target],capture_output=True,text=True,timeout=180,creationflags=flags)
except subprocess.TimeoutExpired:
 (stage/'scp.timeout.json').write_text(json.dumps({'transport_timeout_seconds':180,'SDK_start_not_reached':True,'next':'Verify exact transfer SHA and current handle before any action'})+'\n');raise
(stage/'scp.original.log').write_text(r.stdout+r.stderr,encoding='utf-8');assert r.returncode==0
proof=json.loads((stage/'transport-proof.json').read_text());unpack=(b/'unpack-stage-transfer.py').read_text();install="""from pathlib import Path
import hashlib,shutil,sys
src=Path('/home/ubuntu/season-season-theme-r90-transfer.tar.gz');dst=Path('/home/ubuntu/season-balance-20261102-a03-storage-r90/transfer.tar.gz')
assert not dst.exists() and hashlib.sha256(src.read_bytes()).hexdigest()==EXPECTED
shutil.copyfile(src,dst)
sys.argv=['unpack','storage-r90',EXPECTED]
""".replace('EXPECTED',repr(proof['transfer_sha256']))
remote_py(install+'\n'+unpack,'unpack')
text=remote_py("""import runpy
runpy.run_path('/home/ubuntu/season-balance-20261102-a03-storage-r90/start-storage-tests.py',run_name='__main__')
""",'start',timeout=45)
handle=json.loads(text);(stage/'sdk-handle.json').write_text(json.dumps(handle,indent=2)+'\n');print('Owned r84 handle captured; follow the same container only.',flush=True)
