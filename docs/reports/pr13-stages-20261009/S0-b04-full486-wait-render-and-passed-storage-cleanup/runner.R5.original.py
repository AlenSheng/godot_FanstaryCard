"""Bounded real-pixel matrix admitted between frozen T03 sampling units."""
import hashlib,json,os,subprocess,time,urllib.request
from pathlib import Path
BASE=Path('/home/ubuntu/pr13-acceptance-20261009');A='B04-wait-boundary-render-r5-20261012';E=BASE/'evidence'/A;OWNER='pr13-pool-segment-b04-wait-boundary-r5-20261012';D=BASE/'work/cap-RENDER-r7-inputs';RAM=Path('/dev/shm/pr13-'+A);IMAGE='sha256:180f524270f6ac28d2fe0ff29707fb392387d7b766f731e41fda1e45e8230520';plan=json.loads((E/'plan.original.json').read_bytes());SOURCE=plan['source_sha']
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def save(p,v):assert not p.exists();p.write_bytes((json.dumps(v,indent=2)+'\n').encode())
def run(a,timeout=40,check=True):
 r=subprocess.run([str(x) for x in a],capture_output=True,timeout=timeout)
 if check:r.check_returncode()
 return r
def docker(*a,**kw):return run(['docker',*a],**kw)
def guard(start=False):
 memory=int(next(l.split()[1] for l in Path('/proc/meminfo').read_text().splitlines() if l.startswith('MemAvailable:')))*1024;s=os.statvfs('/');assert memory>=500000000+(1664*1024**2 if start else 0) and s.f_bavail/s.f_blocks>=.15
 with urllib.request.urlopen('http://127.0.0.1:8080/health/ready',timeout=10) as h:assert h.status==200
 return {'at':time.time(),'memory_available_bytes':memory,'root_free_fraction':s.f_bavail/s.f_blocks,'health_status':200}
def frozen(git_check=False):
 assert sha(D/'manifest.json')==plan['shared_source_manifest_sha256'];meta=json.loads((D/'manifest.json').read_bytes())
 for row in meta['files']:
  p=D/row['path'];assert p.resolve().is_relative_to(D) and not p.is_symlink() and p.stat().st_size==row['bytes'] and sha(p)==row['sha256']
 for filename,key in [('fixture.original.gd','fixture_sha256'),('fixture.original.tscn','scene_sha256'),('card-view-current.original.gd','current_card_view_sha256'),('parse-probe.original.gd','parse_probe_sha256'),('parse-probe.original.tscn','parse_scene_sha256')]:assert sha(E/filename)==plan[key]
 proof={'ok':True,'source_sha':SOURCE,'frozen_input_members':len(meta['files']),'shared_source_manifest_sha256':plan['shared_source_manifest_sha256'],'external_fixture_and_scene_sha256':[plan['fixture_sha256'],plan['scene_sha256']],'source_bytes_unchanged':True,'owned_current_card_view_byte_overlay':{'path':'client/ui/card_view.gd','sha256':plan['current_card_view_sha256'],'git_blob_sha1':plan['current_card_view_git_blob_sha1'],'only_CRLF_to_current_Git_LF_difference':True},'MAIN_accepted':False}
 if git_check:
  R=Path('/opt/fantasycard-github');command=['git','-c','safe.directory='+str(R),'-C',str(R)];assert not run([*command,'diff','--name-only',meta['product_source_sha'],SOURCE,'--','client']).stdout.strip();entries=run([*command,'ls-tree','-r',SOURCE,'--','client']).stdout.decode().splitlines();checked=[];excluded=[]
  for line in entries:
   header,name=line.split('\t');mode,kind,oid=header.split();assert kind=='blob' and mode in ('100644','100755')
   if name=='client/tests/pr13_cap_effective_render.gd':excluded.append({'path':name,'reason':'Existing declared unrelated cap fixture override; this scene does not execute it'});continue
   p=E/'card-view-current.original.gd' if name=='client/ui/card_view.gd' else D/name;assert p.is_file() and not p.is_symlink();data=p.read_bytes();assert hashlib.sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest()==oid;checked.append({'path':name,'git_blob_sha1':oid})
  assert len(checked)>=2100 and len(excluded)==1;proof.update(current_client_git_objects_verified=len(checked),declared_unrelated_test_override=excluded,verified_git_objects=checked)
 return proof
def sample_slot_free():
 controller=BASE/'evidence/T03-conditioned-full-r2-20261012/controller.original.py';r=run(['python3',controller,'status']);st=json.loads(r.stdout);units=run(['systemctl','list-units','--state=running','--no-legend','--plain','--no-pager','pr13-cap-*','pr13-pool-segment-*']).stdout.decode().splitlines();others=[l for l in units if l.split()[0]!=OWNER+'.service'];return st['current'] is None and not others,st['completed_G_verified_units']
