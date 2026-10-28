"""Wait for all original inputs, then run the frozen full analysis on Tencent only."""
import gzip,hashlib,importlib.util,json,os,tarfile,time
from pathlib import Path,PurePosixPath
B=Path(__file__).parent;OUT=B/'cap-full-statistics-cloud-queue-r5';assert not OUT.exists();OUT.mkdir();READY=B/'cap-full-statistics-all360-projection-queue-r1/projection-ready-for-Tencent.json';until=time.monotonic()+187200;ATTEMPT='cap-full-statistics-r1-20261011';SHA='5f6fd687c67ab60a2d283974ab3591b989dc479c';REMOTE_BASE='/home/ubuntu/pr13-acceptance-20261009';TOOLS=REMOTE_BASE+'/cache/cap-full-statistics-frozen-r1-20261011';PROJECTION=REMOTE_BASE+'/work/cap-full-statistics-projection-r1-20261011'
while not READY.exists():
 assert time.monotonic()<until,'Full original 360 projection incomplete; no statistical dispatch';print(json.dumps({'state':'waiting_for_full_360_original_projection','statistics_executed':False}),flush=True);time.sleep(30)
ready=json.loads(READY.read_bytes());assert ready['ok'] and ready['logical_units']==360 and ready['no_statistics_executed'];root=Path(ready['projection']);assert root.resolve().drive.upper()=='G:'
source_receipt=json.loads((B/'cap-full-statistics-source-install-r1/cloud-source-receipt.original.json').read_bytes());assert source_receipt['ok'] and source_receipt['source_sha']==SHA
archive=OUT/'projection.private.tar.gz';rows=[]
with tarfile.open(archive,'w:gz',compresslevel=1) as t:
 for p in sorted(root.rglob('*')):
  assert not p.is_symlink()
  if p.is_file():
   relative=p.relative_to(root).as_posix();digest=hashlib.sha256(p.read_bytes()).hexdigest();rows.append({'path':relative,'bytes':p.stat().st_size,'sha256':digest});t.add(p,arcname=relative,recursive=False)
assert sum(row['bytes'] for row in rows)<=256*1024**2
with gzip.open(archive,'rb') as f:
 for _ in iter(lambda:f.read(65536),b''):pass
