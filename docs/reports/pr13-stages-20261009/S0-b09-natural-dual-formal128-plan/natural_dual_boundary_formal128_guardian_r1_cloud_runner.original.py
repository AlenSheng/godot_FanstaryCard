import hashlib,json,os,subprocess,time,urllib.request
from pathlib import Path
B=Path('/home/ubuntu/pr13-acceptance-20261009');A='natural-dual-boundary-formal128-guardian-r1-20261012';OWNER='pr13-cap-'+A;E=B/'evidence'/A;W=B/'work'/A;D=B/'work/natural-dual-boundary-r4-inputs';RAM=Path('/dev/shm/pr13-'+A);IMAGE='180f524270f6ac28d2fe0ff29707fb392387d7b766f731e41fda1e45e8230520'
def command(args,check=True):return subprocess.run(args,capture_output=True,check=check,timeout=35)
def docker(*args,check=True):return command(['docker',*map(str,args)],check)
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def freeze():
 meta=json.loads((D/'manifest.json').read_bytes())
 for row in meta['files']:
  p=D/row['path'];assert not p.is_symlink() and p.stat().st_size==row['bytes'] and sha(p)==row['sha256']
 return meta
def guard(start=False):
 memory=int(next(x.split()[1] for x in Path('/proc/meminfo').read_text().splitlines() if x.startswith('MemAvailable:')))*1024;st=os.statvfs('/');assert memory>=500000000+(768+640)*1024**2*int(start) and st.f_bavail*st.f_frsize>=st.f_blocks*st.f_frsize*.15+128*1024**2*int(start)
 with urllib.request.urlopen('http://127.0.0.1:8080/health/ready',timeout=10) as h:assert h.status==200
 return {'memory_available_bytes':memory,'root_free_bytes':st.f_bavail*st.f_frsize,'production_health_status':200}
