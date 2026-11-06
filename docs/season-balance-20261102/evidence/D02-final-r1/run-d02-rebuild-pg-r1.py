from pathlib import Path
import base64,ctypes,hashlib,json,os,queue,re,shlex,socket,subprocess,sys,threading,time

sys.stdout.reconfigure(encoding='utf-8');repo=Path.cwd();base=Path(__file__).parent;build=base/'d02-rebuild-build-r2';out=base/'d02-rebuild-pg-r1';assert not out.exists()
assert json.loads((build/'result.json').read_bytes())['exit']==0
pin=json.loads((build/'source-pin.json').read_bytes());assert all(hashlib.sha256((repo/n).read_bytes()).hexdigest()==h for n,h in pin.items())
budget_path=repo/'docs/season-balance-20261102/D02-BUDGET.json';prior=budget_path.read_bytes();budget=json.loads(prior);assert budget['used']==91 and budget['current_handle'] is None
out.mkdir();(out/'prior-budget.original.json').write_bytes(prior);(out/'policy.original.json').write_bytes((base/'d02-rebuild-policy.before-run-r1.json').read_bytes())
observations=out/'observations';binary=build/'build/bin/FantasyCard.Server.Tests/debug';binaries={p.relative_to(binary).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in binary.rglob('*') if p.is_file()};(out/'binary-manifest.original.json').write_text(json.dumps(binaries,indent=2)+'\n')
class MemoryStatus(ctypes.Structure):
    _fields_=[('length',ctypes.c_ulong),('load',ctypes.c_ulong)]+[(n,ctypes.c_ulonglong) for n in ['total','available','total_page','available_page','total_virtual','available_virtual','extended']]
def available():
    status=MemoryStatus();status.length=ctypes.sizeof(status);assert ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status));return status.available
def admit(kind):
    started=time.monotonic()
    while True:
        samples=[]
        for _ in range(3):samples.append(available());time.sleep(1)
        with (out/'admission.original.jsonl').open('a') as log:log.write(json.dumps(dict(kind=kind,samples=samples,reserve=2*1024**3,startup=1024**3,admitted=min(samples)>=3*1024**3))+'\n')
        if min(samples)>=3*1024**3:return
        if time.monotonic()-started>=180:raise RuntimeError('Local3GiB admission unavailable; no new owned heavy process')
        time.sleep(10)
