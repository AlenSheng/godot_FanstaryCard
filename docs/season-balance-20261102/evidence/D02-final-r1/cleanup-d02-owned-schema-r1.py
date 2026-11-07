from pathlib import Path
import base64,ctypes,json,re,shlex,subprocess,time

base=Path(__file__).parent;root=base/'d02-rebuild-pg-r1';out=base/'d02-rebuild-owned-cleanup-r1';assert not out.exists()
assert json.loads((root/'result.json').read_bytes())['guard_reason']=='600s observation limit'
check=json.loads((root/'schema-cleanup.original.json').read_bytes());names=check['schemas_still_present'];assert len(names)==1
mage=json.loads((root/'observations/Mage/schema.original.json').read_bytes())['schema'];priest=json.loads((root/'observations/Priest/schema.original.json').read_bytes())['schema'];assert names==[mage] and mage!=priest and re.fullmatch(r'fc_runtime_test_[0-9a-f]{32}',mage)
assert (root/'observations/Priest/result.original.json').exists() and not (root/'observations/Mage/attempts.original.jsonl').exists()
class M(ctypes.Structure):_fields_=[('l',ctypes.c_ulong),('load',ctypes.c_ulong)]+[(n,ctypes.c_ulonglong) for n in ['t','a','p','pa','v','va','e']]
samples=[]
for _ in range(3):
    m=M();m.l=ctypes.sizeof(m);assert ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m));samples.append(m.a);time.sleep(1)
assert min(samples)>=3*1024**3;out.mkdir();(out/'ownership.original.json').write_text(json.dumps(dict(target=names,source=str(root/'observations/Mage/schema.original.json'),original_presence=check,local_admission_samples=samples),indent=2)+'\n')
remote="""from pathlib import Path
import json,re,shutil,subprocess
def guard():
 m=dict(x.split(':',1) for x in Path('/proc/meminfo').read_text().splitlines());d=shutil.disk_usage('/home/ubuntu');r=dict(available_ram=int(m['MemAvailable'].split()[0])*1024,free_disk=d.free,disk_fraction=d.free/d.total);assert r['available_ram']>=500*1024**2 and r['free_disk']>=3*1024**3 and r['disk_fraction']>=.05;return r
cid='803968e390014540be88f60b9ac43203946d0145bf886fc61d9d9d4d04bc3b1a';p=json.loads(subprocess.check_output(['docker','inspect',cid]))[0];assert p['State']['Status']=='running' and p['Config']['Labels']['com.fantasycard.task']=='season-balance-20261102-a03-storage-r1'
"""
remote+='names='+repr(names)+'\n'
remote+="""assert all(re.fullmatch(r'fc_runtime_test_[0-9a-f]{32}',s) for s in names)
before=guard();sql="SET lock_timeout='5s';"+''.join('DROP SCHEMA IF EXISTS "'+s+'" CASCADE;' for s in names)
r=subprocess.run(['docker','exec','-i',cid,'psql','-U','season_stage','-d','season_stage','-v','ON_ERROR_STOP=1','-qAt','-c',sql],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True);assert r.returncode==0
query='SELECT nspname FROM pg_namespace WHERE nspname IN ('+','.join("'"+s+"'" for s in names)+')';present=subprocess.check_output(['docker','exec','-i',cid,'psql','-U','season_stage','-d','season_stage','-qAt','-c',query]).decode().splitlines();assert present==[]
print(json.dumps(dict(owned_schema_dropped=names,still_present=present,guard_before=before,guard_after=guard(),isolated_pg_still_running=True,other_schemas_touched=False,production_modified=False)))
"""
command='sudo -n python3 -c '+shlex.quote('import base64;exec(base64.b64decode('+repr(base64.b64encode(remote.encode()).decode())+'))')
r=subprocess.run(['ssh','-i',r'C:\Users\SHENGJIAHAO\.ssh\gpt-deploy-release.pem','-o','BatchMode=yes','-o','StrictHostKeyChecking=yes','-o','ConnectTimeout=15','ubuntu@43.172.70.182',command],stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,encoding='utf-8',creationflags=subprocess.CREATE_NO_WINDOW|subprocess.BELOW_NORMAL_PRIORITY_CLASS,timeout=40)
(out/'stdout.original.json').write_text(r.stdout);(out/'stderr.original.log').write_text(r.stderr);assert r.returncode==0;result=json.loads(r.stdout);assert result['still_present']==[];print(json.dumps(result))