def write(p,v):assert not p.exists();p.write_text(json.dumps(v,indent=2)+'\n');p.chmod(0o600)
unit=dict(x.split('=',1) for x in command(['systemctl','show',OWNER,'--property=MainPID,ActiveState,InvocationID']).stdout.decode().splitlines());assert unit['ActiveState']=='active' and int(unit['MainPID'])==os.getpid();assert os.environ['PR13_CHOICE_CONTRACT_OWNER']==OWNER;meta=freeze();initial=guard(True);assert not (E/'run-started.json').exists() and not RAM.exists()
write(E/'run-started.json',{'actual_PID':os.getpid(),'invocation_id':unit['InvocationID'],'boot_id':Path('/proc/sys/kernel/random/boot_id').read_text().strip(),'input_manifest_sha256':sha(D/'manifest.json'),'actual_working_tree_harness_source_kind':meta['harness_source_kind'],'at':time.time(),'guard':initial})
RAM.mkdir();command(['mount','-t','tmpfs','-o','size=671088640,mode=0777,nosuid,nodev',OWNER,str(RAM)]);artifacts=W/'artifacts';artifacts.mkdir();artifacts.chmod(0o777)
inner=r'''
import json,os,subprocess
from pathlib import Path
E=Path('/evidence');phases=[];project='/inputs/harness/DualContract.csproj'
def phase(name,args,timeout):
 with (E/(name+'.log')).open('xb') as f:r=subprocess.run(args,stdout=f,stderr=subprocess.STDOUT,cwd='/inputs',timeout=timeout)
 phases.append({'name':name,'exit_code':r.returncode});assert r.returncode==0,name+' failed'
try:
 actual=subprocess.check_output(['dotnet','--version'],cwd='/inputs',text=True).strip();assert actual==json.loads(Path('/inputs/global.json').read_bytes())['sdk']['version']
 phase('restore',['dotnet','restore',project,'--artifacts-path','/artifacts','--configfile','/inputs/harness/NuGet.Config','-p:RestorePackagesPath=/tmp/packages','-p:UseSharedCompilation=false','-maxcpucount:1'],300)
 phase('build',['dotnet','build',project,'-c','Release','--no-restore','--artifacts-path','/artifacts','-p:Pr13RuntimeDirectory=/inputs/runtime','-p:UseSharedCompilation=false','-maxcpucount:1'],480)
 routes=0;coverage=[]
 for hero in ('Guardian',):
  phase('native-'+hero,['dotnet','/artifacts/bin/DualContract/release/DualContract.dll','--output',str(E/hero),'--source','aaa8fbbf04149823a6cf0ae38db0dc613cf95e1f','--hero',hero,'--seed-start','484001','--seeds','128'],1800)
  v=json.loads((E/hero/'result.json').read_bytes());assert v['ok'] and v['routes']==512 and v['naturalCombat'] and v['typedRouterIntents'] and not v['productionChanged']
  rows=[json.loads(x) for x in (E/hero/'routes.jsonl').read_text().splitlines()];assert len(rows)==512 and {(x['seed'],x['capacity']) for x in rows}=={(seed,cap) for seed in range(484001,484129) for cap in (0,3,5,8)}
  assert all(x['instanceAudits']>0 and len(x['players'])==len(set(x['players']))==2 and len(x['finalPhases'])==2 and x['outcome'] for x in rows)
  for cap in (0,3,5,8):
   r=[x for x in rows if x['capacity']==cap];coverage.append({'hero':hero,'capacity':cap,'paired_routes':128,'known_foreign_candidate_probes':sum(x['knownForeignProbes'] for x in r),'own_choices':sum(x['ownChoices'] for x in r),'natural_PVP_entries':sum(x['naturalPvpEntries'] for x in r),'actual_checkpoint_restores':sum(x['checkpointRestores'] for x in r),'mutual_leave_returns':sum(x['mutualLeaveReturns'] for x in r),'terminal_invariant_checks':sum(x['terminalInvariantChecks'] for x in r)})
  routes+=512
 result={'ok':True,'formal_dual_boundary_supplement':True,'natural_routes':routes,'coverage':coverage,'phases':phases,'missing_branches_are_not_passes':True,'MAIN_accepted':False}
except Exception as error:result={'ok':False,'error':type(error).__name__,'detail':str(error),'phases':phases,'failed_raw_retained':True,'MAIN_accepted':False}
(E/'inner-result.json').write_text(json.dumps(result,indent=2)+'\n');raise SystemExit(0 if result['ok'] else 1)
'''
(E/'inner.original.py').write_text(inner);cid=None;result={'ok':False,'MAIN_accepted':False}
try:
 assert docker('inspect',OWNER,check=False).returncode!=0
 cid=docker('create','--name',OWNER,'--label','codex.owner='+OWNER,'--network','none','--memory','768m','--memory-swap','768m','--cpus','1','--read-only','--tmpfs','/tmp:rw,nosuid,nodev,size=134217728','--user','1000:1000','-e','HOME=/tmp/home','-e','DOTNET_CLI_HOME=/tmp/dotnet','-v',str(D)+':/inputs:ro','-v',str(E/'inner.original.py')+':/inner.py:ro','-v',str(artifacts)+':/artifacts','-v',str(RAM)+':/evidence',IMAGE,'python3','/inner.py').stdout.decode().strip();docker('start',cid);deadline=time.monotonic()+3300
 while True:
  info=json.loads(docker('inspect',cid).stdout)[0];assert info['Id']==cid and info['Name']=='/'+OWNER and info['Config']['Labels']['codex.owner']==OWNER
  if not info['State']['Running']:break
  assert time.monotonic()<deadline;sample=guard();assert sum(x.stat().st_size for x in artifacts.rglob('*') if x.is_file())<=128*1024**2
  with (E/'resources.jsonl').open('a') as f:f.write(json.dumps(sample)+'\n')
  time.sleep(5)
 logs=docker('logs',cid);(RAM/'container.original.log').write_bytes(logs.stdout+logs.stderr);observed=json.loads((RAM/'inner-result.json').read_bytes()) if (RAM/'inner-result.json').exists() else {};result.update(ok=info['State']['ExitCode']==0 and not info['State']['OOMKilled'] and observed.get('ok') is True,exit_code=info['State']['ExitCode'],oom_killed=info['State']['OOMKilled'],inner=observed)
except Exception as error:result.update(error=type(error).__name__,detail=str(error),failed_raw_retained=True)
finally:
 removed=False
 if cid:
  info=json.loads(docker('inspect',cid).stdout)[0];assert info['Id']==cid and info['Name']=='/'+OWNER and info['Config']['Labels']['codex.owner']==OWNER
  if info['State']['Running']:docker('stop','--time','10',cid)
  docker('rm',cid);removed=True
 freeze();result.update(owned_container_removed=removed,frozen_inputs_unchanged=True,all_originals_retained_pending_G=True);result['ok']=result['ok'] and removed;write(E/'run-result.json',result)
print(json.dumps(result));raise SystemExit(0 if result['ok'] else 1)
