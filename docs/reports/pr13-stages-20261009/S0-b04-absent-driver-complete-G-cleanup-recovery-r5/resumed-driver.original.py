"""Resume R1 after absent local drivers: existing G archive complete; cleanup proven never started."""
import hashlib
import importlib.util
import json
import msvcrt
import os
import shutil
import time
import traceback
from pathlib import Path

B = Path(__file__).parent
G = Path('G:/PR13Evidence/B04-single-factor-full-r1')
OUT = B / 'B04-full-r1-resumed-G-driver-r5'
assert not OUT.exists()
OUT.mkdir()
spec = importlib.util.spec_from_file_location('original_B04_G_driver', B / 'B04_full_R1_G_driver.original.py')
d = importlib.util.module_from_spec(spec)
spec.loader.exec_module(d)
d.OUT = OUT
d.receiver.OUT = OUT


def sha(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 ** 2), b''):
            h.update(chunk)
    return h.hexdigest()


original_connect = d.transport.connect

def connect_before_any_command():
    for attempt in range(3):
        try:
            return original_connect()
        except (d.transport.paramiko.SSHException, OSError, EOFError) as error:
            if isinstance(error, (d.transport.paramiko.BadHostKeyException, d.transport.paramiko.AuthenticationException)):
                raise
            d.event({'phase':'ConnectionFailedBeforeAnyRemoteCommand','attempt':attempt+1,
                     'error':type(error).__name__,'detail':str(error),
                     'remote_command_sent':False,'mutation_retried':False})
            if attempt == 2:
                raise
            time.sleep(5 * (attempt + 1))

d.transport.connect = connect_before_any_command

def readonly_status():
    return d.remote('status')

