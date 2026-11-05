from pathlib import Path
import subprocess,base64,shlex,json,sys
sys.stdout.reconfigure(encoding='utf-8')
b=Path(__file__).parent;root=b/'runtime-r106';out=root/'receiver-progress-r1.original.json';assert not out.exists()
assert 'not responding' in (root/'start-delta-retry1.original.log').read_text('utf-8')
marker=base64.b64encode((root/'start-delta-runtime.py').read_text('utf-8').encode()).decode()
code="""from pathlib import Path
import json,time,subprocess,hashlib
root=Path('/home/ubuntu/season-balance-20261102-a03-runtime-r106');expected=MARKER;pid=1843998;p=Path('/proc')/str(pid)
def sample():
 if not p.exists():return {'exists':False}
 args=(p/'cmdline').read_bytes().split(b'\\0');assert len(args)>2 and args[1]==b'-c' and expected.encode() in args[2]
 raw=(p/'stat').read_text();tail=raw[raw.rindex(')')+2:].split();io={k:int(v.strip()) for k,v in (l.split(':',1) for l in (p/'io').read_text().splitlines())}
 return dict(exists=True,pid=pid,state=tail[0],start_ticks=int(tail[19]),wchan=(p/'wchan').read_text().strip(),rchar=io['rchar'],read_bytes=io['read_bytes'],argv_sha256=hashlib.sha256((p/'cmdline').read_bytes()).hexdigest())
a=sample();time.sleep(5);z=sample();containers=subprocess.check_output(['docker','ps','-a','--filter','label=com.fantasycard.task=season-balance-20261102-a03-runtime-r106','--format','{{.ID}}']).decode().strip()
print(json.dumps(dict(samples=[a,z],runtime_root_exists=root.exists(),runtime_containers=containers)))
""".replace('MARKER',repr(marker))
cmd='sudo -n python3 -c '+shlex.quote('import base64;exec(base64.b64decode('+repr(base64.b64encode(code.encode()).decode())+'))')
r=subprocess.run(['ssh','-i',r'C:\Users\SHENGJIAHAO\.ssh\gpt-deploy-release.pem','-o','BatchMode=yes','-o','StrictHostKeyChecking=yes','-o','ConnectTimeout=12','ubuntu@43.172.70.182',cmd],capture_output=True,text=True,encoding='utf-8',timeout=45)
out.write_text(r.stdout+r.stderr,encoding='utf-8');print(r.stdout+r.stderr);assert r.returncode==0
