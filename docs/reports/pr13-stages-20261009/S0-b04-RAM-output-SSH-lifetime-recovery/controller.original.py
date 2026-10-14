"""Tencent-only full one-card study; original 21600 outcomes and G custody."""
import fcntl,gzip,hashlib,io,itertools,json,os,shutil,subprocess,sys,tarfile,time,urllib.request
from pathlib import Path
from functools import cache
BASE=Path('/home/ubuntu/pr13-acceptance-20261009');A='B04-single-factor-reduced-ram-r3-20261014';E=BASE/'evidence'/A;W=Path('/run/pr13-b04-reduced540-output-r3');PREFIX='pr13-cap-b04-single-factor-reduced-ram-r3-';MEMORY=1024*1024**2;BUDGET=256*1024**2;IMAGE='sha256:180f524270f6ac28d2fe0ff29707fb392387d7b766f731e41fda1e45e8230520';MONITOR='2734235cbfa1f9d8f1352cd9a925251f6356021d86ede341f80c6196e799149a'
def require(ok,msg):
 if not ok:raise ValueError(msg)
def read(p):return json.loads(Path(p).read_bytes())
def write(p,v):
 p=Path(p);require(not p.exists(),'Immutable original already exists');p.write_bytes((json.dumps(v,indent=2)+'\n').encode())
def sha(p):
 h=hashlib.sha256()
 with Path(p).open('rb') as f:
  for b in iter(lambda:f.read(1024**2),b''):h.update(b)
 return h.hexdigest()
def run(a,timeout=40,check=True):
 r=subprocess.run([str(x) for x in a],capture_output=True,timeout=timeout)
 if check:r.check_returncode()
 return r
def docker(*a,**kw):return run(['docker',*a],**kw)
@cache
def matrix():return [{'unit':f'{h}-{g}-{t}-B{b}-P{o:04}','hero':h,'group':g,'strategy':t,'block':b,'offset':o,'samples':20,'encounters':40} for b,h,g,t,o in itertools.product(range(3),['Mage','Priest','Guardian'],['O1','O6','E1','BOSS'],['baseline_all_hand','basic','build'],range(0,100,20))]
@cache
def spec_index():return {r['unit']:r for r in matrix()}
def spec(name):
 require(name in spec_index(),'Unknown immutable full unit');return spec_index()[name]
def paths(name):spec(name);return E/'units'/name,W/name
def owner(name):spec(name);return PREFIX+name.lower().replace('_','-')
def state(name):return dict(l.split('=',1) for l in run(['systemctl','show',owner(name),'--property=MainPID,ActiveState,ExecMainStatus,LoadState,InvocationID']).stdout.decode().splitlines())
def terminal(name):
 s=state(name);require(s['MainPID']=='0' and s['ActiveState']=='inactive' and s['ExecMainStatus']=='0' and s['LoadState']=='loaded','Original successful terminal handle required');return s
def files(root):
 root=Path(root);require(root.resolve()==root and not root.is_symlink(),'Nonordinary root');out=[]
 for p in sorted(root.rglob('*')):
  require(not p.is_symlink(),'Unexpected source link')
  if p.is_file():out.append(p)
  else:require(p.is_dir(),'Unexpected special file')
 return out
def guard(output=None,start=False):
 require(run(['findmnt','-n','-o','FSTYPE','-T','/run']).stdout.strip()==b'tmpfs','Actual output filesystem must be RAM tmpfs');ram=os.statvfs('/run');require(ram.f_bavail*ram.f_frsize>=BUDGET if start else True,'RAM output space admission hold')
 s=os.statvfs('/');m=int(next(l.split()[1] for l in Path('/proc/meminfo').read_text().splitlines() if l.startswith('MemAvailable:')))*1024;headroom=(s.f_bavail-.15*s.f_blocks)*s.f_frsize;require(m>=500000000+(MEMORY+BUDGET+64*1024**2 if start else 0),'Memory admission hold');require(headroom>=16*1024**2,'Disk admission hold');used=sum(p.stat().st_size for p in files(output)) if output and output.exists() else 0;require(used<=BUDGET,'Frozen part output budget exceeded; originals retained')
 with urllib.request.urlopen('http://127.0.0.1:8080/health/ready',timeout=10) as h:require(h.status==200,'Actual health check failed')
 return {'at':time.time(),'memory_available_bytes':m,'root_free_bytes':s.f_bavail*s.f_frsize,'root_free_fraction':s.f_bavail/s.f_blocks,'owned_output_bytes':used,'health_status':200}
