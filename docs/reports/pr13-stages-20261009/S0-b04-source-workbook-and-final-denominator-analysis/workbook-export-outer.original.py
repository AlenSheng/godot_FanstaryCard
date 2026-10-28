import hashlib,json,os,subprocess,time
from pathlib import Path
B=Path('/home/ubuntu/pr13-acceptance-20261009');A='B04-current-workbook-export-r2-20261013';E=B/'evidence'/A;W=B/'work'/A;OWNER='pr13-cap-'+A;meta=json.loads((E/'inputs.original.json').read_bytes());IMAGE='sha256:180f524270f6ac28d2fe0ff29707fb392387d7b766f731e41fda1e45e8230520'
def run(a,timeout=40,check=True):
 r=subprocess.run([str(x) for x in a],capture_output=True,timeout=timeout)
 if check:r.check_returncode()
 return r
def docker(*a,**kw):return run(['docker',*a],**kw)
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def frozen():
 for row in meta['runtime_files']:
  p=Path(meta['runtime_root'])/row['path'];assert p.stat().st_size==row['bytes'] and sha(p)==row['sha256']
 for row in meta['input_files']:
  p=W/'inputs'/row['path'];assert p.stat().st_size==row['bytes'] and sha(p)==row['sha256']
def guard(start=False):
 s=os.statvfs('/');m=int(next(l.split()[1] for l in Path('/proc/meminfo').read_text().splitlines() if l.startswith('MemAvailable:')))*1024;assert m>=500000000+(320*1024**2 if start else 0) and s.f_bavail/s.f_blocks>=.15;return {'at':time.time(),'memory_available_bytes':m,'root_free_fraction':s.f_bavail/s.f_blocks}
state=dict(l.split('=',1) for l in run(['systemctl','show',OWNER,'--property=MainPID,ActiveState']).stdout.decode().splitlines());assert state['MainPID']==str(os.getpid()) and state['ActiveState']=='active';(E/'started.original.json').write_bytes((json.dumps({'PID':os.getpid(),'state':state})+'\n').encode());frozen();until=time.monotonic()+3600
while True:
 st=json.loads(run(['python3',B/'evidence/T03-conditioned-full-r2-20261012/controller.original.py','status']).stdout);units=run(['systemctl','list-units','--state=running','--no-legend','--plain','--no-pager','pr13-cap-*','pr13-pool-segment-*']).stdout.decode().splitlines();others=[l for l in units if l.split()[0]!=OWNER+'.service']
 if st['current'] is None and not others:
  try:guard(True);break
  except AssertionError:pass
 assert time.monotonic()<until,'Admission deadline; original handles retained';time.sleep(5)
out=E/'persistent-native-outputs';out.mkdir(mode=0o777);out.chmod(0o777);cid=None;result={'ok':False,'source_sha':meta['source_sha'],'MAIN_accepted':False}
def owned():
 v=json.loads(docker('inspect',cid).stdout)[0];assert v['Id']==cid and v['Name']=='/'+OWNER and v['Config']['Labels']['codex.owner']==OWNER;return v
try:
 version=(W/'inputs/server/config/generated/fantasycard.config.version.txt').read_text().strip();args=['dotnet','/runtime/FantasyCard.ConfigExporter.dll','--input','/inputs/config/FantasyCard_Config.xlsx','--version',version,'--server-output','/output/server','--client-output','/output/client'];cid=docker('create','--name',OWNER,'--label','codex.owner='+OWNER,'--network','none','--memory','256m','--memory-swap','256m','--cpus','1','--read-only','--tmpfs','/tmp:rw,nosuid,nodev,size=67108864','--user','1000:1000','-e','HOME=/tmp/home','-v',meta['runtime_root']+':/runtime:ro','-v',str(W/'inputs')+':/inputs:ro','-v',str(out)+':/output',IMAGE,*args).stdout.decode().strip();owned();docker('start',cid);until=time.monotonic()+120
 while True:
  info=owned()
  if not info['State']['Running']:break
  assert time.monotonic()<until;guard();time.sleep(1)
 logs=docker('logs',cid);(out/'export.original.log').write_bytes(logs.stdout+logs.stderr);(E/'native-terminal-state.original.json').write_bytes((json.dumps({k:info['State'][k] for k in ['ExitCode','OOMKilled','StartedAt','FinishedAt','Error']},indent=2)+'\n').encode());assert info['State']['ExitCode']==0 and not info['State']['OOMKilled'];checks=[]
 for side in ['server','client']:
  for suffix in ['bytes','sha256','version.txt']:
   original=W/'inputs'/('server/config/generated' if side=='server' else 'client/data/generated')/('fantasycard.config.'+suffix);generated=out/side/('fantasycard.config.'+suffix);assert generated.read_bytes()==original.read_bytes();checks.append({'side':side,'name':generated.name,'bytes':generated.stat().st_size,'sha256':sha(generated),'byte_equal_current_Git_input':True})
 actual=sha(out/'server/fantasycard.config.bytes');assert actual==meta['expected_embedded_resource_bytes_sha256'];result.update(ok=True,exit_code=0,oom_killed=False,source_workbook_Git_sha256=next(r['sha256'] for r in meta['input_files'] if r['path'].endswith('.xlsx')),actual_generated_resource_bytes_sha256=actual,canonical_bundle_sha256=(out/'server/fantasycard.config.sha256').read_text().strip(),canonical_bundle_hash_not_direct_resource_bytes_hash=True,exact_original_client_server_generated_members=checks,generated_bytes_equal_actual_experiment_embedded_resource=True,production_config_unchanged=True)
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
 try:frozen();result['inputs_unchanged']=True
 except Exception:result['inputs_unchanged']=False
 result['ok']=result['ok'] and removed and result['inputs_unchanged'];(E/'result.original.json').write_bytes((json.dumps(result,indent=2)+'\n').encode())
print(json.dumps(result));raise SystemExit(0 if result['ok'] else 1)
