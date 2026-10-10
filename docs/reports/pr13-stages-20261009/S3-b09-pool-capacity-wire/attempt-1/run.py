import gzip,hashlib,json,os,subprocess,time,urllib.request,xml.etree.ElementTree as ET
from pathlib import Path
B=Path('/home/ubuntu/pr13-acceptance-20261009');E=B/'evidence/pool-capacity-wire-r1';R=Path('/dev/shm/pr13-pool-capacity-wire-r1-20261011');S=R/'source';meta=json.loads((E/'inputs.json').read_text());SHA=meta['source_sha'];OWNER='pr13-pool-capacity-wire-20261011';cid=None;out={'ok':False,'source_sha':SHA}
def docker(*args):return subprocess.run(['sudo','-n','docker',*args],capture_output=True,text=True,check=True,timeout=30)
payload="""import gzip,hashlib,json,subprocess,sys,time,xml.etree.ElementTree as ET
from pathlib import Path
r=Path('/ram');sha=sys.argv[1];out={}
def run(name,cmd,budget):
 (r/'phase.json').write_text(json.dumps({'phase':name,'started':time.time()}))
 with (r/(name+'.log')).open('w') as f:p=subprocess.run(cmd,stdout=f,stderr=subprocess.STDOUT,timeout=budget)
 out[name]={'exit_code':p.returncode};(r/'inner-result.json').write_text(json.dumps(out))
 if p.returncode:sys.exit(p.returncode)
base=['dotnet','test','/work/server/tests/FantasyCard.Server.Tests/FantasyCard.Server.Tests.csproj','-c','Release','--results-directory','/ram/test-results','-p:RestoreIgnoreFailedSources=true','-p:NuGetAudit=false']
run('server',base+['--filter','FullyQualifiedName~MonsterPoolCapacityWireTests|FullyQualifiedName~MonsterPoolBaselineWireTests|FullyQualifiedName~NumericalProtocolTests','--logger','trx;LogFileName=pool-capacity-server.trx'],360)
rows=0
with (r/'wire-vectors.jsonl').open('wb') as target:
 for p in sorted((r/'wire').glob('*.jsonl.gz')):
  with gzip.open(p,'rb') as source:
   for line in source:
    row=json.loads(line);assert row['source_sha']==sha;target.write(line);rows+=1
assert rows==279
run('independent',['python3','/work/tools/pr13_monster_pool_capacity.py','--native','/ram/wire','--source-sha',sha,'--output','/ram/independent-validation.json'],120)
run('client',['godot','--headless','--path','/client','--script','res://tests/run_monster_pool_capacity_vectors.gd'],120)
assert json.loads((r/'client-result.json').read_text())['ok']
run('native-return',base+['--no-build','--no-restore','--filter','FullyQualifiedName~MonsterPoolCapacityGodotWireTests','--logger','trx;LogFileName=pool-capacity-Godot-return.trx'],120)
receipt=json.loads((r/'native-return-receipt.json').read_text());assert receipt['ok'] and receipt['original_Godot_commands_decoded']==279 and receipt['fallback_native_CI_used'] is False
tests={}
for name,expected in [('pool-capacity-server.trx',36),('pool-capacity-Godot-return.trx',1)]:
 c=ET.parse(r/'test-results'/name).getroot().find('{http://microsoft.com/schemas/VisualStudio/TeamTest/2010}ResultSummary/{http://microsoft.com/schemas/VisualStudio/TeamTest/2010}Counters').attrib;assert int(c['failed'])==0 and int(c['notExecuted'])==0 and int(c['passed'])==expected;tests[name]=dict(c)
v=json.loads((r/'independent-validation.json').read_text());assert v['ok']
(r/'native-summary.json').write_text(json.dumps({'ok':True,'source_sha':sha,'tests':tests,'wire_rows':rows,'original_snapshot_frames':rows*2,'capacity_rows':v['case_rows'],'original_files':v['original_files'],'native_return':receipt,'formal_experiment_pending':True,'canonical_render_pending':True,'whole_task_accepted':False},indent=2))
"""
try:
 mem=int(next(l.split()[1] for l in Path('/proc/meminfo').read_text().splitlines() if l.startswith('MemAvailable:')))*1024;s=os.statvfs(B);shm=os.statvfs('/dev/shm');assert mem>=500000000+(950+128)*1024**2 and s.f_bavail/s.f_blocks>=.15 and shm.f_bavail*shm.f_frsize>=128*1024**2
 cid=docker('create','--name','pr13-pool-capacity-wire-r1','--label','codex.owner='+OWNER,'--memory','950m','--cpus','1','--user','1000:1000','--network','none','-e','NUGET_PACKAGES=/packages','-e','FANTASYCARD_PR13_SOURCE_SHA='+SHA,'-e','FANTASYCARD_PR13_POOL_CAPACITY_WIRE_EVIDENCE=/ram/wire','-e','FANTASYCARD_PR13_POOL_WIRE_EVIDENCE=/ram/baseline-wire','-e','PR13_POOL_CAPACITY_SOURCE='+SHA,'-e','PR13_POOL_CAPACITY_VECTORS=/ram/wire-vectors.jsonl','-e','PR13_POOL_CAPACITY_RESULT=/ram/client-result.json','-e','PR13_POOL_CAPACITY_CLIENT_COMMANDS=/ram/client-commands.jsonl','-e','FANTASYCARD_PR13_POOL_CAPACITY_GODOT_COMMANDS=/ram/client-commands.jsonl','-e','FANTASYCARD_PR13_POOL_CAPACITY_NATIVE_COMMANDS=/ram/wire-vectors.jsonl','-e','FANTASYCARD_PR13_POOL_CAPACITY_GODOT_RECEIPT=/ram/native-return-receipt.json','-e','FANTASYCARD_SERVER_URL=http://127.0.0.1:1','-v',str(S)+':/work','-v',str(R)+':/ram','-v',meta['client_root']+':/client:ro','-v',str(B/'cache')+':/cache:ro','-v',meta['package_root']+':/packages:ro','sha256:6ea92944e8779a5bb6e5c40faca53a40a1b02b5a0dcd47fff0815ba9cfbded1f','python3','-c',payload,SHA).stdout.strip();assert len(cid)==64;docker('start',cid);deadline=time.monotonic()+900
 while True:
  d=json.loads(docker('inspect',cid).stdout)[0];assert d['Id']==cid and d['Config']['Labels']['codex.owner']==OWNER
  if not d['State']['Running']:break
  mem=int(next(l.split()[1] for l in Path('/proc/meminfo').read_text().splitlines() if l.startswith('MemAvailable:')))*1024;s=os.statvfs(B);used=sum(p.stat().st_size for p in R.rglob('*') if p.is_file());assert mem>=500000000 and s.f_bavail/s.f_blocks>=.15 and used<=128*1024**2 and time.monotonic()<deadline
  with (E/'resources.jsonl').open('a') as f:f.write(json.dumps({'at':time.time(),'memory_available_bytes':mem,'disk_free_ratio':s.f_bavail/s.f_blocks,'RAM_bytes':used})+'\n')
  time.sleep(5)
 out.update(exit_code=d['State']['ExitCode'],oom_killed=d['State']['OOMKilled'],ok=d['State']['ExitCode']==0 and not d['State']['OOMKilled'])
