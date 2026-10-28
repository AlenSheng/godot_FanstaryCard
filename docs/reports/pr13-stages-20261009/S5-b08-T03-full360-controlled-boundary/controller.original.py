"""Tencent-only controlled Room.PlayCards study; immutable originals, explicit G receipts."""
import argparse,fcntl,gzip,hashlib,io,itertools,json,os,shutil,subprocess,sys,tarfile,time,urllib.request
from pathlib import Path
BASE=Path('/home/ubuntu/pr13-acceptance-20261009')
ATTEMPT='T03-conditioned-full-r2-20261012'; E=BASE/'evidence'/ATTEMPT; W=BASE/'work'/ATTEMPT
PILOT='T03-conditioned-pilot-r1-20261012'; PE=BASE/'evidence'/PILOT; PW=BASE/'work'/PILOT
SOURCE='3d08df3638f01f033bba5ff3835a8ba8913df34e'
IMAGE='sha256:180f524270f6ac28d2fe0ff29707fb392387d7b766f731e41fda1e45e8230520'
MONITOR='2734235cbfa1f9d8f1352cd9a925251f6356021d86ede341f80c6196e799149a'
RUNTIME=PW/'artifacts/bin/T03ConditionedRoomBoundary/release'
PREFIX='pr13-cap-t03-conditioned-full-r2-'
BUDGET=256*1024**2; MEMORY=1024*1024**2

def require(v,msg):
 if not v:raise ValueError(msg)
def sha(p):
 h=hashlib.sha256()
 with Path(p).open('rb') as f:
  for b in iter(lambda:f.read(1024**2),b''):h.update(b)
 return h.hexdigest()
def read(p):return json.loads(Path(p).read_bytes())
def write(p,v):
 p=Path(p);require(not p.exists(),'Immutable file exists: '+str(p));p.write_bytes((json.dumps(v,indent=2)+'\n').encode())
def run(args,timeout=40,check=True):
 r=subprocess.run([str(x) for x in args],capture_output=True,timeout=timeout)
 if check:r.check_returncode()
 return r
def docker(*a,**kw):return run(['docker',*a],**kw)
def matrix():
 return [{'unit':f'{h}-{g}-{e}-L{l}-B{b}','hero':h,'group':g,'element':e,'level':l,'block':b,'samples':1000,'witnesses':8000} for b,h,g,e,l in itertools.product(range(3),('Mage','Priest','Guardian'),('O1','O6','E1','BOSS'),('Fire','Wood','Earth','Metal','Water'),(0,5))]
def spec(name):
 rows=[r for r in matrix() if r['unit']==name];require(len(rows)==1,'Unknown frozen unit');return rows[0]
def paths(name):spec(name);return E/'units'/name,W/name
def owner(name):spec(name);return PREFIX+name.lower()
def state(name):
 return dict(x.split('=',1) for x in run(['systemctl','show',owner(name),'--property=MainPID,ActiveState,ExecMainStatus,LoadState,InvocationID']).stdout.decode().splitlines())
def terminal(name):
 v=state(name);require(v['MainPID']=='0' and v['ActiveState']=='inactive' and v['ExecMainStatus']=='0' and v['LoadState']=='loaded','Exact successful terminal unit required');return v
def files(root):
 root=Path(root);require(root.resolve()==root and not root.is_symlink(),'Root symlink or path mismatch')
 result=[]
 for p in sorted(root.rglob('*')):
  require(not p.is_symlink(),'Unexpected symlink')
  if p.is_file():result.append(p)
  else:require(p.is_dir(),'Unexpected special file')
 return result
def guard(output=None,start=False):
 available=int(next(l.split()[1] for l in Path('/proc/meminfo').read_text().splitlines() if l.startswith('MemAvailable:')))*1024;s=os.statvfs(BASE);free=s.f_bavail*s.f_frsize;headroom=(s.f_bavail-.15*s.f_blocks)*s.f_frsize
 require(available>=500000000+(MEMORY+64*1024**2 if start else 0),'Memory resource hold')
 require(headroom>=16*1024**2+(BUDGET if start else 0),'Disk resource hold')
 used=sum(p.stat().st_size for p in files(output)) if output and output.exists() else 0;require(used<=BUDGET,'Output budget exceeded; originals retained')
 with urllib.request.urlopen('http://127.0.0.1:8080/health/ready',timeout=10) as h:require(h.status==200,'Health check failed')
 return {'at':time.time(),'available_memory_bytes':available,'root_free_bytes':free,'root_free_fraction':s.f_bavail/s.f_blocks,'output_bytes':used,'health_status':200}
