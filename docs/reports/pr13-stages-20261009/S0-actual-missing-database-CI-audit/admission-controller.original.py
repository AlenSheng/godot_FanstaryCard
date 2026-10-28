import ast,base64,hashlib,importlib.util,json,time
from pathlib import Path
B=Path(__file__).parent;OUT=B/'current-missing-DB-CI-AUDIT-r1-scheduled';assert not OUT.exists();OUT.mkdir();SOURCE='0e1763e21ede5eebd211a0019debca4e096419a9';A='current-missing-db-ci-audit-r1-20261012';payload={}
for name,filename in (('inner.original.py','current_missing_DB_CI_AUDIT_R1_inner.original.py'),('runner.py','current_missing_DB_CI_AUDIT_R1_cloud_runner.original.py')):
 raw=(B/filename).read_bytes();ast.parse(raw);payload[name]={'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest(),'base64':base64.b64encode(raw).decode()}
s=importlib.util.spec_from_file_location('missing_DB_CI_transport',B/'b08_lifecycle_r4_G_transport_gc_r2.py');m=importlib.util.module_from_spec(s);s.loader.exec_module(m);m.OUT=OUT;base=m.load('backup_failed_tuning_equivalence_r1_to_G.py')
def remote(code):
 c=base.connect()
 try:
  ch=c.get_transport().open_session(timeout=45);ch.exec_command('sudo -n python3 -');raw=code.encode()
  for i in range(0,len(raw),512):ch.sendall(raw[i:i+512]);time.sleep(.1)
  ch.shutdown_write();body,_,err=m.receive(ch);assert not err;return json.loads(body)
 finally:c.close()
dispatch=r'''
import base64,fcntl,hashlib,json,os,subprocess,time
from pathlib import Path
B=Path('/home/ubuntu/pr13-acceptance-20261009');E=B/'evidence'/A;W=B/'work'/A;OWNER='pr13-cap-'+A;REPO='/opt/fantasycard-github'
with (B/'evidence/shared-resource-coordination.lock').open('a') as lock:
 fcntl.flock(lock.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB);assert not E.exists() and not W.exists();busy=subprocess.check_output(['systemctl','list-units','--state=running','--no-legend','--plain','--no-pager','pr13-cap-*','pr13-pool-segment-*'],text=True).strip();memory=int(next(x.split()[1] for x in Path('/proc/meminfo').read_text().splitlines() if x.startswith('MemAvailable:')))*1024;s=os.statvfs('/')
 if busy or memory<500000000+1088*1024**2 or s.f_bavail*s.f_frsize<s.f_blocks*s.f_frsize*.15+256*1024**2:
  print(json.dumps({'ok':True,'dispatched':False,'existing_native_running':bool(busy)}));raise SystemExit()
 old=json.loads((B/'work/real-PG-TLS-framing-r2-inputs/manifest.json').read_bytes());assert not subprocess.check_output(['git','-C',REPO,'diff','--name-only',old['frozen_release_sha'],SOURCE,'--','server','protocol']).strip();E.mkdir();W.mkdir();control=E/'control';control.mkdir(mode=0o755)
 files=[]
 for name,row in PAYLOAD.items():
  raw=base64.b64decode(row['base64'],validate=True);assert len(raw)==row['bytes'] and hashlib.sha256(raw).hexdigest()==row['sha256'];p=E/name;p.write_bytes(raw);p.chmod(0o644);files.append({'path':name,'bytes':len(raw),'sha256':row['sha256']})
 name='tools/pr13_suite_coverage.py';raw=subprocess.check_output(['git','-C',REPO,'show',SOURCE+':'+name]);oid=subprocess.check_output(['git','-C',REPO,'rev-parse',SOURCE+':'+name],text=True).strip();assert hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest()==oid;p=control/'pr13_suite_coverage.py';p.write_bytes(raw);p.chmod(0o644);files.append({'path':'control/pr13_suite_coverage.py','bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest(),'git_blob_sha1':oid,'original_git_path':name})
 meta={k:old[k] for k in ('source','input_files','package_root','package_files','supplemental_package_root','supplemental_package_files','SDK_image','frozen_release_sha')};meta.update(production_source_sha=SOURCE,control_files=files,planned_case_ids=['LOAD-11.3-T02'],target_profiles=['AUDIT'],database_environment_key_deliberately_absent=True,production_unchanged=True);(E/'inputs.original.json').write_text(json.dumps(meta,indent=2)+'\n');(E/'inputs.original.json').chmod(0o644);(E/'dispatch-intent.original.json').write_text(json.dumps({'at':time.time(),'owner':OWNER,'source_sha':SOURCE,'no_automatic_retry':True})+'\n');p=subprocess.run(['systemd-run','--unit='+OWNER,'--property=Type=exec','--property=RuntimeMaxSec=1800','--property=Restart=no','python3',str(E/'runner.py')],capture_output=True,text=True,timeout=35);v={'ok':p.returncode==0,'dispatched':True,'owner':OWNER,'native_completion_not_claimed':True};(E/'dispatch-result.original.json').write_text(json.dumps(v)+'\n');print(json.dumps(v));assert v['ok']
'''
deadline=time.monotonic()+187200
while True:
 assert time.monotonic()<deadline
 readiness=remote("import json,subprocess\nbusy=subprocess.check_output(['systemctl','list-units','--state=running','--no-legend','--plain','--no-pager','pr13-cap-*','pr13-pool-segment-*'],text=True).strip();print(json.dumps({'ready':not busy,'existing_native_running':bool(busy),'readonly':True}))\n");(OUT/'last-admission-observation.json').write_text(json.dumps(readiness)+'\n')
 if not readiness['ready']:time.sleep(15);continue
 v=remote('A='+repr(A)+'\nSOURCE='+repr(SOURCE)+'\nPAYLOAD='+repr(payload)+'\n'+dispatch);(OUT/'last-admission-observation.json').write_text(json.dumps(v)+'\n');print(json.dumps(v),flush=True)
 if v['dispatched']:break
 time.sleep(15)
(OUT/'dispatch-result.original.json').write_text(json.dumps(v)+'\n')
while True:
 assert time.monotonic()<deadline
 v=remote('A='+repr(A)+'\n'+r'''
import json,subprocess
from pathlib import Path
E=Path('/home/ubuntu/pr13-acceptance-20261009/evidence')/A;p=E/'run-result.json';state=dict(x.split('=',1) for x in subprocess.check_output(['systemctl','show','pr13-cap-'+A,'--property=MainPID,ActiveState,ExecMainStatus'],text=True).splitlines());result=json.loads(p.read_bytes()) if p.exists() else None;print(json.dumps({'state':state,'result':result}))
''');(OUT/'last-native-observation.json').write_text(json.dumps(v,indent=2)+'\n')
 if v['result'] is not None and v['state']['MainPID']=='0':break
 assert v['state']['ActiveState']=='active','Inspect original exact unit; no redispatch';time.sleep(15)
print(json.dumps({'terminal':True,'native_ok':v['result']['ok'],'G_backup_pending':True}),flush=True)