remote="""from pathlib import Path
import json,os,re,shutil,subprocess,sys,threading
stop=threading.Event()
def sample():
 m=dict(x.split(':',1) for x in Path('/proc/meminfo').read_text().splitlines());d=shutil.disk_usage('/home/ubuntu');r=dict(available_ram=int(m['MemAvailable'].split()[0])*1024,free_disk=d.free,disk_fraction=d.free/d.total);r['guard_ok']=r['available_ram']>=500*1024**2 and d.free>=3*1024**3 and d.free/d.total>=.05;return r
first=sample();assert first['guard_ok']
cid='803968e390014540be88f60b9ac43203946d0145bf886fc61d9d9d4d04bc3b1a';p=json.loads(subprocess.check_output(['docker','inspect',cid]))[0]
assert p['State']['Status']=='running' and p['Config']['Labels']['com.fantasycard.task']=='season-balance-20261102-a03-storage-r1'
private=json.loads(Path('/home/ubuntu/season-balance-20261102-a03-storage-r1/test-connection.private.json').read_text())
print(json.dumps(dict(resource=first,password=private['password'])),flush=True)
def watch():
 while not stop.wait(2):
  r=sample();print(json.dumps(dict(resource=r)),flush=True)
  if not r['guard_ok']:os._exit(71)
thread=threading.Thread(target=watch,daemon=True);thread.start();data=sys.stdin.read();stop.set();thread.join(timeout=3)
r=sample();print(json.dumps(dict(resource=r)),flush=True)
if not r['guard_ok']:sys.exit(71)
request=json.loads(data);schemas=request['schemas'];assert all(re.fullmatch(r'fc_runtime_test_[0-9a-f]{32}',s) for s in schemas)
sql='SELECT nspname FROM pg_namespace WHERE nspname IN ('+','.join("'"+s+"'" for s in schemas)+') ORDER BY nspname' if schemas else 'SELECT nspname FROM pg_namespace WHERE false'
try:
 present=subprocess.check_output(['docker','exec','-i',cid,'psql','-U','season_stage','-d','season_stage','-qAt','-c',sql],stderr=subprocess.PIPE).decode().splitlines();print(json.dumps(dict(cleanup_check=dict(success=True,owned_schemas=schemas,schemas_still_present=present,check_only=True))),flush=True)
except Exception as e:print(json.dumps(dict(cleanup_check=dict(success=False,error_type=type(e).__name__,check_only=True))),flush=True);sys.exit(74)
"""
ssh=None;child=None;monitor=None;password=None;error=None;stdout='';stderr='';cleanup={};cloud_failed=threading.Event();finishing=threading.Event();started_at=time.time();guard_reason=None
command=['dotnet',str(binary/'FantasyCard.Server.Tests.dll'),'-noLogo','-noColor','-noAutoReporters','-failSkips','-parallel','none','-reporter','verbose','-class','FantasyCard.Server.Tests.Persistence.PostgresSeasonDeathRebuildTests','-trx',str(out/'cases.trx'),'-xml',str(out/'cases.xml')]
try:
    admit('owned-SSH-monitor');port=55643
    with socket.socket() as check:check.bind(('127.0.0.1',port))
    remote_command='sudo -n python3 -c '+shlex.quote('import base64;exec(base64.b64decode('+repr(base64.b64encode(remote.encode()).decode())+'))')
    ssh=subprocess.Popen(['ssh','-i',r'C:\Users\SHENGJIAHAO\.ssh\gpt-deploy-release.pem','-o','BatchMode=yes','-o','StrictHostKeyChecking=yes','-o','ConnectTimeout=15','-o','ServerAliveInterval=15','-o','ServerAliveCountMax=2','-o','ExitOnForwardFailure=yes','-L',f'127.0.0.1:{port}:127.0.0.1:55631','ubuntu@43.172.70.182',remote_command],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,creationflags=subprocess.CREATE_NO_WINDOW|subprocess.BELOW_NORMAL_PRIORITY_CLASS)
    (out/'owned-SSH-start.original.json').write_text(json.dumps(dict(pid=ssh.pid,started_at=time.time(),local_bind=f'127.0.0.1:{port}',isolated_remote_bind='127.0.0.1:55631',cloud_SDK=False))+'\n')
    q=queue.Queue();reader=threading.Thread(target=lambda:q.put(ssh.stdout.readline()),daemon=True);reader.start();line=q.get(timeout=40);reader.join(timeout=1);assert line,'No owned tunnel preflight';first=json.loads(line);password=first.pop('password');del line
    (out/'cloud-first.original.json').write_text(json.dumps(first)+'\n')
    def observe():
        try:
            with (out/'cloud-resource.original.jsonl').open('a') as log:
                for line in ssh.stdout:
                    row=json.loads(line)
                    if 'resource' in row:
                        log.write(json.dumps(row['resource'])+'\n');log.flush()
                        if not row['resource']['guard_ok']:cloud_failed.set()
                    elif 'cleanup_check' in row:cleanup.update(row['cleanup_check']);(out/'schema-cleanup.original.json').write_text(json.dumps(cleanup,indent=2)+'\n')
        except Exception as e:cloud_failed.set();(out/'monitor-error.original.json').write_text(json.dumps(dict(type=type(e).__name__))+'\n')
        if not finishing.is_set():cloud_failed.set()
    monitor=threading.Thread(target=observe,daemon=True);monitor.start()
    for _ in range(40):
        assert ssh.poll() is None
        try:
            with socket.create_connection(('127.0.0.1',port),.25):break
        except OSError:time.sleep(.25)
    else:raise RuntimeError('Owned tunnel failed to become ready')
    admit('owned-precompiled-dotnet');assert not cloud_failed.is_set()
    env=dict(os.environ,DOTNET_CLI_UI_LANGUAGE='en',DOTNET_NOLOGO='1',DOTNET_CLI_TELEMETRY_OPTOUT='1',FANTASYCARD_TEST_POSTGRES=f'Host=127.0.0.1;Port={port};Database=season_stage;Username=season_stage;Password='+password+';MaxPoolSize=16;Timeout=10;CommandTimeout=30',FANTASYCARD_RUN_D02_REBUILD='1',FANTASYCARD_D02_REBUILD_OUTPUT=str(observations),FANTASYCARD_RUN_D02_ROUTES='',FANTASYCARD_RUN_D02_DUELS='',FANTASYCARD_RUN_D01_BOUNDARIES='',FANTASYCARD_RUN_C16_CALIBRATION='',FANTASYCARD_C16_REUSE_PREFLIGHT='',FANTASYCARD_RUN_THEME_COMPARISON='',FANTASYCARD_RUN_B05_MATRIX='',FANTASYCARD_RUN_B05_FINAL_NINE='')
    child=subprocess.Popen(command,env=env,stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,encoding='utf-8',errors='replace',creationflags=subprocess.CREATE_NO_WINDOW|subprocess.BELOW_NORMAL_PRIORITY_CLASS)
    handle=dict(parent_pid=os.getpid(),child_pid=child.pid,SSH_pid=ssh.pid,started_at=time.time(),command=command,prior_D02_used=91,reserved_match_attempts=6,local_reserve_GiB=2,startup_GiB=1)
    (out/'owned-dotnet-start.original.json').write_text(json.dumps(handle,indent=2)+'\n');budget_path.write_text(json.dumps(dict(item='D02',used=91,remaining=209,maximum=300,current_handle=handle),indent=2)+'\n')
    while True:
        try:stdout,stderr=child.communicate(timeout=.25);break
        except subprocess.TimeoutExpired:
            if available()<2*1024**3:guard_reason='local2GiB'
            elif cloud_failed.is_set():guard_reason='cloud500MiB/3GiB/5percent'
            elif time.time()-handle['started_at']>=600:guard_reason='600s observation limit'
            if guard_reason:child.kill();stdout,stderr=child.communicate(timeout=10);break
    assert password not in stdout+stderr,'Secret unexpectedly appeared in test output; do not persist raw output'
    (out/'test.original.log').write_text(stdout+stderr,encoding='utf-8')