except Exception as ex:out.update(error=type(ex).__name__,detail=str(ex))
finally:
 if cid:
  d=json.loads(docker('inspect',cid).stdout)[0];assert d['Id']==cid and d['Config']['Labels']['codex.owner']==OWNER;log=docker('logs',cid);(E/'container.log').write_text(log.stdout+log.stderr);docker('rm','-f','-v',cid);out['owned_container_removed']=True
 out['source_inputs_unchanged']=all(hashlib.sha256((S/n).read_bytes()).hexdigest()==h for n,h in meta['server_hashes'].items());out['readonly_packages_unchanged']=all(hashlib.sha256((Path(meta['package_root'])/n).read_bytes()).hexdigest()==h for n,h in meta['package_hashes'].items())
 out['client_inputs_unchanged']=all(hashlib.sha256((Path(meta['client_root']).parent/n).read_bytes()).hexdigest()==h for n,h in meta['client_hashes'].items());out['ok']=out['ok'] and out['source_inputs_unchanged'] and out['readonly_packages_unchanged'] and out['client_inputs_unchanged']
 with urllib.request.urlopen('http://127.0.0.1:8080/health/ready',timeout=10) as h:out['health_status']=h.status
 out.update(formal_experiment_pending=True,canonical_render_pending=True,whole_task_accepted=False);(E/'result.json').write_text(json.dumps(out,indent=2)+'\n')
print(json.dumps(out))