def frozen(packages=False):
 p=read(E/'plan.original.json');require(p['units']==matrix() and p['source_sha']==SOURCE and p['full_expected_witnesses']==2880000,'Frozen plan changed');require(sha(E/'controller.original.py')==p['controller_sha256'] and sha(E/'validator.original.py')==p['validator_sha256'],'Runner changed')
 require(sha(PE/'inputs.original.json')==p['pilot_inputs_sha256'] and sha(PE/'independent-validator.original.py')==p['independent_validator_sha256'],'Pilot provenance or independent validator changed');meta=read(PE/'inputs.original.json')
 for row in meta['input_files']:
  f=Path(meta['source'])/row['path'];require(not f.is_symlink() and f.stat().st_size==row['bytes'] and sha(f)==row['sha256'],'Business source changed')
 if packages:
  for row in meta['package_files']:
   f=Path(meta['package_root'])/row['path'];require(not f.is_symlink() and f.stat().st_size==row['bytes'] and sha(f)==row['sha256'],'Package changed')
 for row in p['runtime_files']:
  f=RUNTIME/row['path'];require(not f.is_symlink() and f.stat().st_size==row['bytes'] and sha(f)==row['sha256'],'Compiled runtime changed')
 repo=Path('/opt/fantasycard-github');require(not run(['git','-c','safe.directory='+str(repo),'-C',repo,'diff','--name-only',SOURCE,'HEAD','--','server','protocol']).stdout.strip(),'Current release business code differs')
 return p
def initialize():
 require(not W.exists() and not (E/'plan.original.json').exists(),'Never reinitialize existing study')
 pilot=read(PE/'result.original.json');require(pilot['ok'] and pilot['owned_container_removed'] and pilot['source_and_packages_unchanged'],'Actual pilot required');terminal_pilot=dict(x.split('=',1) for x in run(['systemctl','show','pr13-cap-'+PILOT,'--property=MainPID,ActiveState,ExecMainStatus']).stdout.decode().splitlines());require(terminal_pilot['MainPID']=='0' and terminal_pilot['ActiveState']=='inactive' and terminal_pilot['ExecMainStatus']=='0','Pilot live or failed')
 v=read(PE/'independent-validation.original.json');require(v['ok'] and v['actual_witnesses']==2880,'Independent cloud pilot validation required')
 prereg=read(PE/'preregistration.original.json');require(prereg['full_units']==360 and prereg['full_expected_witnesses']==2880000,'Original full quota changed')
 runtime=[{'path':p.relative_to(RUNTIME).as_posix(),'bytes':p.stat().st_size,'sha256':sha(p)} for p in files(RUNTIME)];require(len(runtime)==7,'Exact seven compiled pilot artifacts required')
 guard(start=True);W.mkdir();(E/'units').mkdir();plan={'attempt':ATTEMPT,'source_sha':SOURCE,'SDK_image':IMAGE,'units':matrix(),'full_expected_witnesses':2880000,'witnesses_per_unit':8000,'runtime_files':runtime,'runtime_directory':str(RUNTIME),'controller_sha256':sha(E/'controller.original.py'),'validator_sha256':sha(E/'validator.original.py'),'independent_validator_sha256':sha(PE/'independent-validator.original.py'),'pilot_inputs_sha256':sha(PE/'inputs.original.json'),'pilot_result_sha256':sha(PE/'result.original.json'),'pilot_validation_sha256':sha(PE/'independent-validation.original.json'),'preregistration_sha256':sha(PE/'preregistration.original.json'),'native_deadline_seconds':1200,'validation_deadline_seconds':1200,'owned_unit_deadline_seconds':2700,'output_budget_bytes':BUDGET,'memory_floor_bytes':500000000,'disk_free_floor_fraction':.15,'native_only_Tencent':True,'original720000_and314_gaps_unchanged':True,'candidate_activation':False,'formal_EXPERIMENT_accepted':False,'MAIN_accepted':False};write(E/'plan.original.json',plan);frozen(True);return {'ok':True,'plan':plan,'guard':guard()}
