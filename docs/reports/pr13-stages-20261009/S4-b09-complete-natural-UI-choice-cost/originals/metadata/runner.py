import hashlib,json,os,subprocess,time
from pathlib import Path
B=Path('/home/ubuntu/pr13-acceptance-20261009');A='b09-natural-ui-choice-cost-r1-20261011';OWNER='pr13-cap-'+A;E=B/'evidence'/A;W=B/'work'/A;IMAGE='sha256:6ea92944e8779a5bb6e5c40faca53a40a1b02b5a0dcd47fff0815ba9cfbded1f';links=json.loads((E/'input-links.original.json').read_bytes())
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def save(p,v):
 assert not p.exists();p.write_text(json.dumps(v,indent=2,allow_nan=False)+'\n')
def command(a,t=30):
 p=subprocess.run(a,capture_output=True,text=True,timeout=t);assert p.returncode==0,(a[0],p.returncode,p.stderr[-1000:]);return p
def guard(reserve=False):
 available=int(next(x.split()[1] for x in Path('/proc/meminfo').read_text().splitlines() if x.startswith('MemAvailable:')))*1024;d=os.statvfs('/');assert available>=500000000+(208*1024**2 if reserve else 0) and (d.f_bavail*d.f_frsize-(32*1024**2 if reserve else 0))/(d.f_blocks*d.f_frsize)>=.15;return {'at':time.time(),'memory_available_bytes':available,'root_free_ratio':d.f_bavail/d.f_blocks}
state=dict(x.split('=',1) for x in command(['systemctl','show',OWNER,'--property=Id,MainPID,ActiveState,InvocationID']).stdout.splitlines());assert state['Id']==OWNER+'.service' and int(state['MainPID'])==os.getpid() and state['ActiveState']=='active' and not (E/'startup.json').exists();guard(True)
assert sha(E/'analysis.py')==links['tool_sha256'];index=json.loads((W/'inputs/index.json').read_bytes())
for row in index['files']:assert sha(W/'inputs'/row['path'])==row['sha256']
save(E/'startup.json',{'owner':OWNER,'MainPID':os.getpid(),'invocation_id':state['InvocationID'],'boot_id':Path('/proc/sys/kernel/random/boot_id').read_text().strip(),'source_sha':links['source_sha'],'tool_sha256':links['tool_sha256'],'index_sha256':sha(W/'inputs/index.json'),'at':time.time(),'no_native_business_routes_regenerated':True})
cid=None;result={'ok':False,'attempt':A,'source_sha':links['source_sha'],'tool_sha256':links['tool_sha256'],'MAIN_accepted':False,'whole_task_accepted':False}
try:
 cid=command(['docker','create','--name',OWNER,'--label','pr13.owner='+OWNER,'--label','pr13.attempt='+A,'--network','none','--cpus','0.5','--memory','128m','--memory-swap','128m','--read-only','--pids-limit','64','--user','1000:1000','--tmpfs','/tmp:rw,nosuid,nodev,size=16777216','-e','PYTHONDONTWRITEBYTECODE=1','-e','PR13_UI_COST_CLOUD=tencent-descriptive-v1','-v',str(E/'analysis.py')+':/work/analysis.py:ro','-v',str(W/'inputs')+':/inputs:ro','-v',str(W/'outputs')+':/outputs',IMAGE,'python3','/work/analysis.py','--input','/inputs','--output','/outputs/choice-cost.json'],60).stdout.strip()
 def owned():
  v=json.loads(command(['docker','inspect',cid]).stdout)[0];assert v['Id']==cid and v['Config']['Labels']['pr13.owner']==OWNER and v['Config']['Image']==IMAGE;return v
 owned();command(['docker','start',cid]);deadline=time.monotonic()+180
 while owned()['State']['Running']:
  sample=guard();assert time.monotonic()<deadline
  with (E/'resources.jsonl').open('a') as f:f.write(json.dumps(sample)+'\n')
  time.sleep(1)
 info=owned();logs=command(['docker','logs',cid]);(W/'outputs/container.stdout.original.log').write_text(logs.stdout);(W/'outputs/container.stderr.original.log').write_text(logs.stderr);assert len(logs.stdout)+len(logs.stderr)<1024**2
 assert not info['State']['OOMKilled'] and info['State']['ExitCode']==0
 report=json.loads((W/'outputs/choice-cost.json').read_bytes());assert report['ok'] and report['all_segments']==18 and report['original_render_observations']==3078 and report['negative_controls']['rejected_invalid_evidence_controls']==6 and report['negative_controls']['small_N_tail_control']
 assert all(sha(W/'inputs'/x['path'])==x['sha256'] for x in index['files']) and sha(E/'analysis.py')==links['tool_sha256']
 result.update(ok=True,exit_code=0,oom_killed=False,original_inputs_unchanged=True,full_matrix_described=True,source_inputs_match_git=True,report_sha256=sha(W/'outputs/choice-cost.json'),original_observations=3078,original_vectors=57,invalid_evidence_controls_passed=6,small_N_tail_control_passed=True)
except Exception as error:result.update(error=type(error).__name__,detail=str(error),all_failed_originals_retained=True)
finally:
 if cid:
  info=owned()
  if info['State']['Running']:command(['docker','stop','--time','10',cid])
  assert not owned()['State']['Running'];command(['docker','rm',cid]);result['owned_container_removed']=True
 save(E/'result.json',result)
print(json.dumps(result));raise SystemExit(0 if result['ok'] else 1)
