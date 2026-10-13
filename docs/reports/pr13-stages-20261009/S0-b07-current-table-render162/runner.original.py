import hashlib,json,os,subprocess,time,urllib.request
from pathlib import Path
B=Path('/home/ubuntu/pr13-acceptance-20261009');A='B07-current-table-render-r1-20261013';E=B/'evidence'/A;W=B/'work'/A;OWNER='pr13-pool-segment-b07-current-table-r1-20261013';D=B/'work/cap-RENDER-r7-inputs';meta=json.loads((E/'inputs.original.json').read_bytes());IMAGE='sha256:180f524270f6ac28d2fe0ff29707fb392387d7b766f731e41fda1e45e8230520'
def write(p,v):assert not p.exists();p.write_bytes((json.dumps(v,indent=2)+'\n').encode())
def run(a,timeout=40,check=True):
 r=subprocess.run([str(x) for x in a],capture_output=True,timeout=timeout)
 if check:r.check_returncode()
 return r
def docker(*a,**kw):return run(['docker',*a],**kw)
def guard(start=False):
 s=os.statvfs('/');m=int(next(l.split()[1] for l in Path('/proc/meminfo').read_text().splitlines() if l.startswith('MemAvailable:')))*1024;assert m>=500000000+(1664*1024**2 if start else 0) and s.f_bavail/s.f_blocks>=.15
 with urllib.request.urlopen('http://127.0.0.1:8080/health/ready',timeout=10) as h:assert h.status==200
 return {'at':time.time(),'memory_available_bytes':m,'root_free_fraction':s.f_bavail/s.f_blocks,'health_status':200}
def frozen():
 assert hashlib.sha256((D/'manifest.json').read_bytes()).hexdigest()==meta['shared_source_manifest_sha256'];source=json.loads((D/'manifest.json').read_bytes())
 for r in source['files']:
  p=D/r['path'];assert not p.is_symlink() and p.stat().st_size==r['bytes'] and hashlib.sha256(p.read_bytes()).hexdigest()==r['sha256']
 for r in meta['files']:
  p=E/r['name'];assert p.stat().st_size==r['bytes'] and hashlib.sha256(p.read_bytes()).hexdigest()==r['sha256']
def current_Git():
 R='/opt/fantasycard-github';g=['git','-c','safe.directory='+R,'-C',R];assert not run([*g,'diff','--name-only',meta['shared_product_source_sha'],meta['source_sha'],'--','client']).stdout.strip();checked=0;source=json.loads((D/'manifest.json').read_bytes());by={r['path']:r for r in source['files']}
 for line in run([*g,'ls-tree','-r',meta['source_sha'],'--','client']).stdout.decode().splitlines():
  header,name=line.split('\t');mode,kind,oid=header.split();assert kind=='blob';raw=run([*g,'show',meta['source_sha']+':'+name]).stdout
  if name=='client/tests/pr13_cap_effective_render.gd':continue
  old=(D/name).read_bytes()
  if name=='client/ui/card_view.gd':assert old.replace(b'\r\n',b'\n')==raw and (E/'card-view-current.original.gd').read_bytes()==raw
  else:assert old==raw
  checked+=1
 assert checked>=2100;return checked
state=dict(l.split('=',1) for l in run(['systemctl','show',OWNER,'--property=MainPID,ActiveState,InvocationID']).stdout.decode().splitlines());assert state['MainPID']==str(os.getpid()) and state['ActiveState']=='active';write(E/'started.original.json',{'PID':os.getpid(),'state':state,'at':time.time()});cid=None;child=None;log=None;result={'ok':False,'source_sha':meta['source_sha'],'MAIN_accepted':False}
def owned():
 v=json.loads(docker('inspect',cid).stdout)[0];assert v['Id']==cid and v['Name']=='/'+OWNER and v['Config']['Labels']['codex.owner']==OWNER;return v
