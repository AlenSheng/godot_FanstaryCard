from pathlib import Path
import base64, ctypes, hashlib, json, os, queue, re, shlex, socket, subprocess, sys, threading, time

sys.stdout.reconfigure(encoding='utf-8')
repo=Path.cwd(); base=Path(__file__).parent; build=base/'e01-discard-build-r1'; out=base/'e01-discard-pg-r2'
assert not out.exists() and json.loads((build/'result.json').read_bytes())['exit']==0
pin=json.loads((build/'source-pin.json').read_bytes()); assert all(hashlib.sha256((repo/n).read_bytes()).hexdigest()==h for n,h in pin.items())
out.mkdir(); binary=build/'build/bin/FantasyCard.Server.Tests/debug'
binaries={p.relative_to(binary).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in binary.rglob('*') if p.is_file()}
(out/'binary-manifest.original.json').write_text(json.dumps(binaries,indent=2)+'\n')
budgets={n:(repo/'docs/season-balance-20261102'/f'{n}-BUDGET.json').read_bytes() for n in ['B05','C16','D01','D02','D03']}
class MemoryStatus(ctypes.Structure):
    _fields_=[('length',ctypes.c_ulong),('load',ctypes.c_ulong)]+[(n,ctypes.c_ulonglong) for n in ['total','available','total_page','available_page','total_virtual','available_virtual','extended']]
def available():
    status=MemoryStatus(); status.length=ctypes.sizeof(status); assert ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)); return status.available
def admit(kind):
    samples=[]
    for _ in range(3): samples.append(available()); time.sleep(1)
    with (out/'admission.original.jsonl').open('a') as log: log.write(json.dumps(dict(kind=kind,samples=samples,reserve=2*1024**3,startup=1024**3,admitted=min(samples)>=3*1024**3))+'\n')
    assert min(samples)>=3*1024**3,'Local admission refused; no next owned process started'
remote=(base/'e01-discard-pg-resource-monitor-r1.py').read_bytes()
ssh=child=monitor=password=None; error=guard_reason=None; stdout=stderr=''; cleanup={}; cloud_failed=threading.Event(); finishing=threading.Event(); started=time.time()
command=['dotnet',str(binary/'FantasyCard.Server.Tests.dll'),'-noLogo','-noColor','-noAutoReporters','-failSkips','-parallel','none','-reporter','verbose','-class','FantasyCard.Server.Tests.Persistence.PostgresInventoryDiscardTests','-trx',str(out/'cases.trx'),'-xml',str(out/'cases.xml')]
try:
    admit('owned-SSH-monitor')
    with socket.socket() as check: check.bind(('127.0.0.1',0)); port=check.getsockname()[1]
    remote_command='sudo -n python3 -u -c '+shlex.quote("import base64;exec(base64.b64decode('"+base64.b64encode(remote).decode()+"'))")
    ssh=subprocess.Popen(['ssh','-i',str(Path.home()/'.ssh/gpt-deploy-release.pem'),'-o','BatchMode=yes','-o','ExitOnForwardFailure=yes','-o','ConnectTimeout=15','-L',f'127.0.0.1:{port}:127.0.0.1:55631','ubuntu@43.172.70.182',remote_command],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,creationflags=subprocess.CREATE_NO_WINDOW|subprocess.BELOW_NORMAL_PRIORITY_CLASS)
    (out/'owned-SSH-start.original.json').write_text(json.dumps(dict(pid=ssh.pid,started_at=time.time(),local_bind=f'127.0.0.1:{port}',isolated_remote_bind='127.0.0.1:55631',cloud_SDK=False))+'\n')
    q=queue.Queue(); reader=threading.Thread(target=lambda:q.put(ssh.stdout.readline()),daemon=True); reader.start(); line=q.get(timeout=40); reader.join(timeout=1)
    assert line,'No owned tunnel preflight'; first=json.loads(line); password=first.pop('password'); del line
    (out/'cloud-first.original.json').write_text(json.dumps(first)+'\n')
    def observe():
        try:
            with (out/'cloud-resource.original.jsonl').open('a') as log:
                for line in ssh.stdout:
                    row=json.loads(line)
                    if 'resource' in row:
                        log.write(json.dumps(row['resource'])+'\n'); log.flush()
                        if not row['resource']['guard_ok']: cloud_failed.set()
                    elif 'cleanup_check' in row:
                        cleanup.update(row['cleanup_check']); (out/'schema-cleanup.original.json').write_text(json.dumps(cleanup,indent=2)+'\n')
        except Exception as e: cloud_failed.set(); (out/'monitor-error.original.json').write_text(json.dumps(dict(type=type(e).__name__))+'\n')
        if not finishing.is_set(): cloud_failed.set()
    monitor=threading.Thread(target=observe,daemon=True); monitor.start()
    admit('owned-precompiled-dotnet'); assert not cloud_failed.is_set()
    env=dict(os.environ,DOTNET_CLI_UI_LANGUAGE='en',DOTNET_NOLOGO='1',DOTNET_CLI_TELEMETRY_OPTOUT='1',FANTASYCARD_TEST_POSTGRES=f'Host=127.0.0.1;Port={port};Database=season_stage;Username=season_stage;Password='+password+';MaxPoolSize=16;Timeout=10;CommandTimeout=30;ApplicationName=fc-e01-discard-r1',FANTASYCARD_DISCARD_SCHEMA_EVIDENCE=str(out/'owned-schemas.original.jsonl'))
    for name in list(env):
        if name.startswith('FANTASYCARD_RUN_'): env[name]=''
    child=subprocess.Popen(command,env=env,stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,encoding='utf-8',errors='replace',creationflags=subprocess.CREATE_NO_WINDOW|subprocess.BELOW_NORMAL_PRIORITY_CLASS)
    handle=dict(parent_pid=os.getpid(),child_pid=child.pid,SSH_pid=ssh.pid,started_at=time.time(),command=command,local_reserve_GiB=2,startup_GiB=1,new_matches=0)
    (out/'owned-dotnet-start.original.json').write_text(json.dumps(handle,indent=2)+'\n')
    while True:
        try: stdout,stderr=child.communicate(timeout=.25); break
        except subprocess.TimeoutExpired:
            if available()<2*1024**3: guard_reason='local2GiB'
            elif cloud_failed.is_set(): guard_reason='cloud500MiB/3GiB/5percent'
            elif time.time()-handle['started_at']>=900: guard_reason='900s declared test window'
            if guard_reason: child.kill(); stdout,stderr=child.communicate(timeout=10); break
    assert password not in stdout+stderr,'Secret unexpectedly appeared; raw output not persisted'
    (out/'test.original.log').write_text(stdout+stderr,encoding='utf-8')
