"""Balanced human-revised 540-part study, adopting verified original G parts."""
import gzip,hashlib,importlib.util,json,msvcrt,os,shutil,time,traceback
from pathlib import Path
B=Path(__file__).parent;G=Path('G:/PR13Evidence/B04-single-factor-reduced-r1')
OUT=B/'B04-reduced-r1-G-driver';STAGE=B.parents[1]/'docs/reports/pr13-stages-20261009/S0-human-tenfold-sample-revision'
spec=importlib.util.spec_from_file_location('original_G_byte_transport',B/'B04_full_R1_G_driver.original.py')
d=importlib.util.module_from_spec(spec);spec.loader.exec_module(d)
d.G=G;d.OUT=OUT;d.receiver.OUT=OUT;d.A='B04-single-factor-reduced-r1-20261014'
d.C='/home/ubuntu/pr13-acceptance-20261009/evidence/'+d.A+'/controller.original.py'
original_connect=d.transport.connect
def connect_before_command():
    for attempt in range(3):
        try:return original_connect()
        except (d.transport.paramiko.SSHException,OSError,EOFError) as e:
            if isinstance(e,(d.transport.paramiko.BadHostKeyException,d.transport.paramiko.AuthenticationException)):raise
            d.event({'phase':'ConnectionFailedBeforeAnyRemoteCommand','attempt':attempt+1,'error':type(e).__name__,'remote_command_sent':False})
            if attempt==2:raise
            time.sleep(5*(attempt+1))
d.transport.connect=connect_before_command
def main():
    assert not OUT.exists() and not G.exists();OUT.mkdir();G.mkdir();(G/'units').mkdir();(G/'archives').mkdir()
    common=G/'common-frozen-inputs';common.mkdir()
    for name in ['plan.original.json','controller.original.py','validator.original.py','config-reference.original.json','adoptions.original.json','human-decision.original.json']:
        shutil.copyfile(STAGE/name,common/name)
    plan=json.loads((common/'plan.original.json').read_bytes())
    assert len(plan['units'])==540 and plan['expected_encounters']==21600
    with (G/'local-driver-ownership.lock').open('a+b') as lock:
        lock.seek(0);msvcrt.locking(lock.fileno(),msvcrt.LK_NBLCK,1)
        adopted=json.loads((common/'adoptions.original.json').read_bytes())['adoptions']
        for a in adopted:
            old=Path(a['original_G_directory']);receipt=a['original_G_receipt'];archive=Path(a['original_archive'])
            assert json.loads((old/'local-G-receipt.original.json').read_bytes())==receipt
            assert archive.stat().st_size==receipt['archive_bytes'] and d.sha(archive)==receipt['archive_sha256']
            assert d.sha(old/'complete-original-manifest.json')==receipt['manifest_sha256']
            with gzip.open(archive,'rb') as f:
                while f.read(1024**2):pass
            root=G/'units'/a['unit'];root.mkdir();d.write(root/'adopted-original-G-closure.original.json',a)
        state=d.remote('status');assert state['completed_G_verified_parts']==115 and state['current'] is None
        d.write(OUT/'started.original.json',{'ok':True,'PID':os.getpid(),'required_parts':540,'expected_encounters':21600,
            'adopted_original_parts':115,'native_restarts':0,'old_driver_stopped_by_human_scope_revision':True})
        last_reason=None
        while True:
            state=d.remote('status');assert state['ok']
            if state['completed_G_verified_parts']==540:
                final=d.remote('final');assert final['ok'];d.write(G/'revised-native-and-G-complete.original.json',final)
                d.event({'phase':'Revised540NativeAndGComplete','independent_statistics_pending':True});return
            cur=state['current']
            if cur:
                if cur['result'] is not None:
                    assert cur['result']['ok'],'Actual native failure; no skipped seeds or automatic native retry'
                    if cur['state']['MainPID']=='0' and cur['state']['ActiveState']=='inactive' and cur['state']['ExecMainStatus']=='0':
                        d.backup(cur['spec']['unit']);last_reason=None;continue
                d.event({'phase':'ExactNativeHandleRunning','unit':cur['spec']['unit'],'completed_G_parts':state['completed_G_verified_parts'],'required_parts':540})
                time.sleep(15);continue
            launched=d.remote('launch');assert launched['ok']
            if launched.get('resource_deferred'):
                reason=launched.get('reason')
                if reason!=last_reason:d.event({'phase':'LaunchDeferred','detail':launched})
                last_reason=reason;time.sleep(15)
            else:d.event({'phase':'RevisedPhysicalPartDispatched','detail':launched});last_reason=None
if __name__=='__main__':
    try:main()
    except Exception:
        if OUT.exists() and not (OUT/'driver-failure.original.json').exists():
            d.write(OUT/'driver-failure.original.json',{'ok':False,'error':traceback.format_exc(),'automatic_native_restart':False,'originals_retained':True})
        raise
