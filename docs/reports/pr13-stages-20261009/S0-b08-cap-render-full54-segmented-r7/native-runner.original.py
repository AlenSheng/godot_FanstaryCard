"""One unchanged original vector set at one locale/size and all three FPS caps."""
import hashlib,json,os,subprocess,sys,time,urllib.request
from pathlib import Path
B=Path('/home/ubuntu/pr13-acceptance-20261009');SLUG=sys.argv[1];A=SLUG+'-20261012';OWNER='pr13-cap-'+A;E=B/'evidence'/A;D=B/'work/cap-RENDER-r7-inputs';RAM=Path('/dev/shm/pr13-'+A);IMAGE='sha256:180f524270f6ac28d2fe0ff29707fb392387d7b766f731e41fda1e45e8230520'
plan=json.loads((D/'plan.json').read_bytes());segment=next(s for s in plan['segments'] if s['slug']==SLUG)
def cmd(args,timeout=35):
 p=subprocess.run(args,capture_output=True,timeout=timeout);assert p.returncode==0,(args[0],p.returncode,p.stderr[-1200:]);return p
def docker(*args):return cmd(['docker',*map(str,args)])
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def save(p,v):assert not p.exists();p.write_text(json.dumps(v,indent=2)+'\n')
def freeze():
 meta=json.loads((D/'manifest.json').read_bytes())
 for row in meta['files']:
  p=D/row['path'];assert not p.is_symlink() and p.stat().st_size==row['bytes'] and sha(p)==row['sha256']
 return meta
def guard(start=False):
 memory=int(next(x.split()[1] for x in Path('/proc/meminfo').read_text().splitlines() if x.startswith('MemAvailable:')))*1024;s=os.statvfs('/');assert memory>=500000000+(1664*1024**2 if start else 0) and s.f_bavail/s.f_blocks>=.15
 with urllib.request.urlopen('http://127.0.0.1:8080/health/ready',timeout=10) as h:assert h.status==200
 return {'memory_available_bytes':memory,'root_free_ratio':s.f_bavail/s.f_blocks,'production_health_status':200}
state=dict(x.split('=',1) for x in cmd(['systemctl','show',OWNER,'--property=MainPID,ActiveState,InvocationID']).stdout.decode().splitlines());assert int(state['MainPID'])==os.getpid() and state['ActiveState']=='active';meta=freeze();assert not RAM.exists();guard(True);RAM.mkdir(mode=0o777);cmd(['mount','-t','tmpfs','-o','size=134217728,mode=0777,nosuid,nodev',OWNER,str(RAM)]);save(E/'run-started.json',{'MainPID':os.getpid(),'invocation_id':state['InvocationID'],'boot_id':Path('/proc/sys/kernel/random/boot_id').read_text().strip(),'at':time.time(),'input_manifest_sha256':sha(D/'manifest.json'),'guard':guard(),'segment':segment})
cid=None;result={'ok':False,'segment':segment,'production_source_sha':plan['source_sha'],'MAIN_accepted':False,'RENDER_acceptance_granted':False}
try:
 assert subprocess.run(['docker','inspect',OWNER],capture_output=True).returncode!=0
 cid=docker('create','--name',OWNER,'--label','codex.owner='+OWNER,'--network','none','--memory','1536m','--memory-swap','1536m','--cpus','1','--read-only','--tmpfs','/tmp:rw,nosuid,nodev,size=134217728','--shm-size','128m','--user','1000:1000','-e','HOME=/tmp/render-home','-e','XDG_DATA_HOME=/tmp/render-data','-e','XDG_CONFIG_HOME=/tmp/render-config','-e','XDG_CACHE_HOME=/tmp/render-cache','-e','FANTASYCARD_SERVER_URL=http://127.0.0.1:1','-e','FANTASYCARD_ART_EVIDENCE=/output','-e','PR13_CAP_SEGMENT_LANGUAGE='+segment['language'],'-e','PR13_CAP_SEGMENT_WIDTH='+str(segment['resolution'][0]),'-v',str(D/'client')+':/client:ro','-v',str(RAM)+':/output',IMAGE,'sleep','960').stdout.decode().strip()
 def owned():
  v=json.loads(docker('inspect',cid).stdout)[0];assert v['Id']==cid and v['Name']=='/'+OWNER and v['Config']['Labels']['codex.owner']==OWNER;return v
 owned();docker('start',cid);log=(RAM/'engine.log').open('xb');p=subprocess.Popen(['docker','exec',cid,'xvfb-run','-a','-s','-screen 0 1920x1080x24 -nolisten tcp','godot','--path','/client','--display-driver','x11','--rendering-method','gl_compatibility','--audio-driver','Dummy','--max-fps','30','--windowed','res://tests/pr13_cap_effective_t0'+str(segment['case_number'])+'.tscn'],stdout=log,stderr=subprocess.STDOUT);until=time.monotonic()+900
 while p.poll() is None:
  assert time.monotonic()<until,'Frozen 900s segment deadline';sample=guard();assert sum(x.stat().st_size for x in RAM.rglob('*') if x.is_file())<128*1024**2
  with (E/'resources.jsonl').open('a') as f:f.write(json.dumps(sample)+'\n')
  time.sleep(2)
 log.close();text=(RAM/'engine.log').read_text(errors='replace');native=json.loads((RAM/'native-result.json').read_bytes()) if (RAM/'native-result.json').exists() else {};result.update(exit_code=p.returncode,oom_killed=owned()['State']['OOMKilled'],native=native,strict_engine_log_clean=not any(x.lower() in text.lower() for x in ('SCRIPT ERROR','Parse Error','Failed to load script','ObjectDB instances were leaked','resources still in use')))
 observations=native.get('observations',[]);matrix={(r['language'],tuple(r['resolution']),r['fps_cap']) for r in observations}
 result['ok']=p.returncode==0 and not result['oom_killed'] and result['strict_engine_log_clean'] and native.get('ok') is True and native.get('diagnostic_only') is False and len(observations)==3 and matrix=={(segment['language'],tuple(segment['resolution']),f) for f in (30,60,144)} and all(r['passed'] for r in observations) and native['native_witness_renders']==segment['expected_witnesses'] and native['additional_inactive_contexts']==segment['expected_inactive'] and len(list(RAM.glob('*.png')))==segment['expected_pngs']
except Exception as error:result.update(error=type(error).__name__,detail=str(error),failed_originals_retained=True)
finally:
 if 'p' in globals() and p.poll() is None:p.terminate();p.wait(timeout=10)
 if 'log' in globals() and not log.closed:log.close()
 if cid:
  info=owned()
  if info['State']['Running']:docker('stop','--time','10',cid)
  owned();docker('rm',cid);result['owned_container_removed']=True
 freeze();result['frozen_inputs_unchanged']=True;result['ok']=result['ok'] and result.get('owned_container_removed') is True;save(E/'run-result.json',result)
print(json.dumps({'ok':result['ok'],'segment':SLUG,'native_rows':len(result.get('native',{}).get('observations',[])),'G_backup_pending':True}));raise SystemExit(0 if result['ok'] else 1)