except Exception as e:error=dict(type=type(e).__name__,error=str(e));(out/'driver-error.original.json').write_text(json.dumps(error,indent=2)+'\n')
finally:
    if child is not None and child.poll() is None:child.kill();child.communicate(timeout=10)
    schemas=[]
    for p in observations.glob('*/schema.original.json') if observations.exists() else []:
        name=json.loads(p.read_bytes())['schema'];assert re.fullmatch(r'fc_runtime_test_[0-9a-f]{32}',name);schemas.append(name)
    finishing.set()
    if ssh is not None:
        try:
            if ssh.poll() is None:ssh.stdin.write(json.dumps(dict(schemas=sorted(schemas))).encode());ssh.stdin.flush();ssh.stdin.close()
        except (OSError,BrokenPipeError):pass
        try:ssh.wait(timeout=15)
        except subprocess.TimeoutExpired:ssh.terminate();ssh.wait(timeout=10)
        if monitor:monitor.join(timeout=5)
        ssh_error=ssh.stderr.read().decode('utf-8',errors='replace');assert password is None or password not in ssh_error;(out/'SSH.stderr.original.log').write_text(ssh_error,encoding='utf-8');(out/'owned-SSH-terminal.original.json').write_text(json.dumps(dict(pid=ssh.pid,exit=ssh.returncode,only_owned_handle_stopped=True))+'\n')
    attempts=[]
    for p in observations.glob('*/attempts.original.jsonl') if observations.exists() else []:attempts.extend(json.loads(x) for x in p.read_text('utf-8').splitlines())
    assert len(attempts)<=6
    proof=dict(exit=child.returncode if child else None,error=error,guard_reason=guard_reason,actual_match_attempts=len(attempts),total_D02_used=91+len(attempts),D02_remaining=209-len(attempts),source_unchanged=all(hashlib.sha256((repo/n).read_bytes()).hexdigest()==h for n,h in pin.items()),binary_unchanged=all(hashlib.sha256((binary/n).read_bytes()).hexdigest()==h for n,h in binaries.items()),cloud_guard_ok=not cloud_failed.is_set(),owned_schemas=schemas,cleanup_verified=cleanup.get('success') is True and cleanup.get('schemas_still_present')==[],production_database_used=False,cloud_SDK_started=False,only_own_tunnel_and_validation_child_stopped=True,B05_new_runs=0,C16_new_runs=0,D01_new_runs=0,seconds=time.time()-started_at)
    (out/'result.json').write_text(json.dumps(proof,indent=2)+'\n');budget_path.write_text(json.dumps(dict(item='D02',used=proof['total_D02_used'],remaining=proof['D02_remaining'],maximum=300,current_handle=None,last_result=str(out/'result.json'),prior_budget=str(out/'prior-budget.original.json')),indent=2)+'\n')
    if password is None or password not in stdout+stderr:print((stdout+stderr)[-6500:])
    print(json.dumps(proof))
assert proof['exit']==0 and error is None and guard_reason is None and proof['actual_match_attempts']==6 and proof['source_unchanged'] and proof['binary_unchanged'] and proof['cloud_guard_ok'] and proof['cleanup_verified']
