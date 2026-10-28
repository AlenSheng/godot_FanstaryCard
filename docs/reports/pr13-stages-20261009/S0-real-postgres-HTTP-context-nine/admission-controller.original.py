import ast,base64,hashlib,importlib.util,json,time
from pathlib import Path
B=Path(__file__).parent;OUT=B/'real-PG-HTTP-context-r1-scheduled';assert not OUT.exists();OUT.mkdir();PLAN=json.loads((B/'real-PG-HTTP-context-r1-development/plan.json').read_bytes());RECEIPT=json.loads((B/'real-PG-HTTP-context-r1-inputs-install/cloud-input-receipt.original.json').read_bytes());raw=(B/'real_PG_HTTP_context_R1_cloud_runner.original.py').read_bytes();ast.parse(raw);RUNNER_SHA=hashlib.sha256(raw).hexdigest();A='real-pg-http-context-r1-20261012'
spec=importlib.util.spec_from_file_location('PG_HTTP_admission_transport',B/'b08_lifecycle_r4_G_transport_gc_r2.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);m.OUT=OUT;base=m.load('backup_failed_tuning_equivalence_r1_to_G.py')
def remote(code):
 c=None
 for attempt in range(5):
  try:c=base.connect();break
  except Exception as error:
   print(json.dumps({'preconnect_retry':attempt+1,'error_type':type(error).__name__,'no_remote_action_sent':True}),flush=True)
   if attempt==4:raise
   time.sleep(10)
 try:
  ch=c.get_transport().open_session(timeout=45);ch.exec_command('sudo -n python3 -');data=code.encode()
  for i in range(0,len(data),512):ch.sendall(data[i:i+512]);time.sleep(.1)
  ch.shutdown_write();v,_,err=m.receive(ch);assert not err;return json.loads(v)
 finally:c.close()
dispatch=r'''
import base64,fcntl,hashlib,json,os,subprocess,time
from pathlib import Path
B=Path('/home/ubuntu/pr13-acceptance-20261009');E=B/'evidence'/A;W=B/'work'/A;OWNER='pr13-cap-'+A;D=Path(RECEIPT['input_root'])
with (B/'evidence/shared-resource-coordination.lock').open('a') as lock:
 fcntl.flock(lock.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB);assert not E.exists() and not W.exists();assert hashlib.sha256((D/'manifest.json').read_bytes()).hexdigest()==RECEIPT['manifest_sha256']
 busy=subprocess.check_output(['systemctl','list-units','--state=running','--no-legend','--plain','--no-pager','pr13-cap-*','pr13-pool-segment-*'],text=True).strip();memory=int(next(x.split()[1] for x in Path('/proc/meminfo').read_text().splitlines() if x.startswith('MemAvailable:')))*1024;s=os.statvfs('/')
 if busy or memory<500000000+1536*1024**2 or s.f_bavail*s.f_frsize<s.f_blocks*s.f_frsize*.15+320*1024**2:
  print(json.dumps({'ok':True,'dispatched':False,'existing_native_running':bool(busy)}));raise SystemExit()
 raw=base64.b64decode(DATA,validate=True);assert hashlib.sha256(raw).hexdigest()==RUNNER_SHA;E.mkdir();W.mkdir();(E/'runner.py').write_bytes(raw);(E/'preregistration.original.json').write_text(json.dumps({'plan':PLAN,'runner_sha256':RUNNER_SHA,'input_receipt':RECEIPT},indent=2)+'\n');(E/'input-manifest.original.json').write_bytes((D/'manifest.json').read_bytes());(E/'dispatch-intent.original.json').write_text(json.dumps({'at':time.time(),'owner':OWNER,'no_automatic_native_retry':True})+'\n');p=subprocess.run(['systemd-run','--unit='+OWNER,'--property=Type=exec','--property=RuntimeMaxSec=1800','--property=Restart=no','/usr/bin/python3',str(E/'runner.py')],capture_output=True,text=True,timeout=35);result={'ok':p.returncode==0,'dispatched':True,'owner':OWNER,'native_not_yet_complete':True};(E/'dispatch-result.original.json').write_text(json.dumps(result)+'\n');print(json.dumps(result));assert result['ok']
'''
deadline=time.monotonic()+187200
while True:
 assert time.monotonic()<deadline
 readiness=remote(r'''
import json,os,subprocess
from pathlib import Path
busy=subprocess.check_output(['systemctl','list-units','--state=running','--no-legend','--plain','--no-pager','pr13-cap-*','pr13-pool-segment-*'],text=True).strip();memory=int(next(x.split()[1] for x in Path('/proc/meminfo').read_text().splitlines() if x.startswith('MemAvailable:')))*1024;s=os.statvfs('/');print(json.dumps({'ready':not busy and memory>=500000000+1536*1024**2 and s.f_bavail*s.f_frsize>=s.f_blocks*s.f_frsize*.15+320*1024**2,'readonly':True,'existing_native_running':bool(busy)}))
''');(OUT/'last-admission-observation.json').write_text(json.dumps(readiness)+'\n')
 if not readiness['ready']:time.sleep(15);continue
 v=remote('A='+repr(A)+'\nPLAN='+repr(PLAN)+'\nRECEIPT='+repr(RECEIPT)+'\nRUNNER_SHA='+repr(RUNNER_SHA)+'\nDATA='+repr(base64.b64encode(raw).decode())+'\n'+dispatch);(OUT/'last-admission-observation.json').write_text(json.dumps(v)+'\n');print(json.dumps(v),flush=True)
 if v['dispatched']:break
 time.sleep(15)
(OUT/'dispatch-result.original.json').write_text(json.dumps(v)+'\n')
while True:
 assert time.monotonic()<deadline
 v=remote('A='+repr(A)+'\n'+r'''
import json,subprocess
from pathlib import Path
E=Path('/home/ubuntu/pr13-acceptance-20261009/evidence')/A;p=E/'run-result.json';state=dict(x.split('=',1) for x in subprocess.check_output(['systemctl','show','pr13-cap-'+A,'--property=MainPID,ActiveState,ExecMainStatus'],text=True).splitlines());result=json.loads(p.read_bytes()) if p.exists() else None;print(json.dumps({'state':state,'result':{k:v for k,v in result.items() if k!='inner'} if result else None}))
''');(OUT/'last-native-observation.json').write_text(json.dumps(v,indent=2)+'\n')
 if v['result'] is not None and v['state']['MainPID']=='0':break
 assert v['state']['ActiveState']=='active','Inspect exact original unit; no redispatch';time.sleep(15)
print(json.dumps({'terminal':True,'native_ok':v['result']['ok'],'G_backup_pending':True}),flush=True)