def status():
 completed=0;current=None;next_pending=None
 for s in matrix():
  m,o=paths(s['unit'])
  if not m.exists():next_pending=s;break
  if (m/'cleanup.original.json').exists():
   r=read(m/'cleanup.original.json');require(r['ok'] and r['unit']==s['unit'] and not o.exists(),'Cleanup marker differs');completed+=1;continue
  require(current is None,'More than one pending unit');current={'spec':s,'state':state(s['unit']),'result':read(m/'result.original.json') if (m/'result.original.json').exists() else None,'delivery_ready':(m/'delivery-manifest.original.json').exists()};break
 return {'ok':True,'completed_G_verified_units':completed,'completed_G_verified_witnesses':completed*8000,'current':current,'next_pending':next_pending,'required_units':360,'required_witnesses':2880000,'formal_EXPERIMENT_accepted':False,'MAIN_accepted':False}
def launch():
 with (BASE/'evidence/shared-resource-coordination.lock').open('a') as lock:
  fcntl.flock(lock,fcntl.LOCK_EX);st=status();require(st['current'] is None and st['next_pending'] is not None,'Inspect existing handle; never duplicate or skip')
  live=run(['systemctl','list-units','--state=running','--no-legend','pr13-cap-*','pr13-pool-segment-*']).stdout.decode().strip();active=[n for n in docker('ps','--format','{{.Names}}').stdout.decode().splitlines() if n.startswith(('pr13-cap-','pr13-pool-segment-'))]
  if live or active:return {'ok':True,'resource_deferred':True,'live_units':live,'live_containers':active}
  try:observation=guard(start=True)
  except ValueError as e:return {'ok':True,'resource_deferred':True,'reason':str(e)}
  frozen();s=st['next_pending'];name=s['unit'];m,o=paths(name);require(not m.exists() and not o.exists(),'Owned paths already exist');m.mkdir();write(m/'preregistration.original.json',{'spec':s,'source_sha':SOURCE,'plan_sha256':sha(E/'plan.original.json'),'guard':observation,'owner':owner(name),'no_automatic_retry':True});unit=Path('/etc/systemd/system')/(owner(name)+'.service');require(not unit.exists(),'Unit already exists');unit.write_text('[Unit]\nDescription=PR13 full controlled Room.PlayCards boundary unit\n[Service]\nType=exec\nUser=root\nWorkingDirectory=/opt/fantasycard-github\nExecStart=/usr/bin/python3 '+str(E/'controller.original.py')+' run '+name+'\nRuntimeMaxSec=2700\nRestart=no\n')
  write(m/'dispatch-intent.original.json',{'owner':owner(name),'unit_file':str(unit),'unit_file_sha256':sha(unit),'spec':s,'no_automatic_retry':True});run(['systemctl','daemon-reload']);r=run(['systemctl','start','--no-block',owner(name)],check=False);write(m/'dispatch-result.original.json',{'exit_code':r.returncode,'stdout':r.stdout.decode(),'stderr':r.stderr.decode()});require(r.returncode==0,'Dispatch error requires same-handle inspection');return {'ok':True,'started':True,'spec':s,'owner':owner(name)}
