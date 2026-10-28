import hashlib,json,os,subprocess,time,urllib.request
from pathlib import Path
B=Path('/home/ubuntu/pr13-acceptance-20261009');E=B/'evidence/pool-baseline-offline-r4';R=Path('/dev/shm/pr13-pool-baseline-offline-r4-20261011');S=R/'source';meta=json.loads((E/'inputs.json').read_text());SHA=meta['source_sha'];OWNER='pr13-pool-baseline-20261011';cid=None;out={'ok':False,'source_sha':SHA}
def docker(*args):return subprocess.run(['sudo','-n','docker',*args],capture_output=True,text=True,check=True,timeout=30)
payload="""import gzip,hashlib,json,subprocess,sys,time,xml.etree.ElementTree as ET
from pathlib import Path
sha=sys.argv[1];r=Path('/ram');out={}
def run(name,cmd,budget):
 (r/'phase.json').write_text(json.dumps({'phase':name,'started':time.time()})+'\\n')
 with (r/(name+'.log')).open('w') as f:p=subprocess.run(cmd,stdout=f,stderr=subprocess.STDOUT,timeout=budget)
 out[name]={'exit_code':p.returncode};(r/'inner-result.json').write_text(json.dumps(out)+'\\n')
 if p.returncode:sys.exit(p.returncode)
# The exact-source domain/TRX/originals are reused after their successful prior phase.
out['domain']={'exit_code':0,'reused_verified_source_phase':True}
run('server',['dotnet','test','/work/server/tests/FantasyCard.Server.Tests/FantasyCard.Server.Tests.csproj','-c','Release','--filter','FullyQualifiedName~MonsterPoolBaselineWireTests|FullyQualifiedName~NumericalProtocolTests','--logger','trx;LogFileName=pool-server.trx','--results-directory','/ram/test-results','-p:RestoreIgnoreFailedSources=true','-p:NuGetAudit=false'],300)
rows=0
with (r/'wire-vectors.jsonl').open('wb') as target:
 for p in sorted((r/'wire').glob('*.jsonl.gz')):
  with gzip.open(p,'rb') as source:
   for line in source:
    d=json.loads(line);assert d['source_sha']==sha and len(d['legal_deck'])==len(set(d['legal_deck']))==20;target.write(line);rows+=1
assert rows==18
run('client',['godot','--headless','--path','/client','--script','res://tests/run_monster_pool_baseline_vectors.gd'],120)
assert json.loads((r/'client-result.json').read_text())['ok']
run('independent',['python3','/work/tools/pr13_monster_pool_baseline.py','--native','/ram/native','--catalog','/client/data/catalog.json','--source-sha',sha,'--output','/ram/independent-validation.json'],180)
files=[];counts={}
for directory in ['native','wire']:
 for p in sorted((r/directory).glob('*.jsonl.gz')):
  raw_hash=hashlib.sha256();raw_bytes=count=0
  with gzip.open(p,'rb') as f:
   for line in f:
    d=json.loads(line);assert d['source_sha']==sha;raw_hash.update(line);raw_bytes+=len(line);count+=1;counts[d['case_id']]=counts.get(d['case_id'],0)+1
  files.append({'path':p.relative_to(r).as_posix(),'rows':count,'raw_bytes':raw_bytes,'raw_sha256':raw_hash.hexdigest(),'stored_bytes':p.stat().st_size,'stored_sha256':hashlib.sha256(p.read_bytes()).hexdigest()})
tests={}
for p in (r/'test-results').glob('*.trx'):
 d=ET.parse(p).getroot();c=d.find('{http://microsoft.com/schemas/VisualStudio/TeamTest/2010}ResultSummary/{http://microsoft.com/schemas/VisualStudio/TeamTest/2010}Counters');assert int(c.attrib['failed'])==0 and int(c.attrib['notExecuted'])==0;tests[p.name]=dict(c.attrib)
(r/'native-summary.json').write_text(json.dumps({'ok':True,'source_sha':sha,'original_files':files,'case_rows':counts,'wire_rows':rows,'tests':tests,'full_experiment_pending':True,'canonical_render_pending':True,'whole_task_accepted':False},indent=2)+'\\n')
"""
try:
 mem=int(next(l.split()[1] for l in Path('/proc/meminfo').read_text().splitlines() if l.startswith('MemAvailable:')))*1024;shm=os.statvfs('/dev/shm');assert mem>=500000000+(950+256)*1024**2 and shm.f_bavail*shm.f_frsize>=256*1024**2
 cid=docker('create','--name','pr13-pool-baseline-offline-r4','--label','codex.owner='+OWNER,'--memory','950m','--cpus','1','--user','1000:1000','--network','none','-e','NUGET_PACKAGES=/packages','-e','FANTASYCARD_PR13_SOURCE_SHA='+SHA,'-e','FANTASYCARD_PR13_POOL_EVIDENCE=/ram/native','-e','FANTASYCARD_PR13_POOL_WIRE_EVIDENCE=/ram/wire','-e','PR13_POOL_SOURCE='+SHA,'-e','PR13_POOL_VECTORS=/ram/wire-vectors.jsonl','-e','PR13_POOL_RESULT=/ram/client-result.json','-e','FANTASYCARD_SERVER_URL=http://127.0.0.1:1','-v',str(S)+':/work','-v',meta['client_root']+':/client:ro','-v',str(R)+':/ram','-v',str(B/'cache')+':/cache:ro','-v',meta['package_root']+':/packages:ro','sha256:6ea92944e8779a5bb6e5c40faca53a40a1b02b5a0dcd47fff0815ba9cfbded1f','python3','-c',payload,SHA).stdout.strip();assert len(cid)==64;docker('start',cid);deadline=time.monotonic()+900
 while True:
  d=json.loads(docker('inspect',cid).stdout)[0];assert d['Id']==cid and d['Config']['Labels']['codex.owner']==OWNER
  if not d['State']['Running']:break
  mem=int(next(l.split()[1] for l in Path('/proc/meminfo').read_text().splitlines() if l.startswith('MemAvailable:')))*1024;s=os.statvfs(B);used=sum(p.stat().st_size for p in R.rglob('*') if p.is_file());assert mem>=500000000 and s.f_bavail/s.f_blocks>=.15 and used<=256*1024**2 and time.monotonic()<deadline
  with (E/'resources.jsonl').open('a') as f:f.write(json.dumps({'at':time.time(),'memory_available_bytes':mem,'disk_free_ratio':s.f_bavail/s.f_blocks,'RAM_bytes':used})+'\n')
  time.sleep(5)
 out.update(exit_code=d['State']['ExitCode'],oom_killed=d['State']['OOMKilled'],ok=d['State']['ExitCode']==0 and not d['State']['OOMKilled'])
