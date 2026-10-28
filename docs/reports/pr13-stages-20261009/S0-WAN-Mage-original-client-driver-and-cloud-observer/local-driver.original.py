"""One actual Windows Godot client; cloud observations and complete raw custody on G."""
import ctypes,hashlib,importlib.util,json,os,subprocess,sys,time,traceback
from pathlib import Path
import strict_compressed_TCP_NODELAY_cloud_transport as transport
B=Path(__file__).parent;G=Path('G:/PR13Evidence/WAN-Mage-natural3-r1');PROJECT=G/'client';OUT=G/'run';REMOTE='/home/ubuntu/pr13-WAN-Mage-observer-r1.original.py';EXE='G:/Program Files/Godot_v4.7.2-stable_win64.exe/Godot_v4.7.2-stable_win64.exe';STOP=OUT/'STOP'
class M(ctypes.Structure):_fields_=[('dwLength',ctypes.c_ulong),('dwMemoryLoad',ctypes.c_ulong),('ullTotalPhys',ctypes.c_ulonglong),('ullAvailPhys',ctypes.c_ulonglong),('ullTotalPageFile',ctypes.c_ulonglong),('ullAvailPageFile',ctypes.c_ulonglong),('ullTotalVirtual',ctypes.c_ulonglong),('ullAvailVirtual',ctypes.c_ulonglong),('ullAvailExtendedVirtual',ctypes.c_ulonglong)]
def memory():
 m=M();m.dwLength=ctypes.sizeof(m);assert ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m));return m.ullAvailPhys
def write(p,v):assert not p.exists();p.write_text(json.dumps(v,indent=2)+'\n',encoding='utf-8')
def cloud(action=None):
 start=time.monotonic();c=transport.connect()
 try:
  c.get_transport().set_keepalive(5);ch=c.get_transport().open_session(timeout=10);ch.settimeout(.2);ch.exec_command('sudo -n python3 '+REMOTE+(' assets' if action=='assets' else ''));ch.shutdown_write();out=bytearray();err=bytearray();deadline=time.monotonic()+(25 if action else 10)
  while not ch.exit_status_ready() or ch.recv_ready() or ch.recv_stderr_ready():
   assert time.monotonic()<deadline,'Readonly cloud observation timed out'
   if ch.recv_ready():out.extend(ch.recv(65536));assert len(out)<262144
   if ch.recv_stderr_ready():err.extend(ch.recv_stderr(65536));assert len(err)<32768
   if not ch.recv_ready() and not ch.recv_stderr_ready():time.sleep(.05)
  assert ch.recv_exit_status()==0 and not err,bytes(err).decode(errors='replace');v=json.loads(out);v['local_observation_elapsed_ms']=(time.monotonic()-start)*1000;return v
 finally:c.close()
def stop(reason):
 if not STOP.exists():STOP.write_text(reason+'\n')
