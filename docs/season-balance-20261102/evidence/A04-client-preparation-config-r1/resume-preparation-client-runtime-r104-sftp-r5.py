from pathlib import Path
import subprocess,json,time,hashlib
b=Path(r'G:\PR13Evidence\season-balance-20261102-r1');o=b/'runtime-r104';local=o/'transport-stream-r3.bin';digest=hashlib.sha256(local.read_bytes()).hexdigest();proof=json.loads((o/'partial-transfer-prefix-verified.original.json').read_text(encoding='utf-8'));assert proof['local_prefix_identical'] and not proof['complete']
batch=o/'resume-sftp-r5.batch';assert not batch.exists();batch.write_text('reput "'+local.as_posix()+'" "/home/ubuntu/season-balance-20261102-a03-runtime-r104-upload/stream-r4.bin.part"\n',encoding='utf-8')
cmd=['sftp','-b',str(batch),'-i',r'C:\Users\SHENGJIAHAO\.ssh\gpt-deploy-release.pem','-o','BatchMode=yes','-o','StrictHostKeyChecking=yes','-o','ConnectTimeout=8','ubuntu@43.172.70.182'];started=time.monotonic()
try:
 r=subprocess.run(cmd,capture_output=True,text=True,timeout=240);result=dict(exit=r.returncode,seconds=time.monotonic()-started,stdout=r.stdout,stderr=r.stderr,resumed_from_bytes=proof['remote_bytes'],expected_bytes=local.stat().st_size,sha256=digest)
except subprocess.TimeoutExpired as e:
 result=dict(transport_timeout_seconds=240,seconds=time.monotonic()-started,stdout=(e.stdout or b'').decode(errors='replace') if isinstance(e.stdout,bytes) else e.stdout,stderr=(e.stderr or b'').decode(errors='replace') if isinstance(e.stderr,bytes) else e.stderr,resumed_from_bytes=proof['remote_bytes'],expected_bytes=local.stat().st_size,sha256=digest)
p=o/'sftp-resume-r5.original.json';assert not p.exists();p.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8');print(json.dumps(result),flush=True)
assert result.get('exit')==0