except Exception as ex:out.update(error=type(ex).__name__,detail=str(ex))
finally:
 if cid:
  d=json.loads(docker('inspect',cid).stdout)[0];assert d['Id']==cid and d['Config']['Labels']['codex.owner']==OWNER;log=docker('logs',cid);(E/'container.log').write_text(log.stdout+log.stderr);docker('rm','-f','-v',cid);out['owned_container_removed']=True
 out['server_inputs_unchanged']=all(hashlib.sha256((S/n).read_bytes()).hexdigest()==h for n,h in meta['server_hashes'].items());out['client_inputs_unchanged']=all(hashlib.sha256((Path(meta['client_root']).parent/n).read_bytes()).hexdigest()==h for n,h in meta['client_hashes'].items());out['readonly_packages_unchanged']=all(hashlib.sha256((Path(meta['package_root'])/n).read_bytes()).hexdigest()==h for n,h in meta['package_hashes'].items())
 for name in ['native-summary','client-result']:
  if (R/(name+'.json')).exists():out[name]=json.loads((R/(name+'.json')).read_text())
 out['ok']=out['ok'] and out['server_inputs_unchanged'] and out['client_inputs_unchanged'] and out['readonly_packages_unchanged'] and out.get('client-result',{}).get('ok') is True
 with urllib.request.urlopen('http://127.0.0.1:8080/health/ready',timeout=10) as h:out['health_status']=h.status
 out.update(full_experiment_pending=True,canonical_render_pending=True,whole_task_accepted=False);(E/'result.json').write_text(json.dumps(out,indent=2)+'\n')
print(json.dumps({k:v for k,v in out.items() if k not in ['native-summary','client-result']}))
