import hashlib,json,os,subprocess,time,urllib.request
from pathlib import Path
B=Path('/home/ubuntu/pr13-acceptance-20261009');E=B/'evidence/cap-experiment-pilot-r3';R=Path('/dev/shm/pr13-cap-experiment-pilot-r3-20261011');S=Path('/dev/shm/pr13-cap-experiment-pilot-r2-20261011/source');BASE=S.parent;meta=json.loads((E/'inputs.json').read_text());SHA=meta['native_source_sha'];OWNER='pr13-cap-experiment-20261011';cid=None;out={'ok':False,'source_sha':SHA}
def docker(*args):return subprocess.run(['sudo','-n','docker',*args],capture_output=True,text=True,check=True,timeout=30)
payload="""import itertools,json,subprocess,sys,time
from pathlib import Path
sha=sys.argv[1];r=Path('/ram');status={}
def run(name,cmd,budget):
 (r/'phase.json').write_text(json.dumps({'phase':name,'started':time.time()})+'\\n')
 with (r/(name+'.log')).open('w') as f:p=subprocess.run(cmd,stdout=f,stderr=subprocess.STDOUT,timeout=budget)
 status[name]={'exit_code':p.returncode};(r/'inner-result.json').write_text(json.dumps(status)+'\\n')
 if p.returncode:sys.exit(p.returncode)
units=[]
for hero,group,element,level in itertools.product(['Mage','Priest','Guardian'],['O1','O6','E1','BOSS'],['Fire','Wood','Earth','Metal','Water'],[0,5]):
 name=f'{hero}-{group}-{element}-L{level}';native=r/'units'/name;native.parent.mkdir(exist_ok=True)
 run(name,['dotnet','/base/runtime/FantasyCard.Numerics.dll','--cap-effective-experiment','--source-sha',sha,'--output',str(native),'--hero',hero,'--group',group,'--element',element,'--equipment-level',str(level),'--block-index','0','--samples','3'],120)
 run(name+'-validation',['python3','/analysis/pr13_cap_effective_experiment.py','--input',str(native),'--source-sha',sha,'--controls','--output',str(native/'validation.json')],120)
 units.append({'unit':name,'validation':json.loads((native/'validation.json').read_text())});(r/'pilot-progress.json').write_text(json.dumps({'completed_units':len(units),'expected_units':120,'latest':name})+'\\n')
assert len(units)==120 and sum(u['validation']['encounters'] for u in units)==720
(r/'pilot-summary.json').write_text(json.dumps({'ok':True,'source_sha':sha,'units':units,'encounters':720,'pairs':360,'actual_casts':sum(u['validation']['actual_casts'] for u in units),'actual_ticks':sum(u['validation']['actual_ticks'] for u in units),'full_experiment_complete':False,'main_acceptance_granted':False},indent=2)+'\\n')
"""
try:
 mem=int(next(l.split()[1] for l in Path('/proc/meminfo').read_text().splitlines() if l.startswith('MemAvailable:')))*1024;assert mem>=500000000+(950+512)*1024**2
 cid=docker('create','--name','pr13-cap-experiment-pilot-r3','--label','codex.owner='+OWNER,'--memory','950m','--cpus','1','--user','1000:1000','--network','none','-v',str(S)+':/work:ro','-v',str(BASE/'runtime')+':/base/runtime:ro','-v',str(E/'analysis')+':/analysis:ro','-v',str(R)+':/ram','-v',str(B/'cache')+':/cache:ro','sha256:6ea92944e8779a5bb6e5c40faca53a40a1b02b5a0dcd47fff0815ba9cfbded1f','python3','-c',payload,SHA).stdout.strip();assert len(cid)==64;docker('start',cid);deadline=time.monotonic()+1800
 while True:
  d=json.loads(docker('inspect',cid).stdout)[0];assert d['Id']==cid and d['Config']['Labels']['codex.owner']==OWNER
  if not d['State']['Running']:break
  mem=int(next(l.split()[1] for l in Path('/proc/meminfo').read_text().splitlines() if l.startswith('MemAvailable:')))*1024;s=os.statvfs(B);used=sum(p.stat().st_size for p in R.rglob('*') if p.is_file());assert mem>=500000000 and s.f_bavail/s.f_blocks>=.15 and used<=512*1024**2 and time.monotonic()<deadline
  with (E/'resources.jsonl').open('a') as f:f.write(json.dumps({'at':time.time(),'memory_available_bytes':mem,'disk_free_ratio':s.f_bavail/s.f_blocks,'RAM_bytes':used})+'\n')
  time.sleep(5)
 out.update(exit_code=d['State']['ExitCode'],oom_killed=d['State']['OOMKilled'],ok=d['State']['ExitCode']==0 and not d['State']['OOMKilled'])
except Exception as ex:out.update(error=type(ex).__name__,detail=str(ex))
finally:
 if cid:
  d=json.loads(docker('inspect',cid).stdout)[0];assert d['Id']==cid and d['Config']['Labels']['codex.owner']==OWNER;log=docker('logs',cid);(E/'container.log').write_text(log.stdout+log.stderr);docker('rm','-f','-v',cid);out['owned_container_removed']=True
 out['source_inputs_unchanged']=all(hashlib.sha256((S/n).read_bytes()).hexdigest()==h for n,h in meta['native_source_hashes'].items());out['analysis_source_sha']=meta['analysis_source_sha'];out['analysis_input_unchanged']=hashlib.sha256((E/'analysis/pr13_cap_effective_experiment.py').read_bytes()).hexdigest()==meta['analysis_sha256'];out['compiled_runtime_unchanged']=all(hashlib.sha256((BASE/'runtime'/n).read_bytes()).hexdigest()==h for n,h in meta['runtime_hashes'].items());out['ok']=out['ok'] and out['source_inputs_unchanged'] and out['analysis_input_unchanged'] and out['compiled_runtime_unchanged']
 if (R/'pilot-summary.json').exists():p=json.loads((R/'pilot-summary.json').read_text());out.update(encounters=p['encounters'],pairs=p['pairs'],units=len(p['units']),actual_casts=p['actual_casts'],actual_ticks=p['actual_ticks'])
 with urllib.request.urlopen('http://127.0.0.1:8080/health/ready',timeout=10) as h:out['health_status']=h.status
 out['full_experiment_complete']=False;out['main_acceptance_granted']=False;(E/'result.json').write_text(json.dumps(out,indent=2)+'\n')
print(json.dumps(out))
