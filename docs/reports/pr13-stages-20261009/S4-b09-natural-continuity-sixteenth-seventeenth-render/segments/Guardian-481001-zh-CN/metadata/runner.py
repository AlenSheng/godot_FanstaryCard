import fcntl,hashlib,json,os,subprocess,time,urllib.request
from pathlib import Path
B=Path('/home/ubuntu/pr13-acceptance-20261009');G=Path('/opt/fantasycard-github');A='b09-continuity-natural-render-guardian-481001-zh-cn-r1-20261011';OWNER='pr13-cap-'+A;E=B/'evidence'/A;W=B/'work'/A;S=B/'work/b09-continuity-natural-render-smoke-r4-20261011/source';RAM=Path('/dev/shm/pr13-'+A);OLD=B/'work/b09-legal-route-receive-r4-20261011/source';READER='8c6bb777e2d3aea333b6917dcce8f339c2f494c3';NATIVE=Path('/dev/shm/pr13-b09-continuity-formal-guardian-481001-r1-20261011/native/Guardian/render-vectors.jsonl')
IMAGE='sha256:180f524270f6ac28d2fe0ff29707fb392387d7b766f731e41fda1e45e8230520'
def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for x in iter(lambda:f.read(65536),b''):h.update(x)
 return h.hexdigest()
def command(args,timeout=30):
 env=os.environ.copy()
 if args[0]=='git':
  args=['/usr/bin/git','-c','safe.directory=/opt/fantasycard-github',*args[1:]]
  env={k:v for k,v in env.items() if not k.startswith('GIT_')}
 r=subprocess.run(args,capture_output=True,env=env,timeout=timeout)
 if r.returncode!=0:
  if args[0]=='/usr/bin/git':
   p=E/'git-read-failure-original.json';assert not p.exists();p.write_text(json.dumps({'args':args,'exit_code':r.returncode,'stdout':r.stdout.decode(errors='replace'),'stderr':r.stderr.decode(errors='replace')},indent=2)+'\n')
  r.check_returncode()
 return r
def docker(*a):return command(['sudo','-n','docker',*map(str,a)])
def save(p,v):
 assert not p.exists();p.write_text(json.dumps(v,indent=2)+'\n')
def health():
 with urllib.request.urlopen('http://127.0.0.1:8080/health/ready',timeout=10) as h:assert h.status==200
def guard(start=False):
 mem=next(int(x.split()[1])*1024 for x in Path('/proc/meminfo').read_text().splitlines() if x.startswith('MemAvailable:'));s=os.statvfs(B);assert mem>=500000000+(1600*1024**2 if start else 0) and s.f_bavail/s.f_blocks>=.15;health();return {'at':time.time(),'memory_available_bytes':mem,'root_free_ratio':s.f_bavail/s.f_blocks}
def owned(cid):
 v=json.loads(docker('inspect',cid).stdout)[0];assert v['Id']==cid and v['Config']['Labels']['codex.owner']==OWNER;return v
