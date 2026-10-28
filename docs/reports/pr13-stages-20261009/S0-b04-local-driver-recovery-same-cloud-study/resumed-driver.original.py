"""Resume the same cloud study after a confirmed absent local G driver."""
import importlib.util,json,os,time,traceback,hashlib,msvcrt
from pathlib import Path
B=Path(__file__).parent;G=Path('G:/PR13Evidence/B04-single-factor-full-r1');OUT=B/'B04-full-r1-resumed-G-driver-r1';ORIGINAL=B/'B04_full_R1_G_driver.original.py'
def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(1024**2),b''):h.update(b)
 return h.hexdigest()
assert not OUT.exists() and G.is_dir();OUT.mkdir();s=importlib.util.spec_from_file_location('unchanged_original_B04_G_driver',ORIGINAL);d=importlib.util.module_from_spec(s);s.loader.exec_module(d);d.OUT=OUT;d.receiver.OUT=OUT
lock=(G/'local-driver-ownership.lock').open('a+b');lock.seek(0)
if lock.read(1)==b'':lock.write(b'1');lock.flush()
lock.seek(0);msvcrt.locking(lock.fileno(),msvcrt.LK_NBLCK,1)
def main():
 plan=json.loads((G/'common-frozen-inputs/plan.original.json').read_bytes());assert len(plan['units'])==5400 and plan['expected_encounters']==216000;st=d.remote('status');assert st['ok'];n=st['completed_G_verified_parts'];assert n==233,'Current authoritative state changed; inspect before adoption';checked=[]
 for spec in plan['units'][:n]:
  root=G/'units'/spec['unit'];receipt=json.loads((root/'local-G-receipt.original.json').read_bytes());clean=json.loads((root/'cloud-cleanup.original.json').read_bytes());manifest=root/'complete-original-manifest.json';archive=G/'archives'/(spec['unit']+'.original.tar.gz');assert receipt['ok'] and clean['ok'] and clean['originals_G_complete'] and receipt['unit']==spec['unit'] and receipt['manifest_sha256']==sha(manifest)==clean['manifest_sha256'] and archive.stat().st_size==receipt['archive_bytes'] and sha(archive)==receipt['archive_sha256'];checked.append({'unit':spec['unit'],'archive_sha256':receipt['archive_sha256'],'manifest_sha256':receipt['manifest_sha256']})
 cur=st['current'];assert cur and cur['spec']['unit']=='Mage-O6-basic-B0-P0660' and cur['result']['ok'] and cur['state']['MainPID']=='0' and cur['state']['ActiveState']=='inactive' and cur['state']['ExecMainStatus']=='0';assert not (G/'units'/cur['spec']['unit']).exists() and not (G/'archives'/(cur['spec']['unit']+'.original.tar.gz')).exists()
 d.write(OUT/'resumed.original.json',{'PID':os.getpid(),'adopted_G_parts':n,'adopted_G_encounters':n*40,'previous_PID_confirmed_absent':61332,'original_driver_sha256':sha(ORIGINAL),'same_original_controller_plan_runtime_and_validator':True,'current_native_successful_part_not_restarted':cur['spec']['unit'],'prior_original_logs_and_output_unchanged':True,'adopted_originals':checked,'at':time.time()});d.event({'phase':'ConfirmedAbsentLocalDriverResumed','adopted_G_parts':n,'native_restarts':0});last_reason=None
 while True:
  st=d.remote('status');assert st['ok']
  if st['completed_G_verified_parts']==5400:
   v=d.remote('final');assert v['ok'];d.write(G/'full-native-and-G-complete.original.json',v);d.event({'phase':'FullOriginal216000NativeAndGComplete','final_independent_statistics_pending':True});return
  cur=st['current']
  if cur is not None:
   if cur['result'] is not None:
    assert cur['result']['ok'],'Actual failed native part; originals retained, no skipped seeds'
    if cur['state']['MainPID']=='0' and cur['state']['ActiveState']=='inactive' and cur['state']['ExecMainStatus']=='0':d.backup(cur['spec']['unit']);last_reason=None;continue
   d.event({'phase':'ExactNativeHandleRunning','unit':cur['spec']['unit'],'completed_G_parts':st['completed_G_verified_parts']});time.sleep(15);continue
  launched=d.remote('launch');assert launched['ok']
  if launched.get('resource_deferred'):
   reason=launched.get('reason','Resource admission hold')
   if reason!=last_reason:d.event({'phase':'LaunchDeferred','detail':launched});last_reason=reason
   time.sleep(30)
  else:d.event({'phase':'ExactPhysicalPartDispatched','detail':launched});last_reason=None
if __name__=='__main__':
 try:main()
 except BaseException as error:
  d.write(OUT/'resume-failure.original.json',{'error':type(error).__name__,'detail':str(error),'traceback':traceback.format_exc(),'automatic_native_restart':False,'originals_retained':True});raise
 finally:lock.close()
