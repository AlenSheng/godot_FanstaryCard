from pathlib import Path
import subprocess,json,base64,shlex,hashlib
b=Path(r'G:\PR13Evidence\season-balance-20261102-r1');o=b/'runtime-r104';transfer=json.loads((o/'partial-transfer-prefix-verified-r5.original.json').read_text(encoding='utf-8'));assert transfer['complete'] and transfer['local_prefix_identical']
source=(o/'start-runtime.py').read_text(encoding='utf-8');encoded=base64.b64encode(source.encode()).decode();stream=o/'transport-stream-r3.bin';digest=hashlib.sha256(stream.read_bytes()).hexdigest()
code='''from pathlib import Path
import subprocess,json,sys,hashlib
p=Path('/home/ubuntu/season-balance-20261102-a03-runtime-r104-upload/stream-r4.bin.part');assert p.stat().st_size==int(sys.argv[1]);assert hashlib.sha256(p.read_bytes()).hexdigest()==sys.argv[2]
print(json.dumps({'validated_stream_bytes':p.stat().st_size,'stream_sha256':sys.argv[2]}),flush=True)
with p.open('rb') as f:
 r=subprocess.run(['python3','-c','import base64;exec(base64.b64decode('+repr(sys.argv[3])+'))'],stdin=f,capture_output=True,text=True,timeout=60)
print(r.stdout,end='',flush=True);sys.stderr.write(r.stderr);assert r.returncode==0
'''
cmd='sudo -n python3 -c '+shlex.quote(code)+' '+str(stream.stat().st_size)+' '+digest+' '+shlex.quote(encoded)
try:
 r=subprocess.run(['ssh','-n','-i',r'C:\Users\SHENGJIAHAO\.ssh\gpt-deploy-release.pem','-o','BatchMode=yes','-o','StrictHostKeyChecking=yes','-o','ConnectTimeout=8','ubuntu@43.172.70.182',cmd],capture_output=True,text=True,timeout=80)
except subprocess.TimeoutExpired as e:
 (o/'file-start-observation-timeout.original.json').write_text(json.dumps(dict(timeout_seconds=80,remote_outcome_unknown=True,follow_same_stage_required=True))+'\n');raise
p=o/'file-start-r5.original.log';assert not p.exists();p.write_text(r.stdout+r.stderr,encoding='utf-8');print(r.stdout+r.stderr);assert r.returncode==0
for line in r.stdout.splitlines():
 d=json.loads(line)
 if 'container_id' in d:(o/'runtime-handle.json').write_text(json.dumps(d,indent=2)+'\n',encoding='utf-8')
