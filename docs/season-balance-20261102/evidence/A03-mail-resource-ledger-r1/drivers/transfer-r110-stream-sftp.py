from pathlib import Path
import json,subprocess,hashlib,time,sys,re
sys.stdout.reconfigure(encoding='utf-8');b=Path(__file__).parent;o=b/'runtime-r110';index=sys.argv[1];mode=sys.argv[2];assert re.fullmatch(r'r[1-9][0-9]*',index) and mode in ['put','reput']
stream=o/'transport-stream-file-r1.bin';m=json.loads((o/'file-stream-manifest.json').read_text('utf-8'));assert stream.stat().st_size==m['bytes'] and hashlib.sha256(stream.read_bytes()).hexdigest()==m['sha256']
if mode=='put':assert json.loads((o/'file-transfer-setup.original.json').read_text('utf-8'))['stream_sha256']==m['sha256']
else:
    p=json.loads((o/('file-prefix-'+index+'.original.json')).read_text('utf-8'));assert p['local_prefix_identical'] and not p['complete']
out=o/('sftp-'+index+'.original.json');assert not out.exists();batch=o/('sftp-'+index+'.batch');batch.write_text(mode+' "'+stream.as_posix()+'" "/home/ubuntu/season-balance-20261102-a03-runtime-r110-upload/stream-r1.bin.part"\nbye\n',encoding='utf-8')
cmd=['sftp','-R','1','-B','8192','-i',r'C:\Users\SHENGJIAHAO\.ssh\gpt-deploy-release.pem','-o','BatchMode=yes','-o','StrictHostKeyChecking=yes','-o','ConnectTimeout=12','-o','ServerAliveInterval=15','-o','ServerAliveCountMax=12','-b',str(batch),'ubuntu@43.172.70.182'];started=time.monotonic()
try:
    r=subprocess.run(cmd,capture_output=True,text=True,encoding='utf-8',timeout=600);result=dict(exit=r.returncode,seconds=time.monotonic()-started,stdout=r.stdout,stderr=r.stderr)
except subprocess.TimeoutExpired as e:
    result=dict(observation_timeout_seconds=600,seconds=time.monotonic()-started,remote_partial_file_must_be_observed_before_retry=True,stdout=str(e.stdout or ''),stderr=str(e.stderr or ''))
result.update(expected_bytes=m['bytes'],expected_sha256=m['sha256'],mode=mode);out.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8');print(json.dumps(result));assert result.get('exit')==0