try:
 frozen();checked=current_Git();until=time.monotonic()+3600
 while True:
  st=json.loads(run(['python3',B/'evidence/T03-conditioned-full-r2-20261012/controller.original.py','status']).stdout);units=run(['systemctl','list-units','--state=running','--no-legend','--plain','--no-pager','pr13-cap-*','pr13-pool-segment-*']).stdout.decode().splitlines();others=[l for l in units if l.split()[0]!=OWNER+'.service']
  if st['current'] is None and not others:
   try:guard(True);break
   except AssertionError:pass
  assert time.monotonic()<until,'Admission timeout; inspect original handles';time.sleep(5)
 assert not W.exists();W.mkdir();run(['cp','-al',D/'client',W/'client'],timeout=90);client=W/'client';(client/'ui/card_view.gd').unlink();(client/'ui/card_view.gd').write_bytes((E/'card-view-current.original.gd').read_bytes())
 for source,dest in [('fixture.original.gd','b07_current_table_r1.gd'),('fixture.original.tscn','b07_current_table_r1.tscn'),('parse.original.gd','b07_current_table_parse.gd'),('parse.original.tscn','b07_current_table_parse.tscn')]:
  p=client/'tests'/dest;assert not p.exists();p.write_bytes((E/source).read_bytes())
 out=E/'persistent-native-outputs';out.mkdir(mode=0o777);out.chmod(0o777);write(E/'admitted.original.json',{'guard':guard(),'current_Git_client_objects_checked':checked,'full_required_rows':162,'render_deadline_seconds':900,'hardlinked_tree_readonly':True});assert docker('inspect',OWNER,check=False).returncode!=0;cid=docker('create','--name',OWNER,'--label','codex.owner='+OWNER,'--network','none','--memory','1536m','--memory-swap','1536m','--cpus','1','--read-only','--tmpfs','/tmp:rw,nosuid,nodev,size=134217728','--shm-size','128m','--user','1000:1000','-e','HOME=/tmp/render-home','-e','XDG_DATA_HOME=/tmp/render-data','-e','XDG_CONFIG_HOME=/tmp/render-config','-e','XDG_CACHE_HOME=/tmp/render-cache','-e','FANTASYCARD_SERVER_URL=http://127.0.0.1:1','-e','FANTASYCARD_ART_EVIDENCE=/output','-e','PR13_SOURCE_SHA='+meta['source_sha'],'-v',str(client)+':/client:ro','-v',str(out)+':/output',IMAGE,'sleep','1200').stdout.decode().strip();owned();docker('start',cid)
 def phase(name,command,budget):
  global child,log
  log=(out/(name+'.original.log')).open('xb');child=subprocess.Popen(command,stdout=log,stderr=subprocess.STDOUT);until=time.monotonic()+budget
  while child.poll() is None:
   assert time.monotonic()<until,'Original native deadline';guard();assert sum(p.stat().st_size for p in out.rglob('*') if p.is_file())<128*1024**2;time.sleep(2)
  log.close();write(E/(name+'-exit.original.json'),{'exit_code':child.returncode,'deadline_seconds':budget});assert child.returncode==0,name+' failed'
 phase('parse',['docker','exec',cid,'godot','--headless','--path','/client','res://tests/b07_current_table_parse.tscn'],120);phase('render',['docker','exec',cid,'xvfb-run','-a','-s','-screen 0 1920x1080x24 -nolisten tcp','godot','--path','/client','--display-driver','x11','--rendering-method','gl_compatibility','--audio-driver','Dummy','--verbose','--max-fps','30','--windowed','res://tests/b07_current_table_r1.tscn'],900);native=json.loads((out/'native-result.json').read_bytes());assert native['ok'] and len(native['observations'])==162 and not native['failures'];expected={(l,(x,y),f,d,c) for l in ['zh-CN','en'] for x,y in [(1920,1080),(1280,720),(960,540)] for f in [30,60,144] for d in [0,100,300] for c in ['PR13-B07.1-T01','PR13-B07.1-T02','PR13-B07.1-T03']};keys=[(r['language'],tuple(r['resolution']),r['fps_cap'],r['controlled_response_delay_ms'],r['case_id']) for r in native['observations']];assert len(set(keys))==162 and set(keys)==expected and all(r['passed'] for r in native['observations']);assert len(list(out.glob('*.png')))==18;logs='\n'.join(p.read_text(errors='replace') for p in out.glob('*.original.log'));assert not any(s.lower() in logs.lower() for s in ['SCRIPT ERROR','Parse Error','Failed to load script','ObjectDB instances were leaked','resources still in use']);result.update(ok=True,native_clean=True,source_inputs_match_git=True,current_Git_client_objects_checked=checked,actual_rows=162,original_PNGs=18,display_driver=native['display_driver'],adapter=native['adapter'],oom_killed=owned()['State']['OOMKilled'],visual_review_pending=True)
except Exception as error:result.update(error=type(error).__name__,detail=str(error),failed_originals_retained=True)
finally:
 if child is not None and child.poll() is None:child.terminate();child.wait(timeout=20)
 if log is not None and not log.closed:log.close()
 if cid:
  try:
   info=owned()
   if info['State']['Running']:docker('stop','--time','10',cid)
   owned();docker('rm',cid);result['owned_container_removed']=True
  except Exception as error:result['cleanup_error']=type(error).__name__
 try:frozen();result['shared_source_and_fixture_unchanged']=True
 except Exception:result['shared_source_and_fixture_unchanged']=False
 result['ok']=result['ok'] and result.get('owned_container_removed') is True and result['shared_source_and_fixture_unchanged'] and not result.get('oom_killed',False);write(E/'result.original.json',result)
print(json.dumps(result));raise SystemExit(0 if result['ok'] else 1)