archive_sha=hashlib.sha256(archive.read_bytes()).hexdigest();(OUT/'projection-transport-intent.json').write_text(json.dumps({'original_projection':str(root),'archive_bytes':archive.stat().st_size,'archive_sha256':archive_sha,'files':rows,'all360':True,'no_statistics_executed_locally':True},indent=2)+'\n')
spec=importlib.util.spec_from_file_location('full_cap_statistics_owned_transport',B/'b08_lifecycle_r4_G_transport_gc_r2.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);m.OUT=OUT;base=m.load('backup_failed_tuning_equivalence_r1_to_G.py')
def remote(code):
 c=base.connect()
 try:
  ch=c.get_transport().open_session(timeout=45);ch.exec_command('python3 -');data=code.encode();
  for offset in range(0,len(data),512):ch.sendall(data[offset:offset+512]);time.sleep(.01)
  ch.shutdown_write();raw,_,err=m.receive(ch);assert not err;return json.loads(raw)
 finally:c.close()
remote_archive=REMOTE_BASE+'/cache/cap-full-statistics-projection-r1.private.tar.gz';v=remote('P='+repr(remote_archive)+'\n'+"from pathlib import Path\nimport json\nassert not Path(P).exists()\nprint(json.dumps({'ok':True}))\n");assert v['ok']
c=base.connect()
try:
 sf=c.open_sftp()
 try:
  with sf.open(remote_archive,'wx') as target,archive.open('rb') as source:
   target.set_pipelined(True)
   for chunk in iter(lambda:source.read(512),b''):target.write(chunk);target.flush();time.sleep(.01)
  sf.chmod(remote_archive,0o600)
 finally:sf.close()
finally:c.close()
extract=r'''
import hashlib,json,os,tarfile
from pathlib import Path,PurePosixPath
P=Path(PROJECTION);assert not P.exists();st=os.statvfs('/');assert st.f_bavail*st.f_frsize>=int(st.f_blocks*st.f_frsize*.15)+sum(r['bytes'] for r in ROWS)+96*1024**2;assert hashlib.sha256(Path(ARCHIVE).read_bytes()).hexdigest()==ARCHIVE_SHA;P.mkdir();expected={r['path']:r for r in ROWS};seen=set()
with tarfile.open(ARCHIVE,'r:gz') as t:
 for item in t:
  rel=PurePosixPath(item.name);assert item.isfile() and not rel.is_absolute() and '..' not in rel.parts and item.name in expected and item.name not in seen;seen.add(item.name);data=t.extractfile(item).read();r=expected[item.name];assert len(data)==r['bytes'] and hashlib.sha256(data).hexdigest()==r['sha256'];p=P/item.name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(data)
assert seen==set(expected);print(json.dumps({'ok':True,'all_projection_members_verified':len(seen),'statistics_not_started':True}))
'''
v=remote('PROJECTION='+repr(PROJECTION)+'\nARCHIVE='+repr(remote_archive)+'\nARCHIVE_SHA='+repr(archive_sha)+'\nROWS='+repr(rows)+'\n'+extract);assert v['ok'];(OUT/'cloud-projection-extracted.original.json').write_text(json.dumps(v)+'\n')
prepared=False
while not prepared:
 assert time.monotonic()<until,'Prepared statistics resource wait exceeded without native restart'
 code='ATTEMPT='+repr(ATTEMPT)+'\nTOOLS='+repr(TOOLS)+'\nPROJECTION='+repr(PROJECTION)+'\nSHA='+repr(SHA)+'\nREADY='+repr(ready)+'\n'+r'''
import json,os,subprocess
from pathlib import Path
memory=int(next(x.split()[1] for x in Path('/proc/meminfo').read_text().splitlines() if x.startswith('MemAvailable:')))*1024
render=subprocess.check_output(['systemctl','list-units','--state=active','--no-legend','--plain','--no-pager','pr13-pool-segment-*','pr13-cap-*'],text=True).strip()
if render or memory<500000000+(950+64)*1024**2:print(json.dumps({'ok':True,'prepared':False,'resource_deferred':True}));raise SystemExit()
env=os.environ.copy();env.update(GIT_CONFIG_COUNT='1',GIT_CONFIG_KEY_0='safe.directory',GIT_CONFIG_VALUE_0='/opt/fantasycard-github');p=subprocess.run(['sudo','-n','env','GIT_CONFIG_COUNT=1','GIT_CONFIG_KEY_0=safe.directory','GIT_CONFIG_VALUE_0=/opt/fantasycard-github','python3',TOOLS+'/runner.py','prepare','--attempt',ATTEMPT,'--projection',PROJECTION,'--dataset-sha256',READY['dataset_sha256'],'--prereg-sha256',READY['prereg_sha256'],'--formal-plan-sha256',READY['formal_plan_sha256'],'--analysis-source-sha',SHA],capture_output=True,text=True,timeout=600);assert p.returncode==0,(p.returncode,p.stderr[-2000:]);v=json.loads(p.stdout);v['prepared']=not v.get('prepare_deferred_resources',False);print(json.dumps(v))
'''
 v=remote(code);(OUT/'last-prepare-observation.json').write_text(json.dumps(v,indent=2)+'\n');prepared=v['prepared']
 if not prepared:time.sleep(30)
dispatch=r'''
import json,re,subprocess,time
from pathlib import Path
E=Path('/home/ubuntu/pr13-acceptance-20261009/evidence')/ATTEMPT;intent=E/'systemd-dispatch-intent.json';assert not intent.exists() and not (E/'startup.json').exists();owner='pr13-'+ATTEMPT;assert re.fullmatch('pr13-cap-full-statistics-r1-20261011',owner);unit=Path('/etc/systemd/system')/(owner+'.service');assert not unit.exists()
body='[Unit]\nDescription=PR13 owned full 360 unit statistics\n[Service]\nType=exec\nUser=root\nWorkingDirectory=/opt/fantasycard-github\nEnvironment=GIT_CONFIG_COUNT=1\nEnvironment=GIT_CONFIG_KEY_0=safe.directory\nEnvironment=GIT_CONFIG_VALUE_0=/opt/fantasycard-github\nExecStart=/usr/bin/python3 '+TOOLS+'/runner.py run --attempt '+ATTEMPT+' --systemd-unit '+owner+'\nRuntimeMaxSec=2100\nRestart=no\n'
intent.write_text(json.dumps({'at':time.time(),'owner':owner,'owned_unit_file':str(unit),'persistent_terminal_unit_identity_for_G_proof':True,'no_automatic_retry':True,'all_360_original_projection_ready':True})+'\n')
p=subprocess.run(['sudo','-n','tee',str(unit)],input=body.encode(),capture_output=True,timeout=35);assert p.returncode==0 and unit.read_text()==body
p=subprocess.run(['sudo','-n','systemctl','daemon-reload'],capture_output=True,timeout=35);assert p.returncode==0
p=subprocess.run(['sudo','-n','systemctl','start','--no-block',owner],capture_output=True,text=True,timeout=35);v={'ok':p.returncode==0,'systemd_unit':owner,'owned_unit_file':str(unit),'exit_code':p.returncode,'stdout':p.stdout,'stderr':p.stderr,'computation_complete_not_claimed':True};(E/'systemd-dispatch-result.json').write_text(json.dumps(v,indent=2)+'\n');print(json.dumps(v));assert v['ok']
'''
(OUT/'local-native-dispatch-intent.json').write_text(json.dumps({'attempt':ATTEMPT,'source_sha':SHA,'no_automatic_retry':True})+'\n');v=remote('ATTEMPT='+repr(ATTEMPT)+'\nTOOLS='+repr(TOOLS)+'\n'+dispatch);(OUT/'cloud-native-dispatch-result.original.json').write_text(json.dumps(v,indent=2)+'\n');print(json.dumps(v),flush=True)
while True:
 v=remote('ATTEMPT='+repr(ATTEMPT)+'\n'+r'''
import json,subprocess
from pathlib import Path
E=Path('/home/ubuntu/pr13-acceptance-20261009/evidence')/ATTEMPT;p=E/'result.json';name='pr13-'+ATTEMPT;state=dict(x.split('=',1) for x in subprocess.check_output(['systemctl','show',name,'--property=MainPID,ActiveState,ExecMainStatus'],text=True).splitlines());print(json.dumps({'state':state,'startup_present':(E/'startup.json').exists(),'result':json.loads(p.read_bytes()) if p.exists() else None}))
''');(OUT/'last-statistics-native-observation.json').write_text(json.dumps(v,indent=2)+'\n')
 if v['result'] is not None:print(json.dumps(v),flush=True);break
 assert v['state']['ActiveState']=='active','Statistics exact attempt is terminal without result; audit, never redispatch';time.sleep(15)
print(json.dumps({'statistics_original_result_retained':True,'full_G_backup_and_case_gap_review_pending':True,'MAIN_accepted':False}),flush=True)
