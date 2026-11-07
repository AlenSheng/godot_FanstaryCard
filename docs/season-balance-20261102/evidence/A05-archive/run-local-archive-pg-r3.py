from pathlib import Path
import importlib.util,os,json,hashlib,shutil
repo=Path.cwd();base=Path(r'G:\PR13Evidence\season-balance-20261102-r1');out=base/'local-archive-pg-r3';assert not out.exists();out.mkdir()
files=['config/FantasyCard_Config.xlsx','client/data/catalog.json']
for folder in ['server/config/generated','client/data/generated','server/config/archive/season-v1-config-4','server/config/archive/season-v1-config-5','server/config/archive/season-v1-config-6','server/config/archive/season-v1-config-7','server/config/archive/season-v1-config-8','server/config/archive/season-v1-config-9','server/config/archive/season-v1-config-10','server/config/archive/season-v1-config-11']:
 for n in ['fantasycard.config.bytes','fantasycard.config.sha256','fantasycard.config.version.txt']:files.append(folder+'/'+n)
for n in files:
 p=out/n;p.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(repo/n,p);assert p.read_bytes()==(repo/n).read_bytes()
pins={p.relative_to(repo).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in (repo/'server').rglob('*') if p.is_file() and p.suffix in ['.cs','.sql','.csproj','.props','.targets','.bytes','.proto'] and not any(x in p.parts for x in ['bin','obj','.artifacts'])}
pins.update({n:hashlib.sha256((repo/n).read_bytes()).hexdigest() for n in files});(out/'source-pin.json').write_text(json.dumps(pins,indent=2)+'\n')
spec=importlib.util.spec_from_file_location('fixture_runtime',repo/'client/tests/fixture_runtime.py');r=importlib.util.module_from_spec(spec);spec.loader.exec_module(r)
import subprocess,base64,shlex,threading,queue,socket,time,ctypes,xml.etree.ElementTree as ET
rt=r
class MS(ctypes.Structure):
    _fields_=[('length',ctypes.c_ulong),('load',ctypes.c_ulong)]+[(n,ctypes.c_ulonglong) for n in ['total','available','total_page','available_page','total_virtual','available_virtual','extended']]
samples=[]
for _ in range(3):
    ms=MS();ms.length=ctypes.sizeof(ms);assert ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(ms));samples.append(ms.available);time.sleep(1)
