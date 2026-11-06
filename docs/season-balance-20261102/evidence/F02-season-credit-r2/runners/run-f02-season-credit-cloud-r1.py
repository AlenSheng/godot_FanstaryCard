from pathlib import Path
import base64, ctypes, hashlib, io, json, os, shlex, struct, subprocess, sys, tarfile, time

sys.stdout.reconfigure(encoding='utf-8'); base=Path(__file__).parent; repo=Path.cwd(); out=base/'f02-season-credit-cloud-r1'
assert not out.exists(); out.mkdir(); binary=base/'f02-season-credit-build-r1/build/bin/FantasyCard.Server.Tests/debug'
assert json.loads((base/'f02-season-credit-build-r1/result.json').read_bytes())['exit']==0
files={}; expanded=0
with tarfile.open(out/'payload.tar.gz','w:gz') as tar:
    for p in sorted(binary.rglob('*')):
        if p.is_file():
            raw=p.read_bytes(); name='bin/'+p.relative_to(binary).as_posix(); files[name]=hashlib.sha256(raw).hexdigest(); expanded+=len(raw)
            info=tarfile.TarInfo(name); info.size=len(raw); tar.addfile(info,io.BytesIO(raw))
    for suffix in ['bytes','sha256','version.txt']:
        p=repo/('server/config/archive/season-v1-config-16/fantasycard.config.'+suffix);raw=p.read_bytes();name=p.relative_to(repo).as_posix();files[name]=hashlib.sha256(raw).hexdigest();expanded+=len(raw);info=tarfile.TarInfo(name);info.size=len(raw);tar.addfile(info,io.BytesIO(raw))
    p=repo/'server/src/FantasyCard.Server/FantasyCard.Server.csproj';raw=p.read_bytes();name='server/src/FantasyCard.Server/FantasyCard.Server.csproj';files[name]=hashlib.sha256(raw).hexdigest();expanded+=len(raw);info=tarfile.TarInfo(name);info.size=len(raw);tar.addfile(info,io.BytesIO(raw))
body=(out/'payload.tar.gz').read_bytes(); manifest=dict(payload_sha256=hashlib.sha256(body).hexdigest(),payload_bytes=len(body),expanded_bytes=expanded,files=files)
(out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n'); header=json.dumps(manifest).encode(); data=struct.pack('!I',len(header))+header+body
class Memory(ctypes.Structure):
    _fields_=[('length',ctypes.c_ulong),('load',ctypes.c_ulong)]+[(n,ctypes.c_ulonglong) for n in ['total','available','total_page','available_page','total_virtual','available_virtual','extended']]
def available():
    m=Memory(); m.length=ctypes.sizeof(m); assert ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m)); return m.available
samples=[]
for _ in range(3): samples.append(available()); time.sleep(1)
(out/'admission.original.json').write_text(json.dumps(dict(samples=samples,reserve=2*1024**3,startup=1024**3))+'\n'); assert min(samples)>=3*1024**3
script=(base/'start-f02-season-credit-cloud-r1.py').read_bytes()
remote='sudo -n python3 -u -c '+shlex.quote('import base64;exec(base64.b64decode('+repr(base64.b64encode(script).decode())+'))')
ssh=['ssh','-i',str(Path.home()/'.ssh/gpt-deploy-release.pem'),'-o','BatchMode=yes','-o','StrictHostKeyChecking=yes','-o','ConnectTimeout=15','-o','ServerAliveInterval=15','-o','ServerAliveCountMax=2','ubuntu@43.172.70.182']
proc=subprocess.Popen(ssh+[remote],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,creationflags=subprocess.CREATE_NO_WINDOW|subprocess.BELOW_NORMAL_PRIORITY_CLASS)
(out/'owned-local-handle.original.json').write_text(json.dumps(dict(parent_pid=os.getpid(),SSH_pid=proc.pid,started_at=time.time(),remote_root='/home/ubuntu/season-balance-20261106-f02-season-credit-r1',label='season-balance-20261106-f02-season-credit-r1',payload_sha256=manifest['payload_sha256']))+'\n')
first=True; guard=None
while True:
    try: stdout,stderr=proc.communicate(input=data if first else None,timeout=.25); break
    except subprocess.TimeoutExpired:
        first=False
        if available()<2*1024**3:
            guard='local2GiB'; proc.terminate(); stdout,stderr=proc.communicate(timeout=15); break
(out/'transport.stdout.original.log').write_bytes(stdout); (out/'transport.stderr.original.log').write_bytes(stderr)
(out/'owned-local-terminal.original.json').write_text(json.dumps(dict(pid=proc.pid,exit=proc.returncode,guard=guard))+'\n')
assert proc.returncode==0 and guard is None,stderr.decode('utf-8',errors='replace')
rows=[json.loads(line) for line in stdout.decode().splitlines()]; done=rows[-1]
assert done['evidence_path']=='/home/ubuntu/season-balance-20261106-f02-season-credit-r1/public-evidence.tar.gz'
download=subprocess.run(ssh+['sudo -n cat '+shlex.quote(done['evidence_path'])],capture_output=True,timeout=60,creationflags=subprocess.CREATE_NO_WINDOW|subprocess.BELOW_NORMAL_PRIORITY_CLASS)
assert download.returncode==0 and hashlib.sha256(download.stdout).hexdigest()==done['evidence_sha256']
(out/'public-evidence.tar.gz').write_bytes(download.stdout); target=out/'public'; target.mkdir()
with tarfile.open(fileobj=io.BytesIO(download.stdout),mode='r:gz') as tar:
    for member in tar.getmembers():
        assert member.isfile() and not Path(member.name).is_absolute() and '..' not in Path(member.name).parts
        dest=target/member.name;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(tar.extractfile(member).read())
result=json.loads((target/'result.json').read_bytes()); result['collected_raw_archive_sha256']=done['evidence_sha256']
result['local_binary_inputs_unchanged']=all(hashlib.sha256(((binary/Path(n).relative_to('bin')) if n.startswith('bin/') else repo/n).read_bytes()).hexdigest()==h for n,h in files.items())
(out/'result.json').write_text(json.dumps(result,indent=2)+'\n'); print((target/'test.original.log').read_text(encoding='utf-8')[-6000:]); print(json.dumps(result))
assert result['exit']==0 and result['guard_ok'] and result['input_unchanged'] and result['local_binary_inputs_unchanged'] and result['schemas_still_present']==[]
