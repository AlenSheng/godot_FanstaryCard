from pathlib import Path

b=Path(__file__).parent;source=(b/'f03-minimal-app-worker-r3.py').read_text('utf-8')
source=source.replace('season-balance-20261107-f03-minimal-app-r3','season-balance-20261107-f03-minimal-app-r4').replace('fc-f03-app3-','fc-f03-app4-').replace('app-candidate-r3','app-candidate-r4')
source=source.replace("{'Content-Type':'application/x-protobuf'}","{'Content-Type':'application/protobuf'}")
# The embedded probe source is a repr string; make the exact media replacement there as well.
source=source.replace("{\\'Content-Type\\':\\'application/x-protobuf\\'}","{\\'Content-Type\\':\\'application/protobuf\\'}")
probe=(b/'f03-minimal-app-http-probe-r1.py').read_text('utf-8')
probe=probe.replace('production local auth remains closed despite enable flag','production local auth closed with required false flag')
probe=probe.replace("check('production local auth closed with required false flag',request('POST','/api/v1/auth/local',local,{'Content-Type':'application/x-protobuf'}),404)","check('old media type rejected',request('POST','/api/v1/auth/local',local,{'Content-Type':'application/x-protobuf'}),415)\ncheck('production local auth closed with required false flag',request('POST','/api/v1/auth/local',local,{'Content-Type':'application/protobuf'}),404)")
old="    assert response['status']==status and extra,name+': unexpected response'\n    checks.append(dict(name=name,status=response['status'],content_type=response['headers'].get('Content-Type'),body_bytes=len(response['body']),body_sha256=hashlib.sha256(response['body']).hexdigest()))"
new="    checks.append(dict(name=name,status=response['status'],expected=status,passed=response['status']==status and extra,content_type=response['headers'].get('Content-Type'),body_bytes=len(response['body']),body_sha256=hashlib.sha256(response['body']).hexdigest()))"
assert old in probe;probe=probe.replace(old,new).replace("result=dict(ok=True,checks=checks", "result=dict(ok=all(c['passed'] for c in checks),checks=checks")
probe += "\nassert result['ok'], 'HTTP boundary outcomes contain failures; all checks recorded'\n"
(b/'f03-minimal-app-http-probe-r4.py').write_text(probe,encoding='utf-8')
start=source.index("    probe=root/'http-probe.py';probe.write_text(");end=source.index('\n    command=',start)
source=source[:start]+"    probe=root/'http-probe.py';probe.write_text("+repr(probe)+")"+source[end:]
target=b/'f03-minimal-app-worker-r4.py';assert not target.exists();compile(source,str(target),'exec');target.write_text(source,encoding='utf-8')
prepare=(b/'prepare-f03-minimal-app-input-r3.py').read_text('utf-8').replace('f03-minimal-app-input-r3','f03-minimal-app-input-r4').replace('season-balance-20261107-f03-minimal-app-r3','season-balance-20261107-f03-minimal-app-r4')
(b/'prepare-f03-minimal-app-input-r4.py').write_text(prepare,encoding='utf-8')
runner=(b/'run-f03-minimal-app-cloud-r3.py').read_text('utf-8').replace('f03-minimal-app-cloud-r3','f03-minimal-app-cloud-r4').replace('f03-minimal-app-input-r3','f03-minimal-app-input-r4').replace('f03-minimal-app-worker-r3.py','f03-minimal-app-worker-r4.py').replace('season-balance-20261107-f03-minimal-app-r3','season-balance-20261107-f03-minimal-app-r4')
needle="r=guard.guarded_run(command,env=dict(os.environ),timeout=90,wait_seconds=30);(out/'sftp.stdout.original.log').write_text(r.stdout);(out/'sftp.stderr.original.log').write_text(r.stderr);assert r.returncode==0"
replacement="""import ctypes
class Memory(ctypes.Structure):
    _fields_=[('length',ctypes.c_ulong),('load',ctypes.c_ulong)]+[(n,ctypes.c_ulonglong) for n in ['total','available','total_page','available_page','total_virtual','available_virtual','extended']]
def available():
    m=Memory();m.length=ctypes.sizeof(m);assert ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m));return m.available
samples=[]
for _ in range(3):samples.append(available());time.sleep(1)
assert min(samples)>=3*1024**3
with (out/'sftp.stdout.original.log').open('wb') as stdout,(out/'sftp.stderr.original.log').open('wb') as stderr:
    child=subprocess.Popen(command,stdin=subprocess.DEVNULL,stdout=stdout,stderr=stderr,creationflags=flags)
    (out/'sftp-handle.original.json').write_text(json.dumps(dict(pid=child.pid,parent_pid=os.getpid(),command=command,started_at=time.time(),observation_seconds=180),indent=2)+'\\n')
    began=last=time.monotonic()
    while child.poll() is None:
        if available()<2*1024**3:child.kill();child.wait(timeout=10);raise RuntimeError('Owned transfer reached memory reserve; reconcile child SSH')
        if time.monotonic()-began>180:raise RuntimeError('Follow recorded same live SFTP handle before resuming; no duplicate worker')
        if time.monotonic()-last>=30:print(json.dumps(dict(stage='same complete-file SFTP',pid=child.pid,live=True)),flush=True);last=time.monotonic()
        time.sleep(.25)
assert child.returncode==0
"""
assert needle in runner;runner=runner.replace(needle,replacement)
(b/'run-f03-minimal-app-cloud-r4.py').write_text(runner,encoding='utf-8');compile(runner,str(b/'run-f03-minimal-app-cloud-r4.py'),'exec');print(str(target))
