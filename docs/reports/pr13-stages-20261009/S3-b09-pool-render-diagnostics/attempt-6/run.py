import json,os,subprocess,sys,time
from pathlib import Path
B=Path('/home/ubuntu/pr13-acceptance-20261009');E=B/'evidence/pool-capacity-render-r6-probe';S=E/'source';R=Path('/dev/shm/pr13-pool-capacity-render-r6-probe-20261011');sys.path.insert(0,str(S));from tools.cloud.pr13 import render_runtime
meta=json.loads((E/'preregistration.json').read_text());out={'ok':False,'source_sha':meta['render_source_sha'],'diagnostic_only':True}
def guard(output,reserve_memory=0,reserve_disk=0):
 s=os.statvfs(B);t=os.statvfs('/dev/shm');mem=int(next(l.split()[1] for l in Path('/proc/meminfo').read_text().splitlines() if l.startswith('MemAvailable:')))*1024;used=sum(p.stat().st_size for p in R.rglob('*') if p.is_file());assert mem>=500000000+reserve_memory and s.f_bavail/s.f_blocks>=.15 and s.f_bavail*s.f_frsize>=s.f_blocks*s.f_frsize*.15+reserve_disk and t.f_bavail*t.f_frsize>=reserve_disk and used<=32*1024**2
 import urllib.request
 with urllib.request.urlopen('http://127.0.0.1:8080/health/ready',timeout=10) as h:assert h.status==200
 sample={'at':time.time(),'memory_available_bytes':mem,'root_free_ratio':s.f_bavail/s.f_blocks,'RAM_free_bytes':t.f_bavail*t.f_frsize,'owned_RAM_bytes':used}
 with (E/'resources.jsonl').open('a') as f:f.write(json.dumps(sample)+'\n')
 return sample
render_runtime.guard=guard
try:
 guard(R,768*1024**2)
 cid=render_runtime.docker('create','--name','pr13-pool-capacity-parse-r6','--label','codex.task=pr13-cloud-render-20261010','--network','none','--memory','768m','--cpus','1','--user','1000:1000','-v',str(S/'client')+':/work/client:ro','-v',str(R)+':/evidence','sha256:180f524270f6ac28d2fe0ff29707fb392387d7b766f731e41fda1e45e8230520','godot','--headless','--path','/work/client','res://tests/pr13_pool_capacity_probe.tscn','--quit-after','1').stdout.strip()
 try:
  render_runtime.inspect_owned(cid)
  with (R/'parse.log').open('w') as log:p=subprocess.run(['sudo','-n','docker','start','-a',cid],stdout=log,stderr=subprocess.STDOUT,timeout=60)
  out['syntax_exit_code']=p.returncode
 finally:render_runtime.inspect_owned(cid);render_runtime.docker('rm','-f','-v',cid)
 text=(R/'parse.log').read_text()
 if p.returncode or any(k in text for k in ['SCRIPT ERROR','Parse Error','Failed to load script']):raise RuntimeError('Parse/load failed before actual GUI probe')
 result=render_runtime.render('sha256:180f524270f6ac28d2fe0ff29707fb392387d7b766f731e41fda1e45e8230520',S,E/'inputs.json',R/'PR13-B09.2-T02','res://tests/pr13_pool_capacity_probe.tscn',expected_rows=1,expected_screenshots=1,deadline_seconds=300,reserve_output_bytes=16*1024**2);out['execution']=result;text=(R/'PR13-B09.2-T02/engine.log').read_text();out['shutdown_resources_clean']=not any(k in text for k in ['resources still in use','ObjectDB instances were leaked']);out['ok']=result['ok'] and out['shutdown_resources_clean']
except Exception as ex:out.update(error=type(ex).__name__,detail=str(ex))
finally:out['whole_task_accepted']=False;(E/'result.json').write_text(json.dumps(out,indent=2)+'\n')
print(json.dumps(out))
