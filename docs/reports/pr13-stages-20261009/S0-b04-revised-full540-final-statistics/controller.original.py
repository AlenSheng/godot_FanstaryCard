"""Tencent statistics only after the complete human-revised 540-part matrix."""
import fcntl,hashlib,json,os,subprocess,sys,time,urllib.request
from pathlib import Path
B=Path('/home/ubuntu/pr13-acceptance-20261009')
E=B/'evidence/B04-reduced-final-statistics-r1-20261014'
INPUT=B/'evidence/B04-reduced-final-original-inputs-r1-20261014'
STUDY=B/'evidence/B04-single-factor-reduced-r1-20261014'
OWNER='pr13-cap-b04-reduced-final-statistics-r1'
IMAGE='sha256:180f524270f6ac28d2fe0ff29707fb392387d7b766f731e41fda1e45e8230520'
def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for d in iter(lambda:f.read(1024**2),b''):h.update(d)
 return h.hexdigest()
def read(p):return json.loads(p.read_bytes())
def write(p,v):
 assert not p.exists();p.write_bytes((json.dumps(v,indent=2)+'\n').encode())
def run(a,check=True):return subprocess.run(a,capture_output=True,check=check,timeout=45)
def state():return dict(l.split('=',1) for l in run(['systemctl','show',OWNER,'--property=MainPID,ActiveState,ExecMainStatus,InvocationID']).stdout.decode().splitlines())
def guard(start=False):
 mem=int(next(l.split()[1] for l in Path('/proc/meminfo').read_text().splitlines() if l.startswith('MemAvailable:')))*1024
 disk=os.statvfs('/');assert mem>=500000000+(896*1024**2 if start else 0)
 assert disk.f_bavail*disk.f_frsize>=.15*disk.f_blocks*disk.f_frsize+(32*1024**2 if start else 0)
 with urllib.request.urlopen('http://127.0.0.1:8080/health/ready',timeout=10) as r:assert r.status==200
 return {'memory_available_bytes':mem,'root_free_bytes':disk.f_bavail*disk.f_frsize,'health_status':200}
def frozen():
 plan=read(E/'analysis-plan.original.json')
 for row in plan['control_files']:
  p=E/row['path'];assert p.is_file() and not p.is_symlink() and p.stat().st_size==row['bytes'] and sha(p)==row['sha256']
 study=read(E/'study-plan.original.json');assert len(study['units'])==540 and study['expected_encounters']==21600 and study['required_paired_seeds_per_stratum']==300
 assert sha(E/'config-reference.original.json')==study['config_reference_sha256']
 return plan,study
def complete_inputs():
 plan,study=frozen()
 status=json.loads(run(['python3',str(STUDY/'controller.original.py'),'status']).stdout)
 assert status['completed_G_verified_parts']==540 and status['current'] is None,'Revised 540 native and G closures required'
 assert INPUT.is_dir() and not INPUT.is_symlink()
 ledger=read(E/'recovery-input-ledger.original.json');index=read(E/'parts-index.original.json')
 assert ledger['ok'] and ledger['formal_original_parts']==540 and ledger['formal_original_encounters']==21600
 assert ledger['all540_original_archive_SHA_and_CRC_rechecked'] and len(ledger['files'])==2700 and len(index['parts'])==540
 expected={u['unit'] for u in study['units']};assert {p['unit'] for p in index['parts']}==expected
 for row in ledger['files']:
  p=Path(row['remote_path']);assert p.is_relative_to(INPUT/'units') and p.is_file() and not p.is_symlink()
  assert p.stat().st_size==row['bytes'] and sha(p)==row['sha256']
 for part in index['parts']:assert Path(part['directory'])==INPUT/'units'/part['unit']
 # Container path relocation changes metadata paths only; preserve the original index separately.
 mapped={'parts':[{**p,'directory':'/inputs/units/'+p['unit']} for p in index['parts']],
         'original_cloud_index_sha256':sha(E/'parts-index.original.json'),'path_relocation_only':True,'native_resimulation':False}
 p=E/'container-parts-index.original.json'
 if p.exists():assert read(p)==mapped
 else:write(p,mapped)
 return plan,study
