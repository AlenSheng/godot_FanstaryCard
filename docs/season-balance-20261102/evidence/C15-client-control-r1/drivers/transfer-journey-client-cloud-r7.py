from pathlib import Path
import hashlib,json,subprocess,time

stage=Path(__file__).parent/'journey-client-cloud-r7';handle=stage/'transfer-handle.json';assert not handle.exists()
manifest=json.loads((stage/'manifest.json').read_text('utf-8'));assert hashlib.sha256((stage/'input.tar.gz').read_bytes()).hexdigest()==manifest['payload_sha256']
command=['sftp','-R','1','-B','8192','-i',r'C:\Users\SHENGJIAHAO\.ssh\gpt-deploy-release.pem','-o','BatchMode=yes','-o','StrictHostKeyChecking=yes','-o','ConnectTimeout=12','-o','ServerAliveInterval=15','-o','ServerAliveCountMax=12','-b',str(stage/'sftp-put.batch'),'ubuntu@43.172.70.182']
with (stage/'sftp.stdout.original.log').open('xb') as out,(stage/'sftp.stderr.original.log').open('xb') as err:
 child=subprocess.Popen(command,stdout=out,stderr=err,stdin=subprocess.DEVNULL,creationflags=subprocess.CREATE_NO_WINDOW|subprocess.BELOW_NORMAL_PRIORITY_CLASS)
 handle.write_text(json.dumps({'pid':child.pid,'argv':command,'started_at':time.time(),'native_started':False},indent=2)+'\n',encoding='utf-8')
 try:code=child.wait(timeout=600)
 except subprocess.TimeoutExpired:child.kill();child.wait(timeout=15);code=124
(stage/'transfer-terminal.original.json').write_text(json.dumps({'returncode':code,'native_started':False},indent=2)+'\n',encoding='utf-8');print(json.dumps({'returncode':code}));assert code==0