(out/'tunnel-admission.original.json').write_text(json.dumps(dict(available_samples=samples,reserve=6*1024**3,startup=1024**3))+'\n',encoding='utf-8')
assert min(samples)>=7*1024**3
remote_code="""from pathlib import Path
import json,shutil,subprocess,sys,threading,os
stop=threading.Event()
def sample():
 m=dict(l.split(':',1) for l in Path('/proc/meminfo').read_text().splitlines());d=shutil.disk_usage('/home/ubuntu')
 r=dict(available_ram=int(m['MemAvailable'].split()[0])*1024,free_disk=d.free,disk_fraction=d.free/d.total)
 r['guard_ok']=r['available_ram']>=500*1024**2 and r['free_disk']>=3*1024**3 and r['disk_fraction']>=.05
 return r
first=sample();assert first['guard_ok']
p=json.loads(subprocess.check_output(['docker','inspect','803968e390014540be88f60b9ac43203946d0145bf886fc61d9d9d4d04bc3b1a']))[0]
assert p['State']['Status']=='running' and p['Config']['Labels']['com.fantasycard.task']=='season-balance-20261102-a03-storage-r1'
c=json.loads(Path('/home/ubuntu/season-balance-20261102-a03-storage-r1/test-connection.private.json').read_text())
print(json.dumps(dict(resource=first,password=c['password'])),flush=True)
def watch():
 while not stop.wait(2):
  current=sample();print(json.dumps(dict(resource=current)),flush=True)
  if not current['guard_ok']:os._exit(71)
thread=threading.Thread(target=watch,daemon=True);thread.start();sys.stdin.read();stop.set();thread.join(timeout=3)
"""
ssh=['ssh','-i',r'C:\Users\SHENGJIAHAO\.ssh\gpt-deploy-release.pem','-o','BatchMode=yes','-o','StrictHostKeyChecking=yes','-o','ConnectTimeout=15','-o','ServerAliveInterval=15','-o','ServerAliveCountMax=2']
with socket.socket() as sock:sock.bind(('127.0.0.1',55639))
command='sudo -n python3 -c '+shlex.quote('import base64;exec(base64.b64decode('+repr(base64.b64encode(remote_code.encode()).decode())+'))')
tunnel=subprocess.Popen(ssh+['-o','ExitOnForwardFailure=yes','-L','127.0.0.1:55639:127.0.0.1:55631','ubuntu@43.172.70.182',command],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,creationflags=subprocess.CREATE_NO_WINDOW|subprocess.BELOW_NORMAL_PRIORITY_CLASS)
(out/'owned-tunnel-start.json').write_text(json.dumps(dict(pid=tunnel.pid,local_bind='127.0.0.1:55639',remote_test_bind='127.0.0.1:55631',created_at=time.time(),production_database_used=False))+'\n',encoding='utf-8')
password=None;finishing=threading.Event();cloud_failed=threading.Event();monitor=None
try:
 q=queue.Queue();reader=threading.Thread(target=lambda:q.put(tunnel.stdout.readline()),daemon=True);reader.start();line=q.get(timeout=40);reader.join(timeout=1)
 assert line,'No private tunnel preflight returned';record=json.loads(line);password=record.pop('password');resource=record['resource'];del line,record
 with (out/'cloud-resource.original.jsonl').open('w',encoding='utf-8') as log:log.write(json.dumps(resource)+'\n')
 def observe():
  with (out/'cloud-resource.original.jsonl').open('a',encoding='utf-8') as log:
   for line in tunnel.stdout:
    row=json.loads(line)['resource'];log.write(json.dumps(row)+'\n');log.flush()
    if not row['guard_ok']:cloud_failed.set()
   if not finishing.is_set():cloud_failed.set()
 monitor=threading.Thread(target=observe,daemon=True);monitor.start()
 for _ in range(40):
  assert tunnel.poll() is None
  try:
   with socket.create_connection(('127.0.0.1',55639),.25):break
  except OSError:time.sleep(.25)
 else:raise RuntimeError('Owned tunnel did not become ready')
 selected='FullyQualifiedName~PostgresSeasonArchiveTests|FullyQualifiedName~PostgresSeasonPreparationTests|FullyQualifiedName~PostgresSeasonMatchmakingTests|FullyQualifiedName~PostgresSeasonReadModelTests'
 cmd=['dotnet','test',str(repo/'server/tests/FantasyCard.Server.Tests/FantasyCard.Server.Tests.csproj'),'--artifacts-path',str(base/'local-archive-pg-r2/build'),'--filter',selected,'--logger','trx;LogFileName=archive-followup.trx','--results-directory',str(out/'results'),'--verbosity','minimal','-m:1','-p:UseSharedCompilation=false']
 env=dict(os.environ,DOTNET_CLI_UI_LANGUAGE='en',DOTNET_NOLOGO='1',DOTNET_CLI_TELEMETRY_OPTOUT='1',FANTASYCARD_TEST_POSTGRES='Host=127.0.0.1;Port=55639;Database=season_stage;Username=season_stage;Password='+password+';MaxPoolSize=16;Timeout=10;CommandTimeout=30')
 print('Archive focused follow-up: local SDK, owned isolated PostgreSQL tunnel, continuous local/cloud guards; no cloud SDK or game routes',flush=True)
 result=rt.guarded_run(cmd,env=env,timeout=900)
 text=result.stdout+result.stderr;assert password not in text
 (out/'test.original.log').write_text(text,encoding='utf-8')
 proof=dict(exit=result.returncode,production_database_used=False,cloud_SDK_started=False,new_game_matches=0,B05_not_run=True,source_unchanged=all(hashlib.sha256((repo/n).read_bytes()).hexdigest()==h for n,h in pins.items()),cloud_guard_ok=not cloud_failed.is_set(),command=cmd)
 (out/'result.json').write_text(json.dumps(proof,indent=2)+'\n',encoding='utf-8');print(text[-9000:]);print(json.dumps(proof));assert result.returncode==0 and proof['source_unchanged'] and proof['cloud_guard_ok']
 tree=ET.parse(out/'results/archive-followup.trx');counts=next(n.attrib for n in tree.iter() if n.tag.endswith('Counters'));assert counts['failed']=='0' and counts['notExecuted']=='0';print(json.dumps(counts))
finally:
 finishing.set();tunnel.stdin.close()
 try:tunnel.wait(timeout=10)
 except subprocess.TimeoutExpired:tunnel.terminate();tunnel.wait(timeout=10)
 if monitor:monitor.join(timeout=5)
 error=tunnel.stderr.read().decode('utf-8',errors='replace');assert password is None or password not in error
 (out/'tunnel.stderr.original.log').write_text(error,encoding='utf-8')
 (out/'owned-tunnel-terminal.json').write_text(json.dumps(dict(pid=tunnel.pid,exit_code=tunnel.returncode,own_tunnel_only_stopped=True,other_projects_modified=False,cloud_guard_failed=cloud_failed.is_set()))+'\n',encoding='utf-8')