state=dict(x.split('=',1) for x in command(['systemctl','show',OWNER,'--property=MainPID,ActiveState,InvocationID']).stdout.decode().splitlines());assert int(state['MainPID'])==os.getpid() and state['ActiveState']=='active' and os.environ.get('PR13_CONTINUITY_LEASE')==OWNER
assert S.exists() and not RAM.exists() and not (E/'run-started.json').exists();deadline=time.monotonic()+3600
changed=command(['git','-C',str(G),'diff','--name-only','5b66fc0cb601a7bf7a3b2439daea1a3a9db0f438',READER,'--','client']).stdout.decode().splitlines()
assert set(changed)=={'client/tests/test_monster_pool_legal_route_vectors.gd','client/tests/pr13_pool_continuity_natural_render.gd','client/tests/pr13_pool_continuity_natural_render.tscn'},'Cached and current product client must match; only explicit test fixtures may differ'
old_inputs=json.loads((B/'evidence/b09-legal-route-receive-r4-20261011/inputs.json').read_bytes())
assert all(sha(OLD/name)==digest for name,digest in old_inputs['client_files'].items()),'Original cached reader source changed'
while True:
 assert time.monotonic()<deadline,'Smoke admission deadline; originals retained'
 try:
  with (B/'evidence/shared-resource-coordination.lock').open('a') as lock:
   fcntl.flock(lock.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
   active=command(['systemctl','list-units','--state=active','--plain','--no-legend','--no-pager','pr13-cap-*','pr13-pool-segment-*']).stdout.decode().splitlines();assert not [x for x in active if x.split()[0]!=OWNER+'.service'];guard(True)
   RAM.mkdir(mode=0o777);command(['sudo','-n','mount','-t','tmpfs','-o','size=67108864,mode=0777,nosuid,nodev',OWNER,str(RAM)])
   save(E/'run-started.json',{'owner':OWNER,'MainPID':os.getpid(),'invocation_id':state['InvocationID'],'boot_id':Path('/proc/sys/kernel/random/boot_id').read_text().strip(),'at':time.time(),'reader_source_sha':READER,'original_native_source_sha':'0d56ceccf526f6ae8973f57da152d67faf93a5d5'});break
 except (AssertionError,BlockingIOError):time.sleep(5)
files=json.loads((B/'evidence/b09-continuity-natural-render-smoke-r4-20261011/inputs.json').read_bytes())['client_files'];assert all(sha(S/name)==digest for name,digest in files.items())
vectors_sha=sha(NATIVE);vectors=[json.loads(x) for x in NATIVE.read_text().splitlines()];assert len(vectors)==9 and {x['capacity'] for x in vectors}=={3,5,8} and all(x['hero']=='Guardian' and x['seed']==481001 and x['source']=='0d56ceccf526f6ae8973f57da152d67faf93a5d5' for x in vectors)
save(E/'inputs.json',{'reader_source_sha':READER,'native_source_sha':'0d56ceccf526f6ae8973f57da152d67faf93a5d5','client_files':files,'original_vector_path':str(NATIVE),'original_vector_sha256':vectors_sha,'original_vectors':9,'matrix_mode':'formal','locale':'zh-CN','resolutions':[[1920,1080],[1280,720],[960,540]],'frame_caps':[30,60,144],'controlled_delays_ms':[0,250,1000],'native_numeric_routes_regenerated':False})
cid=None;result={'ok':False,'attempt':A,'reader_source_sha':READER,'native_source_sha':'0d56ceccf526f6ae8973f57da152d67faf93a5d5','development_smoke':False,'MAIN_accepted':False,'formal_RENDER_accepted':False}
try:
 cid=docker('create','--name',OWNER,'--label','codex.owner='+OWNER,'--network','none','--memory','1536m','--memory-swap','1536m','--cpus','1','--read-only','--tmpfs','/tmp:rw,nosuid,nodev,size=134217728','--shm-size','128m','--user','1000:1000','-e','HOME=/tmp/render-home','-e','XDG_DATA_HOME=/tmp/render-data','-e','XDG_CONFIG_HOME=/tmp/render-config','-e','XDG_CACHE_HOME=/tmp/render-cache','-e','FANTASYCARD_SERVER_URL=http://127.0.0.1:1','-e','PR13_CONTINUITY_RENDER_SOURCE='+READER,'-e','PR13_CONTINUITY_RENDER_OUTPUT=/output','-e','PR13_CONTINUITY_RENDER_VECTORS=/vectors.jsonl','-e','PR13_CONTINUITY_RENDER_LOCALE=zh-CN','-e','PR13_CONTINUITY_RENDER_MODE=formal','-v',str(S/'client')+':/client:ro','-v',str(NATIVE)+':/vectors.jsonl:ro','-v',str(RAM)+':/output',IMAGE,'sleep','960').stdout.decode().strip();owned(cid);result['owned_container_id']=cid;docker('start',cid);until=time.monotonic()+900
 log=(RAM/'engine.log').open('xb');native_process=subprocess.Popen(['sudo','-n','docker','exec',cid,'xvfb-run','-a','-s','-screen 0 1920x1080x24 -nolisten tcp','godot','--path','/client','--display-driver','x11','--rendering-method','gl_compatibility','--audio-driver','Dummy','--max-fps','30','--windowed','res://tests/pr13_pool_continuity_natural_render.tscn'],stdout=log,stderr=subprocess.STDOUT)
 while True:
  info=owned(cid)
  if native_process.poll() is not None:break
  assert info['State']['Running'],'Owned renderer parent exited unexpectedly'
  assert time.monotonic()<until,'Formal render segment deadline exceeded';sample=guard()
  with (E/'resources.jsonl').open('a') as f:f.write(json.dumps(sample)+'\n')
  time.sleep(3)
 log.flush();log.close();text=(RAM/'engine.log').read_text(errors='replace');native=json.loads((RAM/'native-result.json').read_bytes()) if (RAM/'native-result.json').exists() else {};clean=not any(x.lower() in text.lower() for x in ('SCRIPT ERROR','Parse Error','Failed to load script','ObjectDB instances were leaked','resources still in use'))
 result.update(exit_code=native_process.returncode,oom_killed=info['State']['OOMKilled'],strict_engine_log_clean=clean,native=native,screenshots=len(list(RAM.glob('*.png'))));result['ok']=result['exit_code']==0 and not result['oom_killed'] and clean and native.get('ok') is True and len(native.get('observations',[]))==243 and result['screenshots']==27
except Exception as e:result.update(error=type(e).__name__,detail=str(e),failed_originals_retained=True)
finally:
 if 'native_process' in globals() and native_process.poll() is None:
  native_process.terminate()
  try:native_process.wait(timeout=5)
  except subprocess.TimeoutExpired:native_process.kill();native_process.wait(timeout=5)
 if 'log' in globals() and not log.closed:log.flush();log.close()
 if cid:
  info=owned(cid)
  if info['State']['Running']:docker('stop','--time','10',cid)
  owned(cid);docker('rm',cid);result['owned_container_removed']=True
 result['client_sources_unchanged']=all(sha(S/name)==digest for name,digest in files.items());result['original_vectors_unchanged']=sha(NATIVE)==vectors_sha;result['ok']=result['ok'] and result['client_sources_unchanged'] and result['original_vectors_unchanged'];health();save(E/'run-result.json',result)
print(json.dumps({'ok':result['ok'],'attempt':A,'development_smoke':False,'exit_code':result.get('exit_code'),'normal_engine_shutdown_clean':result.get('strict_engine_log_clean'),'original_vectors':9,'native_result_observations':len(result.get('native',{}).get('observations',[])),'MAIN_accepted':False}));raise SystemExit(0 if result['ok'] else 1)