def main():
 assert not OUT.exists();assert (PROJECT/'project.godot').read_bytes()==(PROJECT/'project.with-Game-import.original.godot').read_bytes();OUT.mkdir();project_manifest=json.loads((G/'source-manifest.original.json').read_bytes())
 for r in project_manifest['files']:
  data=(PROJECT/r['path']).read_bytes();assert len(data)==r['bytes'] and hashlib.sha256(data).hexdigest()==r['sha256']
 data=(B/'WAN_Mage_cloud_observer_R1.original.py').read_bytes();c=transport.connect()
 try:
  sf=c.open_sftp()
  try:
   with sf.open(REMOTE,'wx') as f:f.write(data)
   with sf.open(REMOTE,'rb') as f:assert f.read()==data
  finally:sf.close()
 finally:c.close()
 before=cloud('assets');write(OUT/'before-cloud.original.json',before);res=before['resources'];assert all(res.get(k) is not None for k in ['cpu','memory_available_bytes','disk_available']);assert res['cpu']<85 and res['memory_available_bytes']>=500000000 and res['disk_available']>=15 and before['health_status']==200;assert memory()>=500000000+64*1024**2
 env={k:v for k,v in os.environ.items() if not k.startswith('FANTASYCARD_')};values={'FANTASYCARD_SERVER_URL':'https://www.relicbound.cn','FANTASYCARD_LOAD_CLIENT_ID':'WANMageR1','FANTASYCARD_LOAD_RUN_ID':'WAN-Mage-natural3-r1','FANTASYCARD_LOAD_PROCESS_EPOCH':'WAN-Mage-r1-20261014','FANTASYCARD_LOAD_PROFILE':'cleared-extraction','FANTASYCARD_LOAD_MAX_CYCLES':'3','FANTASYCARD_LOAD_HERO_CLASS':'Mage','FANTASYCARD_LOAD_STRATEGY':'baseline_all_hand','FANTASYCARD_LOAD_SEED':'20260930','FANTASYCARD_LOAD_CYCLE_LIMIT_SECONDS':'600','FANTASYCARD_LOAD_REPORT':str(OUT/'player.original.json'),'FANTASYCARD_LOAD_STOP_FILE':str(STOP)};env.update(values)
 with (OUT/'engine.original.log').open('xb') as log:
  child=subprocess.Popen([EXE,'--headless','--max-fps','60','--path',str(PROJECT),'res://tests/gameplay_load_client.tscn'],stdout=log,stderr=subprocess.STDOUT,env=env,creationflags=subprocess.CREATE_NO_WINDOW);start=time.monotonic();write(OUT/'started.original.json',{'ok':True,'driver_PID':os.getpid(),'actual_Godot_PID':child.pid,'client_source_sha':project_manifest['source_sha'],'environment_parameters':values,'overall_seconds':600,'cleanup_seconds':120,'native_numerical_experiment_local':False});print(json.dumps({'phase':'ActualGodotPublicWANClientStarted','Godot_PID':child.pid}),flush=True);cause=None;windows={k:0 for k in ['cpu','disk_available','actor_wait','actor_missing']};next_monitor=0
  try:
   while child.poll() is None and time.monotonic()-start<600:
    if memory()<500000000:cause='Local memory safety floor';stop(cause);break
    if time.monotonic()>=next_monitor:
     try:
      sample=cloud();r=sample['resources'];assert sample['health_status']==200 and sample['health_elapsed_ms']<=10000 and all(r.get(k) is not None for k in ['cpu','memory_available_bytes','disk_available']);assert r['memory_available_bytes']>=500000000
      if sample['local_observation_elapsed_ms']>11000:raise ValueError('Cloud monitoring end-to-end budget')
      for k,red in [('cpu',r['cpu']>=85),('disk_available',r['disk_available']<15),('actor_wait',r.get('actor_wait') is not None and r['actor_wait']>=100)]:windows[k]=windows[k]+1 if red else 0
      status_path=OUT/'player.original.json.status.json';status=json.loads(status_path.read_bytes()) if status_path.exists() else {};playing=status.get('stage')=='playing';windows['actor_missing']=windows['actor_missing']+1 if playing and r.get('actor_wait') is None else 0;sample['local_client_status']=status;sample['safety_windows']=windows.copy()
      with (OUT/'cloud-monitor.original.jsonl').open('a',encoding='utf-8') as f:f.write(json.dumps(sample)+'\n')
      if any(n>=3 for n in windows.values()):raise ValueError('Three consecutive cloud safety or actor monitoring windows')
     except Exception as e:cause='Cloud monitoring stop: '+type(e).__name__+': '+str(e);stop(cause);write(OUT/'monitor-stop.original.json',{'reason':cause,'automatic_client_restart':False});break
     next_monitor=time.monotonic()+10
    time.sleep(.25)
   if child.poll() is None:
    cause=cause or 'Original600-second overall deadline';stop(cause)
    try:child.wait(timeout=120)
    except subprocess.TimeoutExpired:write(OUT/'forced-process-stop.original.json',{'actual_Godot_PID':child.pid,'reason':'Original120-second cleanup deadline exceeded'});child.terminate();child.wait(timeout=15)
  finally:
   if child.poll() is None:stop('Driver exception');child.terminate();child.wait(timeout=15)
  report_path=OUT/'player.original.json';report=json.loads(report_path.read_bytes()) if report_path.exists() else None;after=cloud('assets');write(OUT/'after-cloud.original.json',after);files=[]
  for p in OUT.rglob('*'):
   if p.is_file():files.append({'path':p.relative_to(OUT).as_posix(),'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()})
  write(OUT/'captured-originals-manifest.json',{'files':files});v={'ok':True,'actual_Godot_exit_code':child.returncode,'observation_stop_reason':cause,'original_script_report_present':report is not None,'original_script_report_ok':report.get('ok') if report else None,'original_report_cycles_completed':report.get('cycles_completed') if report else None,'all_raw_evidence_retained_on_G':True,'strict_default_Godot_TLS':True,'client_restarted':False,'natural_cycle_and_asset_route_independent_cloud_review_pending':True,'MAIN_accepted':False};write(OUT/'driver-result.original.json',v);print(json.dumps(v),flush=True)
if __name__=='__main__':
 try:main()
 except BaseException:
  if OUT.exists() and not (OUT/'driver-failure.original.json').exists():write(OUT/'driver-failure.original.json',{'ok':False,'error':traceback.format_exc(),'originals_retained':True,'automatic_client_restart':False})
  raise