def frozen():
 p=read(E/'plan.original.json');require(p['units']==matrix() and p['expected_encounters']==21600 and p['required_paired_seeds_per_stratum']==300,'Full quota or matrix changed');require(sha(E/'controller.original.py')==p['controller_sha256'] and sha(E/'validator.original.py')==p['validator_sha256'] and sha(E/'config-reference.original.json')==p['config_reference_sha256'],'Controller, oracle or actual configuration changed');rt=Path(p['runtime_root'])
 for r in p['runtime_files']:require((rt/r['path']).stat().st_size==r['bytes'] and sha(rt/r['path'])==r['sha256'],'Exact compiled collector changed')
 require(not run(['git','-c','safe.directory=/opt/fantasycard-github','-C','/opt/fantasycard-github','diff','--name-only',p['compiled_source_sha'],p['source_sha'],'--','server','protocol']).stdout.strip(),'Current production source differs from proven Domain runtime');return p
def initialize():
 p=frozen();require(len(matrix())==540,'Full physical count differs');(E/'units').mkdir();write(E/'initialized.original.json',{'ok':True,'physical_parts':540,'expected_encounters':21600,'source_sha':p['source_sha'],'wait_for_T03_full360_before_first_native':True,'MAIN_accepted':False});return {'ok':True,'plan':p}
def status():
 done=0;current=None;next_pending=None
 for s in matrix():
  m,o=paths(s['unit'])
  if not m.exists():next_pending=s;break
  if (m/'adopted-original-G-closure.original.json').exists():
   a=read(m/'adopted-original-G-closure.original.json');require(a['ok'] and a['unit']==s['unit'] and not o.exists(),'Adopted original closure differs');done+=1;continue
  if (m/'cleanup.original.json').exists():require(read(m/'cleanup.original.json')['ok'] and not o.exists(),'Cleanup marker differs');done+=1;continue
  current={'spec':s,'state':state(s['unit']),'result':read(m/'result.original.json') if (m/'result.original.json').exists() else None};break
 return {'ok':True,'completed_G_verified_parts':done,'completed_G_verified_encounters':done*40,'current':current,'next_pending':next_pending,'required_parts':540,'required_encounters':21600,'formal_profiles_accepted':False,'MAIN_accepted':False}
def launch():
 with (BASE/'evidence/shared-resource-coordination.lock').open('a') as lock:
  fcntl.flock(lock,fcntl.LOCK_EX);st=status();require(st['current'] is None and st['next_pending'] is not None,'Inspect existing handle; never duplicate')
  other=read_json_command(['python3',BASE/'evidence/T03-conditioned-full-r2-20261012/controller.original.py','status'])
  if other['completed_G_verified_units']<360:return {'ok':True,'resource_deferred':True,'reason':'T03 original full360 priority','T03_G_units':other['completed_G_verified_units']}
  busy=run(['systemctl','list-units','--state=running','--no-legend','pr13-cap-*','pr13-pool-segment-*']).stdout.strip();active=docker('ps','--format','{{.Names}}').stdout.decode().splitlines()
  if busy or any(n.startswith(('pr13-cap-','pr13-pool-segment-')) for n in active):return {'ok':True,'resource_deferred':True,'reason':'Existing real native handle still running'}
  try:g=guard(start=True)
  except ValueError as error:return {'ok':True,'resource_deferred':True,'reason':str(error)}
  p=frozen();s=st['next_pending'];m,o=paths(s['unit']);require(not m.exists() and not o.exists(),'Owned original path exists');m.mkdir();write(m/'preregistration.original.json',{'spec':s,'plan_sha256':sha(E/'plan.original.json'),'guard':g,'source_sha':p['source_sha']});unit=Path('/etc/systemd/system')/(owner(s['unit'])+'.service');require(not unit.exists(),'Original unit handle already exists');unit.write_text('[Unit]\nDescription=Owned B04 full one-card physical part\n[Service]\nType=exec\nUser=root\nExecStart=/usr/bin/python3 '+str(E/'controller.original.py')+' run '+s['unit']+'\nRuntimeMaxSec=1800\nRestart=no\n');run(['systemctl','daemon-reload']);r=run(['systemctl','start','--no-block',owner(s['unit'])],check=False);write(m/'dispatch.original.json',{'exit_code':r.returncode,'owner':owner(s['unit']),'spec':s,'dispatched_once':True});require(r.returncode==0,'Original dispatch failed');return {'ok':True,'started':True,'spec':s,'owner':owner(s['unit'])}