def main():
    with (G / 'local-driver-ownership.lock').open('a+b') as lock:
        lock.seek(0)
        msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
        plan = json.loads((G / 'common-frozen-inputs/plan.original.json').read_bytes())
        assert len(plan['units']) == 5400 and plan['expected_encounters'] == 216000
        state = readonly_status()
        assert state['ok'] and state['completed_G_verified_parts'] == 1035
        cur=state['current'];assert cur and cur['spec']==plan['units'][1035] and cur['result']['ok']
        assert cur['state']['MainPID']=='0' and cur['state']['ActiveState']=='inactive' and cur['state']['ExecMainStatus']=='0'
        checked = []
        for item in plan['units'][:1035]:
            root = G / 'units' / item['unit']
            receipt = json.loads((root / 'local-G-receipt.original.json').read_bytes())
            clean = json.loads((root / 'cloud-cleanup.original.json').read_bytes())
            archive = G / 'archives' / (item['unit'] + '.original.tar.gz')
            assert receipt['ok'] and clean['ok'] and clean['originals_G_complete']
            assert receipt['manifest_sha256'] == sha(root / 'complete-original-manifest.json') == clean['manifest_sha256']
            assert archive.stat().st_size == receipt['archive_bytes'] and sha(archive) == receipt['archive_sha256']
            checked.append({'unit': item['unit'], 'archive_sha256': receipt['archive_sha256'],
                            'manifest_sha256': receipt['manifest_sha256']})
        name=plan['units'][1035]['unit'];root=G/'units'/name
        archive=G/'archives'/(name+'.original.tar.gz')
        receipt=json.loads((root/'local-G-receipt.original.json').read_bytes())
        manifest=json.loads((root/'complete-original-manifest.json').read_bytes())
        assert receipt['ok'] and receipt['all_members_SHA_verified'] and receipt['gzip_CRC_verified']
        assert not (root/'cloud-cleanup.original.json').exists()
        assert archive.stat().st_size==receipt['archive_bytes'] and sha(archive)==receipt['archive_sha256']
        assert sha(root/'complete-original-manifest.json')==receipt['manifest_sha256']
        for row in manifest['files']:
            p=root/row['path'];assert p.stat().st_size==row['bytes'] and sha(p)==row['sha256']
        import gzip
        with gzip.open(archive,'rb') as stream:
            while stream.read(1024**2):pass
        proof=json.loads((B/'B04-r4-interrupted-cleanup-readonly-original-02/stdout.original.json').read_bytes())
        assert proof['unit']==name and proof['output_exists'] and proof['original_collect_matches_manifest']
        assert proof['matching_controller_processes']==''
        assert all(proof['metadata_files'][n]['exists'] is False for n in
                   ['local-G-receipt.original.json','cleanup-intent.original.json','cleanup.original.json'])
        assert proof['metadata_files']['delivery-manifest.original.json']['sha256']==receipt['manifest_sha256']
        quarantine=G/'retained-interruptions/20261014-r4-absent-before-cloud-cleanup'
        assert not quarantine.exists();quarantine.mkdir(parents=True)
        for path in [B/'B04-full-r1-resumed-driver-r4.stdout.original.log',
                     B/'B04-full-r1-resumed-driver-r4.stderr.original.log',
                     B/'B04-complete-condition-release-followthrough-r4.stdout.original.log',
                     B/'B04-complete-condition-release-followthrough-r4.stderr.original.log',
                     B/'B04-r4-interrupted-cleanup-readonly-original-02/stdout.original.json',
                     root/'local-G-receipt.original.json']:
            shutil.copyfile(path,quarantine/path.name)
        d.write(quarantine/'interruption-preservation.original.json',
                {'ok':True,'unit':name,'previous_driver_PID_confirmed_absent':66668,
                 'previous_publisher_PID_confirmed_absent':60484,'exit_reason':'Unknown; no failure records and empty stderr',
                 'original_G_archive_complete':True,'cloud_cleanup_never_started_verified':True,
                 'native_restarted':False,'original_part_not_retransferred':True})
        cleaned=d.remote('cleanup',name,json.dumps(receipt))
        assert cleaned['ok'] and cleaned['originals_G_complete']
        d.write(root/'cloud-cleanup.original.json',cleaned)
        after=readonly_status();assert after['completed_G_verified_parts']==1036 and after['current'] is None
        d.write(OUT / 'resumed.original.json',
                {'PID': os.getpid(), 'at': time.time(), 'adopted_G_parts':1035,'adopted_G_encounters':41400,'already_G_complete_terminal_part_cleanup_finished':name,'G_parts_after_safe_cleanup':1036,
                 'native_restarts': 0, 'next_pending_native_part':plan['units'][1036]['unit'],
                 'original_cloud_plan_controller_runtime_validator_unchanged': True,
                 'original_driver_sha256': sha(B / 'B04_full_R1_G_driver.original.py'),
                 'preserved_failed_transfer': str(quarantine), 'checked_original_G_parts': checked})
        d.event({'phase': 'ConfirmedFailedTransportPreservedSameStudyResumed', 'G_parts':1036, 'native_restarts': 0})
        reason = None
        while True:
            state = readonly_status()
            assert state['ok']
            if state['completed_G_verified_parts'] == 5400:
                final = d.remote('final')
                assert final['ok']
                d.write(G / 'full-native-and-G-complete.original.json', final)
                d.event({'phase': 'FullOriginal216000NativeAndGComplete', 'final_independent_statistics_pending': True})
                return
            cur = state['current']
            if cur is not None:
                if cur['result'] is not None:
                    assert cur['result']['ok'], 'Actual native failure: preserve originals, no skipped seeds'
                    if cur['state']['MainPID'] == '0' and cur['state']['ActiveState'] == 'inactive' and cur['state']['ExecMainStatus'] == '0':
                        d.backup(cur['spec']['unit'])
                        reason = None
                        continue
                d.event({'phase': 'ExactNativeHandleRunning', 'unit': cur['spec']['unit'],
                         'completed_G_parts': state['completed_G_verified_parts']})
                time.sleep(15)
                continue
            launched = d.remote('launch')
            assert launched['ok']
            if launched.get('resource_deferred'):
                current_reason = launched.get('reason', 'Resource admission hold')
                if current_reason != reason:
                    d.event({'phase': 'LaunchDeferred', 'detail': launched})
                reason = current_reason
                time.sleep(30)
            else:
                d.event({'phase': 'ExactPhysicalPartDispatched', 'detail': launched})
                reason = None


if __name__ == '__main__':
    try:
        main()
    except BaseException as error:
        d.write(OUT / 'resume-failure.original.json', {'error': type(error).__name__, 'detail': str(error),
            'traceback': traceback.format_exc(), 'automatic_native_restart': False, 'originals_retained': True})
        raise
