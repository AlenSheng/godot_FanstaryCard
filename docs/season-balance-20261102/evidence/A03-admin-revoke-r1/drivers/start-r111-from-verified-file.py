from pathlib import Path
import json,subprocess,base64,shlex,hashlib,sys,re
sys.stdout.reconfigure(encoding='utf-8');b=Path(__file__).parent;o=b/'runtime-r111';index=sys.argv[1];assert re.fullmatch(r'r[1-9][0-9]*',index)
proof=json.loads((o/('file-prefix-'+index+'.original.json')).read_text('utf-8'));assert proof['complete'] and proof['local_prefix_identical'];assert not proof['runtime_root_exists'] and not proof['runtime_containers'];assert not (o/'runtime-handle.json').exists()
out=o/('file-start-'+index+'.original.log');assert not out.exists();stream=o/'transport-stream-file-r1.bin';digest=hashlib.sha256(stream.read_bytes()).hexdigest();source=(o/'start-delta-runtime.py').read_text('utf-8');encoded=base64.b64encode(source.encode()).decode()
code=r"""from pathlib import Path
import subprocess,json,hashlib,sys
root=Path('/home/ubuntu/season-balance-20261102-a03-runtime-r111-upload');p=root/'stream-r1.bin.part'
assert root.resolve().parent==Path('/home/ubuntu') and not root.is_symlink();assert not p.is_symlink() and p.resolve().parent==root.resolve();assert p.stat().st_size==int(sys.argv[1]);assert hashlib.sha256(p.read_bytes()).hexdigest()==sys.argv[2]
print(json.dumps(dict(validated_stream_bytes=p.stat().st_size,stream_sha256=sys.argv[2])),flush=True)
with p.open('rb') as f:r=subprocess.run(['python3','-c','import base64;exec(base64.b64decode('+repr(sys.argv[3])+'))'],stdin=f,capture_output=True,text=True,timeout=60)
print(r.stdout,end='',flush=True);sys.stderr.write(r.stderr);assert r.returncode==0
"""
cmd='sudo -n python3 -c '+shlex.quote(code)+' '+str(stream.stat().st_size)+' '+digest+' '+shlex.quote(encoded)
try:r=subprocess.run(['ssh','-n','-i',r'C:\Users\SHENGJIAHAO\.ssh\gpt-deploy-release.pem','-o','BatchMode=yes','-o','StrictHostKeyChecking=yes','-o','ConnectTimeout=12','ubuntu@43.172.70.182',cmd],capture_output=True,text=True,encoding='utf-8',timeout=80)
except subprocess.TimeoutExpired as error:
    (o/('file-start-'+index+'-observation-timeout.original.json')).write_text(json.dumps(dict(remote_outcome_unknown=True,follow_same_stage_required=True,stdout=str(error.stdout or ''),stderr=str(error.stderr or '')))+'\n',encoding='utf-8');raise
out.write_text(r.stdout+r.stderr,encoding='utf-8');print(r.stdout+r.stderr);assert r.returncode==0
for line in r.stdout.splitlines():
    data=json.loads(line)
    if 'container_id' in data:(o/'runtime-handle.json').write_text(json.dumps(data,indent=2)+'\n',encoding='utf-8')