def read_json_command(a):return json.loads(run(a).stdout)
def run_unit(name):
 p=frozen();s=spec(name);m,o=paths(name);st=state(name);require(st['MainPID']==str(os.getpid()) and st['ActiveState']=='active','Not original live handle');o.mkdir(mode=0o777);o.chmod(0o777);write(m/'started.original.json',{'spec':s,'PID':os.getpid(),'state':st,'guard':guard(start=True)});cid=None;result={'ok':False,'source_sha':p['source_sha'],'spec':s,'MAIN_accepted':False}
 def owned():
  v=json.loads(docker('inspect',cid).stdout)[0];require(v['Id']==cid and v['Name']=='/'+owner(name) and v['Config']['Labels']['codex.owner']==owner(name),'Foreign native container');return v
 try:
  args=['dotnet','/runtime/B04SingleFactor.dll','--source-sha',p['source_sha'],'--hero',s['hero'],'--group',s['group'],'--strategy',s['strategy'],'--block',str(s['block']),'--offset',str(s['offset']),'--samples','20','--output','/output/native'];code="import json,subprocess,sys\nfrom pathlib import Path\na=json.loads(sys.argv[1]);r=subprocess.run(a,stdout=Path('/output/native.original.log').open('xb'),stderr=subprocess.STDOUT,timeout=900);assert r.returncode==0\nr=subprocess.run(['python3','/validator.py','/output/native','--reference','/config-reference.json',a[a.index('--source-sha')+1]],stdout=Path('/output/validation.original.log').open('xb'),stderr=subprocess.STDOUT,timeout=600);assert r.returncode==0\n"
  cid=docker('create','--name',owner(name),'--label','codex.owner='+owner(name),'--network','none','--memory','1024m','--memory-swap','1024m','--cpus','1','--read-only','--tmpfs','/tmp:rw,nosuid,nodev,size=134217728','--user','1000:1000','-e','HOME=/tmp/home','-e','DOTNET_CLI_HOME=/tmp/dotnet','-v',p['runtime_root']+':/runtime:ro','-v',str(E/'validator.original.py')+':/validator.py:ro','-v',str(E/'config-reference.original.json')+':/config-reference.json:ro','-v',str(o)+':/output',IMAGE,'python3','-c',code,json.dumps(args)).stdout.decode().strip();owned();docker('start',cid);until=time.monotonic()+1530
  while True:
   info=owned()
   if not info['State']['Running']:break
   require(time.monotonic()<until,'Original part deadline');g=guard(o)
   with (m/'resources.original.jsonl').open('a') as f:f.write(json.dumps(g)+'\n')
   time.sleep(3)
  logs=docker('logs',cid);(o/'container.original.log').write_bytes(logs.stdout+logs.stderr);validation=read(o/'native/independent-part-validation.original.json') if (o/'native/independent-part-validation.original.json').exists() else {};result.update(ok=info['State']['ExitCode']==0 and not info['State']['OOMKilled'] and validation.get('ok') is True,exit_code=info['State']['ExitCode'],oom_killed=info['State']['OOMKilled'],validation=validation);require(validation.get('samples')==20 and validation.get('encounters')==40,'Full physical part count differs')
 except Exception as error:result.update(error=type(error).__name__,detail=str(error),failed_originals_retained=True)
 finally:
  removed=False
  if cid:
   try:
    info=owned()
    if info['State']['Running']:docker('stop','--time','10',cid)
    owned();docker('rm',cid);removed=True
   except Exception as error:result['cleanup_error']=str(error)
  result['owned_container_removed']=removed
  try:frozen();result['runtime_and_controller_unchanged']=True
  except Exception:result['runtime_and_controller_unchanged']=False
  result['ok']=result['ok'] and removed and result['runtime_and_controller_unchanged'];write(m/'result.original.json',result)
 return result
def collect(name):
 m,o=paths(name);terminal(name);r=read(m/'result.original.json');require(r['ok'] and r['owned_container_removed'] and r['runtime_and_controller_unchanged'],'Native part not passed');rows=[]
 for root,prefix in [(m,'metadata'),(o,'outputs')]:
  for p in files(root):
   if p.name=='delivery-manifest.original.json':continue
   rows.append({'source':str(p),'path':prefix+'/'+p.relative_to(root).as_posix(),'bytes':p.stat().st_size,'sha256':sha(p)})
 return {'ok':True,'attempt':A,'unit':name,'encounters':40,'files':rows,'MAIN_accepted':False}