except Exception as e:
    error=dict(type=type(e).__name__,error=str(e)); (out/'driver-error.original.json').write_text(json.dumps(error,indent=2)+'\n')
finally:
    if child is not None and child.poll() is None: child.kill(); child.communicate(timeout=10)
    p=out/'owned-schemas.original.jsonl'; schemas=[json.loads(line)['schema'] for line in p.read_text().splitlines()] if p.exists() else []
    assert all(re.fullmatch(r'fc_runtime_test_[0-9a-f]{32}',name) for name in schemas)
    finishing.set()
    if ssh is not None:
        try:
            if ssh.poll() is None: ssh.stdin.write(json.dumps(dict(schemas=sorted(schemas))).encode()); ssh.stdin.flush(); ssh.stdin.close()
        except (OSError,BrokenPipeError): pass
        try: ssh.wait(timeout=15)
        except subprocess.TimeoutExpired: ssh.terminate(); ssh.wait(timeout=10)
        if monitor: monitor.join(timeout=5)
        text=ssh.stderr.read().decode('utf-8',errors='replace'); assert password is None or password not in text
        (out/'SSH.stderr.original.log').write_text(text,encoding='utf-8'); (out/'owned-SSH-terminal.original.json').write_text(json.dumps(dict(pid=ssh.pid,exit=ssh.returncode,only_owned_handle_stopped=True))+'\n')
    proof=dict(exit=child.returncode if child else None,error=error,guard_reason=guard_reason,source_unchanged=all(hashlib.sha256((repo/n).read_bytes()).hexdigest()==h for n,h in pin.items()),binary_unchanged=all(hashlib.sha256((binary/n).read_bytes()).hexdigest()==h for n,h in binaries.items()),cloud_guard_ok=not cloud_failed.is_set(),owned_schemas=schemas,cleanup_verified=cleanup.get('success') is True and cleanup.get('schemas_still_present')==[],production_database_used=False,cloud_SDK_started=False,only_own_tunnel_and_validation_child_stopped=True,all_match_budgets_unchanged=all((repo/'docs/season-balance-20261102'/f'{n}-BUDGET.json').read_bytes()==value for n,value in budgets.items()),new_matches=0,seconds=time.time()-started)
    (out/'result.json').write_text(json.dumps(proof,indent=2)+'\n')
    if password is None or password not in stdout+stderr: print((stdout+stderr)[-7000:])
    print(json.dumps(proof))
assert proof['exit']==0 and error is None and guard_reason is None and all(proof[k] for k in ['source_unchanged','binary_unchanged','cloud_guard_ok','cleanup_verified','all_match_budgets_unchanged'])