def run_unit(name):
 s=spec(name);m,o=paths(name);require(read(m/'preregistration.original.json')['spec']==s,'Frozen unit changed');frozen();require(not o.exists(),'Never rerun original unit');v=state(name);require(v['MainPID']==str(os.getpid()) and v['ActiveState']=='active','Actual owned systemd PID required');write(m/'started.original.json',{'PID':os.getpid(),'state':v,'boot_id':Path('/proc/sys/kernel/random/boot_id').read_text().strip(),'at':time.time(),'guard':guard(start=True)});o.mkdir(mode=0o777);o.chmod(0o777);cid=None;result={'ok':False,'source_sha':SOURCE,'unit':name,'spec':s,'candidate_activation':False,'formal_EXPERIMENT_accepted':False,'MAIN_accepted':False}
 def owned():
  v=json.loads(docker('inspect',cid).stdout)[0];require(v['Id']==cid and v['Name']=='/'+owner(name) and v['Config']['Labels'].get('codex.owner')==owner(name),'Exact container owner differs');return v
 try:
  require(docker('inspect',owner(name),check=False).returncode!=0,'Container already exists')
  commands=[['dotnet','/runtime/T03ConditionedRoomBoundary.dll',SOURCE,'/output/native','1000',str(s['block']),s['hero'],s['group'],s['element'],str(s['level'])],['python3','/validator.py','/output/native','1000',str(s['block']),s['hero'],s['group'],s['element'],str(s['level']),SOURCE]]
  inner="import json,subprocess,sys,time\nfrom pathlib import Path\nc=json.loads(sys.argv[1])\nfor i,a in enumerate(c):\n with open('/output/'+('native' if i==0 else 'validation')+'.original.log','xb') as f:r=subprocess.run(a,stdout=f,stderr=subprocess.STDOUT,timeout=1200)\n if r.returncode:sys.exit(r.returncode)\n"
  cid=docker('create','--name',owner(name),'--label','codex.owner='+owner(name),'--network','none','--memory','1024m','--memory-swap','1024m','--cpus','1','--read-only','--tmpfs','/tmp:rw,nosuid,nodev,size=134217728','--user','1000:1000','-e','HOME=/tmp/home','-e','DOTNET_CLI_HOME=/tmp/dotnet','-e','DOTNET_CLI_TELEMETRY_OPTOUT=1','-v',str(RUNTIME)+':/runtime:ro','-v',str(E/'validator.original.py')+':/validator.py:ro','-v',str(PE/'independent-validator.original.py')+':/independent_validator.py:ro','-v',str(o)+':/output',IMAGE,'env','-u','FANTASYCARD_TEST_POSTGRES','python3','-c',inner,json.dumps(commands)).stdout.decode().strip();owned();write(m/'container-created.original.json',{'Id':cid,'owner':owner(name),'commands':commands,'image':IMAGE});docker('start',cid);deadline=time.monotonic()+2500
  while True:
   info=owned()
   if not info['State']['Running']:break
   require(time.monotonic()<deadline,'Owned unit deadline exceeded');observation=guard(o)
   with (m/'resources.original.jsonl').open('a') as f:f.write(json.dumps(observation)+'\n')
   time.sleep(5)
  log=docker('logs',cid);(o/'container.original.log').write_bytes(log.stdout+log.stderr);summary=read(o/'native/summary.original.json');validation=read(o/'native/independent-validation.original.json');require(summary['passed'] and summary['samples']==1000 and summary['block']==s['block'] and summary['strata']==1 and summary['witnesses']==summary['expected_witnesses']==8000 and summary['source_sha']==SOURCE and not summary['candidate_activation'],'Full native quota not reached');require(validation['ok'] and validation['actual_witnesses']==8000 and validation['exact_stratum']==[s['hero'],s['group'],s['element'],s['level']] and validation['source_sha']==SOURCE,'Full independent validation differs');result.update(ok=info['State']['ExitCode']==0 and not info['State']['OOMKilled'],exit_code=info['State']['ExitCode'],oom_killed=info['State']['OOMKilled'],native_summary=summary,validation=validation)
 except Exception as e:result.update(error=type(e).__name__,detail=str(e),failed_originals_retained=True)
 finally:
  removed=False
  if cid:
   try:
    info=owned()
    if info['State']['Running']:docker('stop','--time','10',cid)
    owned();docker('rm',cid);removed=True
   except Exception as e:result['owned_container_cleanup_error']=str(e)
  result['owned_container_removed']=removed
  try:frozen();result['source_and_runtime_unchanged']=True
  except Exception as e:result.update(source_and_runtime_unchanged=False,source_error=str(e))
  result['ok']=result['ok'] and removed and result['source_and_runtime_unchanged'];write(m/'result.original.json',result)
 return result
def collect(name):
 m,o=paths(name);result=read(m/'result.original.json');require(result['ok'] and result['spec']==spec(name),'Failed originals must remain');st=terminal(name);frozen();rows=[]
 for root,prefix in ((m,'metadata'),(o,'outputs')):
  for p in files(root):
   if root==m and p.name in ('delivery-manifest.original.json','local-G-receipt.original.json','cleanup-intent.original.json','cleanup.original.json'):continue
   rows.append({'path':prefix+'/'+p.relative_to(root).as_posix(),'source':str(p),'bytes':p.stat().st_size,'sha256':sha(p)})
 unit=Path('/etc/systemd/system')/(owner(name)+'.service');rows.append({'path':'systemd/owned-unit.original.service','source':str(unit),'bytes':unit.stat().st_size,'sha256':sha(unit)});require(sum(r['bytes'] for r in rows)<BUDGET,'Archive budget exceeded');return {'ok':True,'attempt':ATTEMPT,'unit':name,'source_sha':SOURCE,'plan_sha256':sha(E/'plan.original.json'),'files':rows,'terminal_state':st,'witnesses':8000,'formal_EXPERIMENT_accepted':False,'MAIN_accepted':False}
def delivery(name):
 m,o=paths(name);p=m/'delivery-manifest.original.json'
 if p.exists():v=read(p);require(collect(name)==v,'Immutable delivery originals changed')
 else:
  terminal(name);journal=run(['journalctl','-u',owner(name),'-o','json','--no-pager']);(m/'terminal-journal.original.jsonl').write_bytes(journal.stdout);v=collect(name);write(p,v)
 return {'ok':True,'manifest_sha256':sha(p),'manifest':v}