def delivery(name):
 m,o=paths(name);p=m/'delivery-manifest.original.json'
 if not p.exists():terminal(name);(m/'terminal-journal.original.jsonl').write_bytes(run(['journalctl','-u',owner(name),'-o','json','--no-pager']).stdout);write(p,collect(name))
 v=read(p);require(collect(name)==v,'Original delivery changed');return {'ok':True,'manifest_sha256':sha(p),'manifest':v}
def stream(name):
 m,o=paths(name);p=m/'delivery-manifest.original.json';v=read(p);require(collect(name)==v,'Originals changed before transfer');data=p.read_bytes()
 class Sink:
  def __init__(self):self.h=hashlib.sha256();self.n=0
  def write(self,b):n=sys.stdout.buffer.write(b);require(n==len(b),'Partial stream write');self.h.update(b);self.n+=n;return n
  def flush(self):sys.stdout.buffer.flush()
 sink=Sink()
 with gzip.GzipFile(fileobj=sink,mode='wb',mtime=0,compresslevel=1) as gz:
  with tarfile.open(fileobj=gz,mode='w|') as t:
   i=tarfile.TarInfo('complete-original-manifest.json');i.size=len(data);t.addfile(i,io.BytesIO(data))
   for r in v['files']:
    p=Path(r['source']);require(sha(p)==r['sha256'],'Immutable streaming input changed');i=tarfile.TarInfo(r['path']);i.size=r['bytes']
    with p.open('rb') as f:t.addfile(i,f)
 sink.flush();require(collect(name)==v,'Originals changed during transfer');sys.stderr.write('ACK '+json.dumps({'bytes':sink.n,'sha256':sink.h.hexdigest(),'manifest_sha256':sha(m/'delivery-manifest.original.json')})+'\n')
def cleanup(name,receipt):
 m,o=paths(name);v=read(m/'delivery-manifest.original.json');require(collect(name)==v,'Exact originals differ before cleanup');r=json.loads(receipt);require(r['ok'] and r['attempt']==A and r['unit']==name and r['all_members_SHA_verified'] and r['gzip_CRC_verified'] and r['manifest_sha256']==sha(m/'delivery-manifest.original.json') and r['members']==len(v['files']) and r['native_reexecuted_by_backup'] is False and r['local_directory'].replace('\\','/').startswith('G:/PR13Evidence/B04-single-factor-reduced-r1/'),'Exact original G custody receipt required');require(o.resolve()==o and o.parent==W,'Wrong output cleanup target');ids=docker('ps','-q').stdout.decode().split();cs=json.loads(docker('inspect',*ids).stdout) if ids else []
 for c in cs:
  for b in c['Mounts']:
   if b['Type']!='bind':continue
   p=Path(b['Source']).resolve()
   if c['Id']==MONITOR and p==Path('/') and b['RW'] is False:continue
   require(not (p==o or p.is_relative_to(o) or o.is_relative_to(p)),'Live bind overlaps passed outputs')
 terminal(name);guard();write(m/'local-G-receipt.original.json',r);write(m/'cleanup-intent.original.json',{'target':str(o),'unit':name,'manifest_sha256':r['manifest_sha256']});before=os.statvfs('/');shutil.rmtree(o);after=os.statvfs('/');result={'ok':True,'unit':name,'originals_G_complete':True,'actual_root_bytes_reclaimed':(after.f_bavail-before.f_bavail)*after.f_frsize,'output_was_RAM_tmpfs':True,'manifest_sha256':r['manifest_sha256'],'all_shared_inputs_retained':True,'MAIN_accepted':False};write(m/'cleanup.original.json',result);return result
def final():
 p=frozen();s=status();require(s['completed_G_verified_parts']==540 and s['current'] is None,'Original full 21600 denominator incomplete');return {'ok':True,'source_sha':p['source_sha'],'original_G_parts':540,'actual_encounters':21600,'independent_statistics_and_full_case_coverage_still_required':True,'MAIN_accepted':False}
def main():
 require(os.geteuid()==0,'Tencent root controller only');a=sys.argv[1:];cmd=a[0]
 if cmd=='stream':stream(a[1]);return
 funcs={'init':initialize,'status':status,'launch':launch,'final':final}
 if cmd in funcs:v=funcs[cmd]()
 elif cmd=='run':v=run_unit(a[1])
 elif cmd=='delivery':v=delivery(a[1])
 elif cmd=='cleanup':v=cleanup(a[1],a[2])
 else:raise ValueError('Unknown original action')
 print(json.dumps(v));require(v['ok'],'Actual action failed')
if __name__=='__main__':main()