state=dict(l.split('=',1) for l in run(['systemctl','show',OWNER,'--property=MainPID,ActiveState,InvocationID']).stdout.decode().splitlines());assert state['MainPID']==str(os.getpid()) and state['ActiveState']=='active';save(E/'started.original.json',{'PID':os.getpid(),'state':state,'boot_id':Path('/proc/sys/kernel/random/boot_id').read_text().strip(),'at':time.time(),'source_sha':SOURCE});cid=None;result={'ok':False,'source_sha':SOURCE,'attempt':A,'candidate_activation':False,'MAIN_accepted':False};overlay=False;memory_mount=False;child=None;log=None
def owned():
 v=json.loads(docker('inspect',cid).stdout)[0];assert v['Id']==cid and v['Name']=='/'+OWNER and v['Config']['Labels'].get('codex.owner')==OWNER;return v
try:
 proof=frozen(True);save(E/'source-proof.original.json',proof);until=time.monotonic()+3600
 while True:
  free,done=sample_slot_free()
  try:observation=guard(True);resources=True
  except AssertionError:resources=False
  with (E/'admission.original.jsonl').open('a') as f:f.write(json.dumps({'at':time.time(),'sampling_slot_free':free,'completed_T03_G_units':done,'render_resource_admission':resources})+'\n')
  if free and resources:break
  assert time.monotonic()<until,'Resource admission deadline; no native restart';time.sleep(5)
 assert not RAM.exists();RAM.mkdir();run(['mount','-t','tmpfs','-o','size=134217728,mode=0777,nosuid,nodev',OWNER,RAM]);memory_mount=True
 for name in ('upper','overlay-work','client','outputs'):(RAM/name).mkdir(mode=0o777);(RAM/name).chmod(0o777)
 run(['mount','-t','overlay','overlay','-o','lowerdir='+str(D/'client')+',upperdir='+str(RAM/'upper')+',workdir='+str(RAM/'overlay-work'),RAM/'client']);overlay=True
 protected=E/'original-pixels';protected.mkdir(mode=0o777);protected.chmod(0o777);(RAM/'client/ui/card_view.gd').write_bytes((E/'card-view-current.original.gd').read_bytes());(RAM/'client/tests/b04_wait_boundary_frames_r1.gd').write_bytes((E/'fixture.original.gd').read_bytes());(RAM/'client/tests/b04_wait_boundary_frames_r1.tscn').write_bytes((E/'fixture.original.tscn').read_bytes());(RAM/'client/tests/b04_wait_parse_probe.gd').write_bytes((E/'parse-probe.original.gd').read_bytes());(RAM/'client/tests/b04_wait_parse_probe.tscn').write_bytes((E/'parse-probe.original.tscn').read_bytes());save(E/'native-admitted.original.json',{'guard':guard(),'completed_T03_G_units_before_render':done,'scene':'res://tests/b04_wait_boundary_frames_r1.tscn','original_lower_snapshot_readonly':True,'RAM_overlay_for_external_fixture_and_generated_caches':True})
 assert docker('inspect',OWNER,check=False).returncode!=0;cid=docker('create','--name',OWNER,'--label','codex.owner='+OWNER,'--network','none','--memory','1536m','--memory-swap','1536m','--cpus','1','--read-only','--tmpfs','/tmp:rw,nosuid,nodev,size=134217728','--shm-size','128m','--user','1000:1000','-e','HOME=/tmp/render-home','-e','XDG_DATA_HOME=/tmp/render-data','-e','XDG_CONFIG_HOME=/tmp/render-config','-e','XDG_CACHE_HOME=/tmp/render-cache','-e','FANTASYCARD_SERVER_URL=http://127.0.0.1:1','-e','FANTASYCARD_ART_EVIDENCE=/output','-e','PR13_SOURCE_SHA='+SOURCE,'-e','PR13_ORIGINAL_PIXELS=/original-pixels','-v',str(RAM/'client')+':/client:ro','-v',str(RAM/'outputs')+':/output','-v',str(protected)+':/original-pixels',IMAGE,'sleep','1200').stdout.decode().strip();owned();save(E/'container-created.original.json',{'Id':cid,'owner':OWNER,'image':IMAGE,'network':'none','memory_mib':1536});docker('start',cid)
 def phase(name,command,deadline):
  global child,log
  log=(RAM/'outputs'/(name+'.original.log')).open('xb');child=subprocess.Popen(command,stdout=log,stderr=subprocess.STDOUT);until=time.monotonic()+deadline
  while child.poll() is None:
   assert time.monotonic()<until,'Frozen native deadline';guard();assert sum(p.stat().st_size for p in (RAM/'outputs').rglob('*') if p.is_file())<64*1024**2;time.sleep(2)
  log.close();code=child.returncode;save(E/(name+'-exit.original.json'),{'exit_code':code,'deadline_seconds':deadline});assert code==0,name+' failed'
 phase('parse',['docker','exec',cid,'godot','--headless','--path','/client','res://tests/b04_wait_parse_probe.tscn'],120)
 phase('render',['docker','exec',cid,'xvfb-run','-a','-s','-screen 0 1920x1080x24 -nolisten tcp','godot','--path','/client','--display-driver','x11','--rendering-method','gl_compatibility','--audio-driver','Dummy','--max-fps','30','--windowed','res://tests/b04_wait_boundary_frames_r1.tscn'],900)
 native=json.loads((RAM/'outputs/native-result.json').read_bytes());rows=native['observations'];expected={(h,l,(x,y),f,d,c) for h in ('Mage','Priest','Guardian') for l in ('zh-CN','en') for x,y in ((1920,1080),(1280,720),(960,540)) for f in (30,60,144) for d in (0,100,300) for c in ('PR13-B04.3-T01','PR13-B04.3-T02','PR13-B04.3-T03')};keys=[(r['hero'],r['language'],tuple(r['resolution']),r['fps_cap'],r['controlled_response_delay_ms'],r['case_id']) for r in rows];assert len(rows)==len(set(keys))==486 and set(keys)==expected and all(r['passed'] for r in rows);assert native['ok'] and not native['failures'] and native['source_sha']==SOURCE and native['display_driver']!='headless';pngs=list(protected.glob('*.png'));assert len(pngs)==18;eligible=[r for r in rows if r['screenshot']];assert len(eligible)==18 and {r['screenshot'] for r in eligible}=={p.name for p in pngs};assert all((protected/r['screenshot']).stat().st_size==r['actual']['original_pixel_bytes'] and sha(protected/r['screenshot'])==r['actual']['original_pixel_SHA256'] and r['actual']['original_pixel_copied_immediately_after_successful_capture'] for r in eligible);logs='\n'.join(p.read_text(errors='replace') for p in (RAM/'outputs').glob('*.original.log'));assert not any(m.lower() in logs.lower() for m in ('SCRIPT ERROR','Parse Error','Failed to load script','ObjectDB instances were leaked','resources still in use'));assert not owned()['State']['OOMKilled'];result.update(ok=True,native_clean=True,original_rows_passed=486,screenshots=18,display_driver=native['display_driver'],adapter=native['adapter'],oom_killed=False,full_matrix_verified=True,source_inputs_match_git=True,visual_review_pending=True,canonical_RENDER_profile_closed=0)
