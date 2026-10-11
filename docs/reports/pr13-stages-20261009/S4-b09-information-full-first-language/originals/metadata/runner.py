import fcntl,hashlib,json,os,subprocess,time,urllib.request
from pathlib import Path
B=Path('/home/ubuntu/pr13-acceptance-20261009');A='b09-information-default-render-full-zh-cn-r2-20261011';OWNER='pr13-cap-'+A;E=B/'evidence'/A;W=B/'work'/A;S=B/'work/b09-information-default-render-smoke-r5-20261011/source';RAM=Path('/dev/shm/pr13-'+A);IMAGE='sha256:180f524270f6ac28d2fe0ff29707fb392387d7b766f731e41fda1e45e8230520'
def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for x in iter(lambda:f.read(65536),b''):h.update(x)
 return h.hexdigest()
def command(args,timeout=35):
 p=subprocess.run(args,capture_output=True,timeout=timeout);assert p.returncode==0,(args[0],p.returncode,p.stderr[-2000:]);return p
def docker(*args):return command(['docker',*map(str,args)])
def save(p,v):
 assert not p.exists();p.write_text(json.dumps(v,indent=2)+'\n')
def guard(start=False):
 available=int(next(x.split()[1] for x in Path('/proc/meminfo').read_text().splitlines() if x.startswith('MemAvailable:')))*1024;d=os.statvfs('/');assert available>=500000000+(1664*1024**2 if start else 0) and d.f_bavail/d.f_blocks>=.15;return {'at':time.time(),'memory_available_bytes':available,'root_free_ratio':d.f_bavail/d.f_blocks}
def unchanged(meta):
 assert all(p.is_file() and not p.is_symlink() and p.stat().st_size==row['bytes'] and sha(p)==row['sha256'] for row in meta['client_files'] for p in [S/row['path']]);assert sha(E/'corpus.json')==meta['corpus_sha256'] and sha(E/'validator.py')==meta['validator_sha256']
meta=json.loads((E/'inputs.json').read_bytes());state=dict(x.split('=',1) for x in command(['systemctl','show',OWNER,'--property=MainPID,ActiveState,InvocationID']).stdout.decode().splitlines());assert int(state['MainPID'])==os.getpid() and state['ActiveState']=='active' and not (E/'run-started.json').exists() and not RAM.exists();deadline=time.monotonic()+1800
while True:
 assert time.monotonic()<deadline,'Original native admission timeout; audit, never restart'
 try:
  with (B/'evidence/shared-resource-coordination.lock').open('a') as lock:
   fcntl.flock(lock.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB);others=command(['systemctl','list-units','--state=active','--plain','--no-legend','--no-pager','pr13-cap-*','pr13-pool-segment-*']).stdout.decode().splitlines();assert not [x for x in others if x.split()[0]!=OWNER+'.service'];guard(True);unchanged(meta);RAM.mkdir(mode=0o777);command(['mount','-t','tmpfs','-o','size=134217728,mode=0777,nosuid,nodev',OWNER,str(RAM)]);save(E/'run-started.json',{'owner':OWNER,'MainPID':os.getpid(),'invocation_id':state['InvocationID'],'boot_id':Path('/proc/sys/kernel/random/boot_id').read_text().strip(),'source_sha':meta['source_sha'],'input_sha256':sha(E/'inputs.json'),'at':time.time()});break
 except (AssertionError,BlockingIOError):time.sleep(5)
cid=None;result={'ok':False,'attempt':A,'source_sha':meta['source_sha'],'development_smoke':False,'formal_RENDER_accepted':False,'MAIN_accepted':False}
try:
 cid=docker('create','--name',OWNER,'--label','codex.owner='+OWNER,'--network','none','--memory','1536m','--memory-swap','1536m','--cpus','1','--read-only','--tmpfs','/tmp:rw,nosuid,nodev,size=134217728','--shm-size','128m','--user','1000:1000','-e','HOME=/tmp/render-home','-e','XDG_DATA_HOME=/tmp/render-data','-e','XDG_CONFIG_HOME=/tmp/render-config','-e','XDG_CACHE_HOME=/tmp/render-cache','-e','FANTASYCARD_SERVER_URL=http://127.0.0.1:1','-e','PR13_INFORMATION_RENDER_SOURCE='+meta['source_sha'],'-e','PR13_INFORMATION_RENDER_OUTPUT=/output','-e','PR13_INFORMATION_RENDER_INPUT=/corpus.json','-e','PR13_INFORMATION_RENDER_LOCALE=zh-CN','-e','PR13_INFORMATION_RENDER_MODE=formal','-v',str(S/'client')+':/client:ro','-v',str(E/'corpus.json')+':/corpus.json:ro','-v',str(RAM)+':/output','-v',str(E/'validator.py')+':/validator.py:ro',IMAGE,'sleep','3660').stdout.decode().strip()
 def owned():
  v=json.loads(docker('inspect',cid).stdout)[0];assert v['Id']==cid and v['Config']['Labels']['codex.owner']==OWNER;return v
 owned();docker('start',cid);log=(RAM/'engine.log').open('xb');process=subprocess.Popen(['docker','exec',cid,'xvfb-run','-a','-s','-screen 0 1920x1080x24 -nolisten tcp','godot','--path','/client','--display-driver','x11','--rendering-method','gl_compatibility','--audio-driver','Dummy','--max-fps','30','--windowed','res://tests/pr13_pool_information_and_default_render.tscn'],stdout=log,stderr=subprocess.STDOUT);until=time.monotonic()+3600
 while process.poll() is None:
  assert time.monotonic()<until and owned()['State']['Running'];sample=guard()
  with (E/'resources.jsonl').open('a') as f:f.write(json.dumps(sample)+'\n')
  time.sleep(2)
 log.flush();log.close();text=(RAM/'engine.log').read_text(errors='replace');result.update(exit_code=process.returncode,oom_killed=owned()['State']['OOMKilled'],strict_engine_log_clean=not any(x.lower() in text.lower() for x in ('ERROR:','SCRIPT ERROR','Parse Error','Failed to load script','ObjectDB instances were leaked','resources still in use')))
 assert result['exit_code']==0 and not result['oom_killed'] and result['strict_engine_log_clean'],text[-3000:]
 validation=command(['docker','exec',cid,'python3','/validator.py','--corpus','/corpus.json','--result','/output/native-result.json','--output','/output/independent-validation.json']);(RAM/'validator.stdout.original.log').write_bytes(validation.stdout);(RAM/'validator.stderr.original.log').write_bytes(validation.stderr);v=json.loads(validation.stdout);assert v['ok'] and v['actual_observations']==486 and v['original_PNGs']==27;result.update(ok=True,rows=486,PNGs=27,independent_control_validation_passed=True)
except Exception as error:result.update(error=type(error).__name__,detail=str(error),failed_originals_retained=True)
finally:
 if 'process' in globals() and process.poll() is None:
  process.terminate()
  try:process.wait(timeout=5)
  except subprocess.TimeoutExpired:process.kill();process.wait(timeout=5)
 if 'log' in globals() and not log.closed:log.flush();log.close()
 if cid:
  info=owned()
  if info['State']['Running']:docker('stop','--time','10',cid)
  assert not owned()['State']['Running'];docker('rm',cid);result['owned_container_removed']=True
 unchanged(meta);result['source_and_corpus_unchanged']=True
 with urllib.request.urlopen('http://127.0.0.1:8080/health/ready',timeout=10) as h:assert h.status==200
 save(E/'run-result.json',result)
print(json.dumps(result));raise SystemExit(0 if result['ok'] else 1)