def launch():
 with (B/'evidence/shared-resource-coordination.lock').open('a') as lock:
  fcntl.flock(lock,fcntl.LOCK_EX)
  assert not (E/'dispatch.original.json').exists(),'Inspect existing exact handle; no dispatch retry'
  busy=run(['systemctl','list-units','--state=running','--no-legend','pr13-cap-*','pr13-pool-segment-*']).stdout.strip()
  if busy:return {'ok':True,'resource_deferred':True,'reason':'Existing native job running'}
  complete_inputs();sample=guard(True)
  unit=Path('/etc/systemd/system')/(OWNER+'.service');assert not unit.exists()
  unit.write_text('[Unit]\nDescription=Full human-revised B04 paired statistics on Tencent\n[Service]\nType=exec\nUser=root\nExecStart=/usr/bin/python3 '+str(E/'controller.original.py')+' run\nRuntimeMaxSec=3700\nRestart=no\n')
  write(E/'dispatch-intent.original.json',{'owner':OWNER,'guard':sample,'unit_sha256':sha(unit),'required_parts':540,'required_encounters':21600,'automatic_native_retry':False})
  run(['systemctl','daemon-reload']);result=run(['systemctl','start','--no-block',OWNER],False)
  write(E/'dispatch.original.json',{'owner':OWNER,'exit_code':result.returncode});assert result.returncode==0
  return {'ok':True,'started':True,'owner':OWNER,'state':state()}
def execute():
 actual=state();assert actual['MainPID']==str(os.getpid()) and actual['ActiveState']=='active'
 plan,study=complete_inputs();sample=guard(True)
 output=E/'persistent-output';assert not output.exists();output.mkdir(mode=0o777);output.chmod(0o777)
 write(E/'started.original.json',{'pid':os.getpid(),'state':actual,'guard':sample,'required_parts':540,'required_encounters':21600})
 args=['python3','/control/statistics.original.py','--parts-index','/control/container-parts-index.original.json',
       '--plan','/control/study-plan.original.json','--config-reference','/control/config-reference.original.json','--output','/output/native']
 cid=None;result={'ok':False,'owner':OWNER,'required_parts':540,'required_encounters':21600,'MAIN_accepted':False}
 def owned():
  c=json.loads(run(['docker','inspect',cid]).stdout)[0];assert c['Id']==cid and c['Name']=='/'+OWNER and c['Config']['Labels']['codex.owner']==OWNER
  return c
 try:
  cid=run(['docker','create','--name',OWNER,'--label','codex.owner='+OWNER,'--network','none',
    '--memory','896m','--memory-swap','896m','--cpus','1','--read-only','--user','1000:1000',
    '--tmpfs','/tmp:rw,nosuid,nodev,size=67108864','-e','PYTHONPATH=/control','-e','HOME=/tmp/home',
    '-v',str(INPUT)+':/inputs:ro','-v',str(E)+':/control:ro','-v',str(output)+':/output',IMAGE,*args]).stdout.decode().strip()
  owned();run(['docker','start',cid]);deadline=time.monotonic()+3600
  while True:
   c=owned()
   if not c['State']['Running']:break
   assert time.monotonic()<deadline,'Statistics deadline; retain original partial output'
   sample=guard();assert sum(p.stat().st_size for p in output.rglob('*') if p.is_file())<=32*1024**2
   with (E/'resources.original.jsonl').open('a') as f:f.write(json.dumps(sample)+'\n')
   time.sleep(5)
  logs=run(['docker','logs',cid]);(E/'native.stdout.original.log').write_bytes(logs.stdout);(E/'native.stderr.original.log').write_bytes(logs.stderr)
  p=output/'native/final-statistics.original.json';stats=read(p) if p.exists() else {}
  result.update(exit_code=c['State']['ExitCode'],oom_killed=c['State']['OOMKilled'],actual_statistics_report_sha256=sha(p) if p.exists() else None)
  assert c['State']['ExitCode']==0 and not c['State']['OOMKilled'] and stats.get('ok')
  assert stats['original_parts']==540 and stats['original_encounters']==21600 and len(stats['levels'])==36
  assert all(l['actual_paired_seeds']==300 and l['independent_blocks']==3 for l in stats['levels'])
  complete_inputs();result.update(ok=True,statistics_computed_on_Tencent=True,local_statistics_computed=False,production_activation=False,full_case_specific_review_pending=True)
 except Exception as error:result.update(error=type(error).__name__,detail=str(error),original_failure_retained=True)
 finally:
  if cid:
   c=owned()
   if c['State']['Running']:run(['docker','stop','--time','10',cid])
   owned();run(['docker','rm',cid]);result['owned_container_removed']=True
  write(E/'result.original.json',result)
 assert result['ok'],'Original statistics failure retained'
if __name__=='__main__':
 if sys.argv[1]=='launch':print(json.dumps(launch()))
 elif sys.argv[1]=='run':execute()
 else:raise ValueError('Unknown action')