def stream(name):
 m,o=paths(name);p=m/'delivery-manifest.original.json';v=read(p);require(collect(name)==v,'Delivery changed');data=p.read_bytes()
 class Sink:
  def __init__(self):self.h=hashlib.sha256();self.n=0
  def write(self,b):n=sys.stdout.buffer.write(b);require(n==len(b),'Partial stream write');self.h.update(b);self.n+=n;return n
  def flush(self):sys.stdout.buffer.flush()
 sink=Sink()
 with gzip.GzipFile(fileobj=sink,mode='wb',mtime=0,compresslevel=1) as gz:
  with tarfile.open(fileobj=gz,mode='w|') as t:
   info=tarfile.TarInfo('complete-original-manifest.json');info.size=len(data);t.addfile(info,io.BytesIO(data))
   for row in v['files']:
    f=Path(row['source']);require(sha(f)==row['sha256'],'Changed streaming input');info=tarfile.TarInfo(row['path']);info.size=row['bytes']
    with f.open('rb') as source:t.addfile(info,source)
 sink.flush();require(collect(name)==v,'Source mutated during stream');sys.stderr.write('ACK '+json.dumps({'bytes':sink.n,'sha256':sink.h.hexdigest(),'manifest_sha256':sha(p),'unit':name})+'\n')
def cleanup(name,receipt):
 m,o=paths(name);manifest=read(m/'delivery-manifest.original.json');require(collect(name)==manifest,'Originals differ before cleanup');terminal(name);r=json.loads(receipt);require(r['ok'] and r['unit']==name and r['attempt']==ATTEMPT and r['all_members_SHA_verified'] and r['gzip_CRC_verified'] and r['manifest_sha256']==sha(m/'delivery-manifest.original.json') and r['members']==len(manifest['files']) and r['native_reexecuted_by_backup'] is False and r['local_directory'].replace('\\','/').startswith('G:/PR13Evidence/T03-conditioned-full-r2/'),'Exact complete G receipt required');require(o.resolve()==o and o.parent==W and not o.is_symlink(),'Wrong cleanup target')
 ids=docker('ps','-q').stdout.decode().split()
 if ids:
  for c in json.loads(docker('inspect',*ids).stdout):
   for bind in c.get('Mounts',[]):
    if bind.get('Type')!='bind':continue
    p=Path(bind['Source']).resolve()
    if c['Id']==MONITOR and p==Path('/') and bind.get('RW') is False:continue
    require(not (p==o or p.is_relative_to(o) or o.is_relative_to(p)),'Active bind overlaps cleanup target')
 guard();write(m/'local-G-receipt.original.json',r);write(m/'cleanup-intent.original.json',{'unit':name,'output_directory':str(o),'receipt_sha256':sha(m/'local-G-receipt.original.json'),'archive_sha256':r['archive_sha256'],'manifest_sha256':r['manifest_sha256']});allocated=sum(p.stat().st_blocks*512 for p in files(o));shutil.rmtree(o);v={'ok':True,'unit':name,'archive_sha256':r['archive_sha256'],'manifest_sha256':r['manifest_sha256'],'allocated_bytes_removed':allocated,'source_runtime_packages_and_metadata_retained':True,'originals_G_complete':True,'formal_EXPERIMENT_accepted':False,'MAIN_accepted':False};write(m/'cleanup.original.json',v);return v
def final_verify():
 p=frozen(True);st=status();require(st['completed_G_verified_units']==360 and st['current'] is None,'Full original quota incomplete');return {'ok':True,'source_sha':SOURCE,'completed_units':360,'completed_witnesses':2880000,'source_runtime_packages_unchanged':True,'plan_sha256':sha(E/'plan.original.json'),'formal_EXPERIMENT_accepted':False,'MAIN_accepted':False}
def main():
 require(os.geteuid()==0 and Path('/proc/meminfo').exists(),'Tencent root controller only');a=sys.argv[1:];command=a[0]
 if command=='stream':stream(a[1]);return
 actions={'init':initialize,'status':status,'launch':launch,'final':final_verify}
 if command in actions:v=actions[command]()
 elif command=='run':v=run_unit(a[1])
 elif command=='delivery':v=delivery(a[1])
 elif command=='cleanup':v=cleanup(a[1],a[2])
 else:raise ValueError('Unknown action')
 print(json.dumps(v));require(v['ok'],'Actual action failed')
if __name__=='__main__':main()
