"""Resume the human-revised original study at313 G closures; cloud bounded RAM outputs."""
import gzip,hashlib,importlib.util,json,msvcrt,os,shlex,time,traceback,threading
from pathlib import Path
B=Path(__file__).parent;G=Path('G:/PR13Evidence/B04-single-factor-reduced-r1');OUT=B/'B04-reduced540-run-RAM-output-G-driver-r4';assert not OUT.exists();OUT.mkdir()
s=importlib.util.spec_from_file_location('original_reduced_driver',B/'B04_reduced_R1_G_driver.original.py');m=importlib.util.module_from_spec(s);s.loader.exec_module(m);d=m.d;d.G=G;d.A='B04-single-factor-reduced-ram-r3-20261014';d.OUT=OUT;d.receiver.OUT=OUT;d.C='/home/ubuntu/pr13-acceptance-20261009/evidence/B04-single-factor-reduced-ram-r3-20261014/controller.original.py'
def remote_file_action(action,*args,target=None):
 c=d.transport.connect()
 try:
  c.get_transport().set_keepalive(5);ch=c.get_transport().open_session(timeout=45);done=threading.Event();failure=[]
  def dispatch():
   try:ch.exec_command('sudo -n python3 '+' '.join(shlex.quote(x) for x in [d.C,action,*args]))
   except BaseException as error:failure.append(error)
   finally:done.set()
  thread=threading.Thread(target=dispatch,daemon=True);thread.start()
  if not done.wait(15):
   c.close();d.event({'phase':'SSHExecAcknowledgementMissing','action':action,'remote_outcome':'Unknown','automatic_action_retry':False});raise TimeoutError('Exec acknowledgement unknown; inspect exact cloud state')
  if failure:raise failure[0]
  ch.shutdown_write();raw,n,err=d.receiver.receive(ch,target)
  if target is not None:return n,err
  assert not err;return json.loads(raw)
 finally:c.close()
d.remote=remote_file_action
def main():
 with (G/'local-driver-ownership.lock').open('a+b') as lock:
  lock.seek(0);msvcrt.locking(lock.fileno(),msvcrt.LK_NBLCK,1)
  plan=json.loads((G/'common-frozen-inputs/plan.original.json').read_bytes());assert len(plan['units'])==540 and plan['expected_encounters']==21600
  state=d.remote('status');assert state['completed_G_verified_parts']==349 and state['current'] is not None and state['current']['result']['ok'] and state['current']['state']['MainPID']=='0' and state['current']['state']['ActiveState']=='inactive'
  checked=[]
  for item in plan['units'][:349]:
   root=G/'units'/item['unit'];adopt=root/'adopted-original-G-closure.original.json'
   if adopt.exists():
    a=json.loads(adopt.read_bytes());rec=a['original_G_receipt'];archive=Path(a['original_archive']);original=Path(a['original_G_directory']);assert rec['ok'] and json.loads((original/'local-G-receipt.original.json').read_bytes())==rec and d.sha(original/'complete-original-manifest.json')==rec['manifest_sha256']
   else:
    rec=json.loads((root/'local-G-receipt.original.json').read_bytes());clean=json.loads((root/'cloud-cleanup.original.json').read_bytes());assert rec['ok'] and clean['ok'] and clean['originals_G_complete'] and rec['manifest_sha256']==clean['manifest_sha256']==d.sha(root/'complete-original-manifest.json');archive=G/'archives'/(item['unit']+'.original.tar.gz')
   assert archive.stat().st_size==rec['archive_bytes'] and d.sha(archive)==rec['archive_sha256']
   with gzip.open(archive,'rb') as f:
    while f.read(1024**2):pass
   checked.append({'unit':item['unit'],'archive_sha256':rec['archive_sha256'],'manifest_sha256':rec['manifest_sha256']})
  assert d.remote('status')==state
  proof=json.loads((B/'B04-exact-pending-stream-handles-r1-readonly/stdout.original.json').read_bytes());assert proof['exact_pending_controller_processes']==[] and not proof['current_metadata']['cleanup-intent.original.json'] and not proof['current_metadata']['cleanup.original.json']
  name=state['current']['spec']['unit'];assert name=='Guardian-BOSS-baseline_all_hand-B1-P0080';assert not (G/'units'/name).exists() and not (G/'archives'/(name+'.original.tar.gz')).exists()
  d.backup(name)
  after=d.remote('status');assert after['completed_G_verified_parts']==350 and after['current'] is None
  d.write(OUT/'resumed.original.json',{'ok':True,'PID':os.getpid(),'adopted_complete_G_parts':349,'existing_successful_native_part_G_recovered':name,'G_parts_after_existing_native_original_recovery':350,'required_parts':540,'remaining_parts':190,'native_restarts':0,'original_349_archives_SHA_CRC_reverified':True,'original_failed_attempts_retained':True,'RAM_output_controller':d.C,'remote_actions_use_existing_frozen_file_with_no_stdin_code_upload':True,'checked_original_G_parts':checked})
  d.event({'phase':'Original540StudyResumedWithBoundedRAMOutput','completed_G_parts':350,'required_parts':540,'native_restarts':0});reason=None
  while True:
   st=d.remote('status');assert st['ok']
   if st['completed_G_verified_parts']==540:
    final=d.remote('final');assert final['ok'];d.write(G/'revised-native-and-G-complete.original.json',final);d.event({'phase':'Revised540NativeAndGComplete','independent_statistics_pending':True});return
   cur=st['current']
   if cur:
    if cur['result'] is not None:
     assert cur['result']['ok'],'Actual native failure; no skipped seeds or automatic native retry'
     if cur['state']['MainPID']=='0' and cur['state']['ActiveState']=='inactive' and cur['state']['ExecMainStatus']=='0':d.backup(cur['spec']['unit']);reason=None;continue
    d.event({'phase':'ExactNativeHandleRunning','unit':cur['spec']['unit'],'completed_G_parts':st['completed_G_verified_parts'],'required_parts':540});time.sleep(15);continue
   launched=d.remote('launch');assert launched['ok']
   if launched.get('resource_deferred'):
    if reason!=launched.get('reason'):d.event({'phase':'LaunchDeferred','detail':launched})
    reason=launched.get('reason');time.sleep(15)
   else:d.event({'phase':'RevisedRAMPhysicalPartDispatched','detail':launched});reason=None
if __name__=='__main__':
 try:main()
 except BaseException:
  d.write(OUT/'driver-failure.original.json',{'ok':False,'error':traceback.format_exc(),'automatic_native_restart':False,'originals_retained':True});raise
