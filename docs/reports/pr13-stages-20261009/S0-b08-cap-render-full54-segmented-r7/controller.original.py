"""Sequential native admission, original G backup and exact passed-output reclamation."""
import ast,base64,hashlib,importlib.util,json,os,subprocess,sys,time
from pathlib import Path
B=Path(__file__).parent;R=B.parents[1];OUT=B/'cap-RENDER-r7-controller';assert not OUT.exists();OUT.mkdir();PLAN=json.loads((B/'cap-RENDER-r7-development/plan.json').read_bytes());RECEIPT=json.loads((B/'cap-RENDER-r7-inputs-install/cloud-input-receipt.original.json').read_bytes());raw=(B/'cap_RENDER_R7_segment_cloud_runner.original.py').read_bytes();runner_sha=hashlib.sha256(raw).hexdigest()
spec=importlib.util.spec_from_file_location('cap_render_transport',B/'b08_lifecycle_r4_G_transport_gc_r2.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);m.OUT=OUT;base=m.load('backup_failed_tuning_equivalence_r1_to_G.py');sys.path.insert(0,str(R));from tools.pr13_pool_render_evidence import png_validate
def remote(code):
 c=base.connect()
 try:
  ch=c.get_transport().open_session(timeout=45);ch.exec_command('sudo -n python3 -');data=code.encode()
  for i in range(0,len(data),512):ch.sendall(data[i:i+512]);time.sleep(.1)
  ch.shutdown_write();v,_,err=m.receive(ch);assert not err;return json.loads(v)
 finally:c.close()
def save(p,v):p.write_text(json.dumps(v,indent=2)+'\n')
dispatch=r'''
import base64,fcntl,hashlib,json,os,subprocess,time
from pathlib import Path
B=Path('/home/ubuntu/pr13-acceptance-20261009');E=B/'evidence'/A;OWNER='pr13-cap-'+A;D=Path(RECEIPT['input_root'])
with (B/'evidence/shared-resource-coordination.lock').open('a') as lock:
 fcntl.flock(lock.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB);assert not E.exists();assert hashlib.sha256((D/'manifest.json').read_bytes()).hexdigest()==RECEIPT['manifest_sha256']
 busy=subprocess.check_output(['systemctl','list-units','--state=running','--no-legend','--plain','--no-pager','pr13-cap-*','pr13-pool-segment-*'],text=True).strip();available=int(next(x.split()[1] for x in Path('/proc/meminfo').read_text().splitlines() if x.startswith('MemAvailable:')))*1024;st=os.statvfs('/')
 if busy or available<500000000+1664*1024**2 or st.f_bavail*st.f_frsize<st.f_blocks*st.f_frsize*.15+128*1024**2:
  print(json.dumps({'ok':True,'dispatched':False,'existing_native_running':bool(busy),'memory_available_bytes':available}));raise SystemExit()
 raw=base64.b64decode(DATA,validate=True);assert hashlib.sha256(raw).hexdigest()==RUNNER_SHA;E.mkdir();(E/'preregistration.original.json').write_text(json.dumps({'full_matrix_plan':PLAN,'segment':SEGMENT,'runner_sha256':RUNNER_SHA},indent=2)+'\n');(E/'runner.py').write_bytes(raw);(E/'input-manifest.original.json').write_bytes((D/'manifest.json').read_bytes());(E/'dispatch-intent.json').write_text(json.dumps({'at':time.time(),'owner':OWNER,'runner_sha256':RUNNER_SHA,'no_automatic_retry':True,'prior_existing_native_not_stopped':True})+'\n')
 p=subprocess.run(['systemd-run','--unit='+OWNER,'--property=Type=exec','--property=RuntimeMaxSec=1080','--property=Restart=no','/usr/bin/python3',str(E/'runner.py'),SEGMENT['slug']],capture_output=True,text=True,timeout=35);v={'ok':p.returncode==0,'dispatched':True,'owner':OWNER,'native_completion_not_claimed':True};(E/'dispatch-result.json').write_text(json.dumps(v)+'\n');print(json.dumps(v));assert v['ok']
'''
deadline=time.monotonic()+187200;completed=[]
for segment in PLAN['segments']:
 slug=segment['slug'];A=slug+'-20261012';unitout=OUT/slug;unitout.mkdir();watch=unitout/'last-native-observation.json';save(OUT/'current-segment.json',segment)
 while True:
  assert time.monotonic()<deadline
  code='A='+repr(A)+'\nSEGMENT='+repr(segment)+'\nPLAN='+repr(PLAN)+'\nRECEIPT='+repr(RECEIPT)+'\nRUNNER_SHA='+repr(runner_sha)+'\nDATA='+repr(base64.b64encode(raw).decode())+'\n'+dispatch
  v=remote(code);save(unitout/'last-admission-observation.json',v);print(json.dumps({'segment':slug,**v}),flush=True)
  if v['dispatched']:break
  time.sleep(15)
 save(unitout/'dispatch-result.original.json',v)
 while True:
  code='A='+repr(A)+'\n'+r'''
import json,subprocess
from pathlib import Path
E=Path('/home/ubuntu/pr13-acceptance-20261009/evidence')/A;p=E/'run-result.json';state=dict(x.split('=',1) for x in subprocess.check_output(['systemctl','show','pr13-cap-'+A,'--property=MainPID,ActiveState,ExecMainStatus'],text=True).splitlines());result=json.loads(p.read_bytes()) if p.exists() else None;print(json.dumps({'state':state,'result':{k:v for k,v in result.items() if k!='native'} if result else None}))
'''
  v=remote(code);save(watch,v)
  if v['result'] is not None and v['state']['MainPID']=='0':break
  assert v['state']['ActiveState']=='active' and time.monotonic()<deadline,'Observe original existing native; never redispatch';time.sleep(15)
 template=(B/'backup_dual-GUI-return-title-fit-r3_complete_G_delta_once.py').read_text(encoding='utf-8')
 template=template.replace("OUT=B/'dual-GUI-return-title-fit-r3-complete-G-delta'",'OUT=B/'+repr(slug+'-complete-G-delta')).replace("DEST=Path('G:/PR13Evidence/dual-GUI-return-title-fit-r3')",'DEST=Path('+repr('G:/PR13Evidence/'+slug)+')').replace("watch=B/'dual-GUI-return-title-fit-r3-scheduled/last-native-observation.json'",'watch=B/'+repr('cap-RENDER-r7-controller/'+slug+'/last-native-observation.json')).replace("A='dual-GUI-return-title-fit-r3-20261012'",'A='+repr(A)).replace("D=B/'work/dual-GUI-return-title-fit-r3-inputs'","D=B/'work/cap-RENDER-r7-inputs'").replace('time.sleep(.01)','time.sleep(.1)')
 backup=B/('backup_'+slug+'_complete_G_delta_once.py');assert not backup.exists();ast.parse(template);backup.write_text(template,encoding='utf-8',newline='\n');subprocess.run([sys.executable,str(backup)],check=True,timeout=3600)
 back=B/(slug+'-complete-G-delta');proof=json.loads((back/'local-backup-receipt.json').read_bytes());assert proof['ok'];G=Path(proof['local_directory']);manifest=json.loads((back/'complete-logical-delivery-manifest.json').read_bytes());resolved={}
 for key in ('transferred_members','verified_existing_G_members'):
  for row in manifest[key]:
   p=G/row['path'] if key=='transferred_members' else Path('\\\\?\\'+str(Path(row['verified_existing_G_path']).resolve()));assert p.stat().st_size==row['bytes'] and m.sha(p)==row['sha256'];resolved[row['path']]=p
 wrapper=json.loads(resolved['metadata/run-result.json'].read_bytes());start=json.loads(resolved['metadata/run-started.json'].read_bytes());journal=resolved['metadata/terminal-journal.original.jsonl'];manager=[json.loads(line) for line in journal.read_text(encoding='utf-8').splitlines() if json.loads(line).get('_PID')=='1' and json.loads(line).get('UNIT')=='pr13-cap-'+A+'.service'];assert manager and all(x.get('INVOCATION_ID')==start['invocation_id'] and x.get('_BOOT_ID')==start['boot_id'].replace('-','') for x in manager)
 if not wrapper['ok']:
  save(unitout/'failed-originals-preserved.json',{'ok':False,'G_backup':proof,'failed_cloud_RAM_retained':True,'later_native_not_dispatched':True});raise RuntimeError('Native segment failed; original evidence retained on G and cloud')
 assert any('Deactivated successfully' in x.get('MESSAGE','') for x in manager) and not any('Failed with result' in x.get('MESSAGE','') for x in manager)
 pixels=[{'path':name,'sha256':m.sha(p),'CRC_validation':png_validate(p)} for name,p in resolved.items() if name.startswith('native-output/') and name.endswith('.png')];assert len(pixels)==segment['expected_pngs'];native=wrapper['native'];assert len(native['observations'])==3 and all(r['passed'] for r in native['observations']) and native['native_witness_renders']==segment['expected_witnesses']
 save(unitout/'independent-G-metadata-verification.json',{'ok':True,'segment':segment,'members_rehashed':len(resolved),'actual_PID1_normal_exit':True,'invocation_id':start['invocation_id'],'original_PNGs':pixels,'visual_review_pending':True,'MAIN_accepted':False})
 # Cleanup only the exact successful RAM files covered by the verified G inventory.
 rows=[r for r in manifest['files'] if r['path'].startswith('native-output/')];receipt=remote('A='+repr(A)+'\nROWS='+repr(rows)+'\nG_RECEIPT='+repr(proof)+'\n'+r'''
import hashlib,json,os,stat,subprocess
from pathlib import Path
B=Path('/home/ubuntu/pr13-acceptance-20261009');E=B/'evidence'/A;RAM=Path('/dev/shm/pr13-'+A);assert RAM.resolve()==RAM and RAM.name.startswith('pr13-cap-RENDER-r7-');result=json.loads((E/'run-result.json').read_bytes());assert result['ok'] and G_RECEIPT['ok'] and G_RECEIPT['native_ok'];state=dict(x.split('=',1) for x in subprocess.check_output(['systemctl','show','pr13-cap-'+A,'--property=MainPID,ActiveState'],text=True).splitlines());assert state['MainPID']=='0' and state['ActiveState']=='inactive'
ids=subprocess.check_output(['docker','ps','-aq'],text=True).splitlines()
for cid in ids:
 info=json.loads(subprocess.check_output(['docker','inspect',cid]))[0];assert (info['Config'].get('Labels') or {}).get('codex.owner')!='pr13-cap-'+A
 for mount in info.get('Mounts',[]):
  if mount.get('Type')!='bind':continue
  path=Path(mount['Source']).resolve();related=path==RAM or path in RAM.parents or RAM in path.parents
  if related:assert info['Id']=='2734235cbfa1f9d8f1352cd9a925251f6356021d86ede341f80c6196e799149a' and info['Name']=='/fantasycard-cloud-node-exporter-1' and info['Image']=='sha256:d00a542e409ee618a4edc67da14dd48c5da66726bbd5537ab2af9c1dfc442c8a' and mount['Source']=='/' and mount['Destination']=='/host' and mount['RW'] is False
expected={Path(r['source']) for r in ROWS};actual=set(p for p in RAM.rglob('*') if p.is_file());assert actual==expected and all(not p.is_symlink() for p in RAM.rglob('*'));removed=0
for row in ROWS:
 p=Path(row['source']);assert p.parent==RAM and stat.S_ISREG(p.lstat().st_mode) and p.stat().st_size==row['bytes'] and hashlib.sha256(p.read_bytes()).hexdigest()==row['sha256'];removed+=row['bytes'];p.unlink()
subprocess.run(['umount',str(RAM)],check=True);RAM.rmdir();receipt={'ok':True,'removed_passed_original_output_bytes':removed,'exact_G_archive_sha256':G_RECEIPT['archive_sha256'],'source_and_metadata_kept':True,'failed_attempts_kept':True,'native_not_reexecuted':True};p=E/'passed-G-output-cleanup.json';assert not p.exists();p.write_text(json.dumps(receipt,indent=2)+'\n');print(json.dumps(receipt))
''');save(unitout/'cloud-cleanup-receipt.json',receipt);completed.append(segment);save(OUT/'completed-segments.json',completed);print(json.dumps({'segment_G_verified_and_RAM_cleaned':slug,'complete':len(completed),'required':18,'native_rows_G':sum(s['expected_rows'] for s in completed),'visual_review_pending':True}),flush=True)
save(OUT/'all18-native-G-metadata-verified.json',{'ok':True,'segments':18,'rows':54,'original_native_witnesses':540,'original_PNGs':24,'visual_review_pending':True,'MAIN_accepted':False})