except Exception as error:result.update(error=type(error).__name__,detail=str(error),traceback=__import__('traceback').format_exc(),failed_originals_retained=True)
finally:
 if child is not None and child.poll() is None:child.terminate();child.wait(timeout=10)
 if log is not None and not log.closed:log.close()
 if memory_mount:
  try:
   destination=E/'retained-native-outputs';destination.mkdir();copied=[]
   for p in sorted((RAM/'outputs').rglob('*')):
    assert not p.is_symlink()
    if p.is_file():
     target=destination/p.relative_to(RAM/'outputs');target.parent.mkdir(parents=True,exist_ok=True);data=p.read_bytes();target.write_bytes(data);assert target.read_bytes()==data;copied.append({'path':target.relative_to(E).as_posix(),'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()})
   save(E/'retained-output-manifest.original.json',{'files':copied,'captured_before_container_teardown':True});result['original_outputs_preserved_before_teardown']=True
  except Exception as error:result['output_preservation_error']=str(error)
 if cid:
  try:
   v=owned()
   if v['State']['Running']:docker('stop','--time','10',cid)
   owned();docker('rm',cid);result['owned_container_removed']=True
  except Exception as error:result['owned_cleanup_error']=str(error)
 try:frozen();result['shared_source_and_fixture_unchanged']=True
 except Exception as error:result.update(shared_source_and_fixture_unchanged=False,source_error=str(error))
 if overlay:
  try:run(['umount',RAM/'client']);result['owned_overlay_unmounted']=True
  except Exception as error:result['overlay_unmount_error']=str(error)
 result['RAM_outputs_and_generated_upper_retained_for_G']=memory_mount;result['ok']=result['ok'] and result.get('original_outputs_preserved_before_teardown') is True and result.get('owned_container_removed') is True and result.get('owned_overlay_unmounted') is True and result.get('shared_source_and_fixture_unchanged') is True;save(E/'result.original.json',result)
print(json.dumps(result));raise SystemExit(0 if result['ok'] else 1)
