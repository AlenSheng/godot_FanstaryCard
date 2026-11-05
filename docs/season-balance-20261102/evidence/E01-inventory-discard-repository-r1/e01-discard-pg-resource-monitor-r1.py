from pathlib import Path
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
