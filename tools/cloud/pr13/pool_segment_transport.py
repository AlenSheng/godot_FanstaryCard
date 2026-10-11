"""Local G evidence transport for the explicitly selected cloud B09.2 queue.

Native Godot/.NET execution remains cloud-only. Local work is limited to
archive, PNG, JSON and typed wire evidence verification. --once observes one
cloud status only. Failed evidence and uncertain mutations are never retried.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shlex
import socket
import sys
import time
import uuid

import paramiko

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from tools import pr13_pool_render_evidence as verifier


HOST = '43.172.70.182'
CLOUD_ROOT = '/home/ubuntu/pr13-acceptance-20261009'
GROUP = 'pool-render-segments-r3'
SEGMENT_RE = r'(Guardian|Mage|Priest)-(3|5|8)-T0[123]-(zh-CN|en)'
POLL_SECONDS = 30
MAX_ARCHIVE_BYTES = 96 * 1024**2


class AttentionRequired(Exception):
    """Safe user-facing reason without credentials or untrusted remote output."""


def require(condition, message):
    if not condition:
        raise AttentionRequired(message)


def read(path):
    require(path.is_file() and not path.is_symlink(), 'Missing or linked local metadata')
    return json.loads(path.read_text(encoding='utf-8'))


def atomic_write(path, value):
    require(not path.is_symlink(), 'Linked local output is rejected')
    temporary = path.with_name(path.name + '.tmp-' + uuid.uuid4().hex)
    with temporary.open('xb') as stream:
        stream.write((json.dumps(value, indent=2, ensure_ascii=False) + '\n').encode('utf-8'))
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


def transport_factory(*args, **kwargs):
    transport = paramiko.Transport(*args, **kwargs)
    options = transport.get_security_options()
    options.kex = ('diffie-hellman-group14-sha256',)
    options.ciphers = ('aes128-ctr',)
    options.digests = ('hmac-sha2-256-etm@openssh.com',)
    return transport


class QueueTransport:
    def __init__(self, args):
        require(args.cloud_host == HOST and args.cloud_root == CLOUD_ROOT, 'Cloud host/root is outside authorized queue')
        self.args = args
        self.evidence = PurePosixPath(args.cloud_root) / 'evidence' / GROUP
        controller = PurePosixPath(args.controller)
        require(controller == self.evidence / 'controller.py', 'Only the explicit owned cloud controller.py is supported')
        self.local = args.local_root.resolve()
        require(self.local.drive.upper() == 'G:', 'Evidence output must remain on local G drive')
        require(not self.local.is_symlink(), 'Linked local evidence root is rejected')
        self.local.mkdir(parents=True, exist_ok=True)
        config = args.private_config.read_text(encoding='utf-8-sig')
        match = re.search(r'set "FANTASYCARD_CLOUD_KEY=(.*?)"', config, re.IGNORECASE)
        require(match is not None, 'Private cloud key configuration is missing')
        self._key = os.path.expandvars(match[1])
        require(Path(self._key).is_file(), 'Configured cloud key file is unavailable')
        self.client = None
        self.last_stdout = 0.0
        self.current_segment = None
        self.last_status = None
        self.wait_started = {}

    def emit(self, value, force=True):
        if not force and time.monotonic() - self.last_stdout < POLL_SECONDS:
            return
        record = {'at_unix': time.time(), 'whole_task_accepted': False,
                  'visual_final_review_pending': True} | value
        raw = json.dumps(record, ensure_ascii=False)
        log = self.local / 'transport-log.jsonl'
        require(not log.is_symlink(), 'Linked local transport log')
        with log.open('a', encoding='utf-8', newline='\n') as stream:
            stream.write(raw + '\n')
        atomic_write(self.local / 'transport-progress.json', record)
        if force or time.monotonic() - self.last_stdout >= POLL_SECONDS:
            print(raw, flush=True)
            self.last_stdout = time.monotonic()

    def connect(self):
        if self.client is not None:
            self.client.close()
        self.client = paramiko.SSHClient()
        self.client.load_system_host_keys(str(Path.home() / '.ssh/known_hosts'))
        self.client.set_missing_host_key_policy(paramiko.RejectPolicy())
        self.client.connect(self.args.cloud_host, username='ubuntu', key_filename=self._key,
                            look_for_keys=False, allow_agent=False, timeout=10, banner_timeout=12,
                            auth_timeout=12, transport_factory=transport_factory)
        self.client.get_transport().set_keepalive(5)

    def channel(self):
        if self.client is None or self.client.get_transport() is None or not self.client.get_transport().is_active():
            self.connect()
        return self.client.get_transport().open_session(timeout=10)

    def request(self, action, segment=None, backup=None):
        arguments = ['python3', self.args.controller, '--root', self.args.cloud_root, '--action', action]
        if segment is not None:
            require(re.fullmatch(SEGMENT_RE, segment) is not None, 'Unknown segment ID')
            arguments += ['--segment', segment]
        if backup is not None:
            arguments += ['--backup-receipt', str(backup)]
        channel = self.channel()
        channel.settimeout(60)
        try:
            channel.exec_command(' '.join(shlex.quote(value) for value in arguments))
            stdout = channel.makefile('rb').read(2 * 1024**2)
            stderr = channel.makefile_stderr('rb').read(65536)
            code = channel.recv_exit_status()
            require(code == 0 and not stderr, 'Cloud controller action failed; retained state requires inspection')
            result = json.loads(stdout.decode('utf-8'))
            require(isinstance(result, dict) and result.get('ok') is True, 'Cloud controller returned unsuccessful state')
            return result
        finally:
            channel.close()

    def status(self, segment=None):
        try:
            result = self.request('status', segment)
        except AttentionRequired:
            raise
        except Exception:
            # This is a read only query. Reconnection cannot launch or restart.
            self.connect()
            result = self.request('status', segment)
        self.last_status = result
        self.current_segment = result.get('segment', {}).get('id')
        return result

    def mutation(self, action, segment=None, backup=None):
        try:
            result = self.request(action, segment, backup)
        except Exception:
            observation = None
            try:
                observation = self.status(segment)
            except Exception:
                pass
            self.emit({'state': 'mutation_observation_uncertain', 'action': action,
                       'segment': segment, 'native_live_observed': bool(observation and self.is_live(observation)),
                       'no_mutation_retry': True})
            raise AttentionRequired('Mutation outcome requires exact cloud status inspection; action was not retried')
        dispatch = result.get('dispatch_state') or result.get('startup_state')
        require(not dispatch or dispatch in ('dispatch_observed',), 'Cloud dispatch uncertain; no automatic restart')
        return result

    @staticmethod
    def is_live(status):
        unit = status.get('unit', {})
        return unit.get('MainPID', 0) != 0 or unit.get('ActiveState') in ('active', 'activating', 'deactivating', 'reloading')

    def local_directory(self, segment):
        require(re.fullmatch(SEGMENT_RE, segment) is not None, 'Unknown native segment ID')
        path = self.local / segment
        require(path.resolve().is_relative_to(self.local) and not path.is_symlink(), 'Linked or escaped local segment')
        path.mkdir(exist_ok=True)
        return path

    def get_json(self, remote, destination):
        temporary = destination.with_name(destination.name + '.download-' + uuid.uuid4().hex)
        def fetch():
            if self.client is None or self.client.get_transport() is None or not self.client.get_transport().is_active():
                self.connect()
            sftp = self.client.open_sftp()
            try:
                info = sftp.lstat(str(remote))
                require(info.st_size <= 2 * 1024**2, 'Unexpected remote metadata size')
                sftp.get(str(remote), str(temporary), prefetch=False)
            finally:
                sftp.close()
        try:
            fetch()
        except AttentionRequired:
            raise
        except Exception:
            # Preserve interrupted reads; only perform a fresh read after reconnect.
            self.connect()
            temporary = destination.with_name(destination.name + '.download-' + uuid.uuid4().hex)
            fetch()
        data = read(temporary)
        if destination.exists():
            require(verifier.sha(destination) == verifier.sha(temporary), 'Existing local metadata differs; preserve both files')
            temporary.unlink()
        else:
            os.rename(temporary, destination)
        return data

    def direct_archive(self, directory, segment, manifest_path, manifest, prepared):
        archive = directory / 'delivery.private.tar.gz'
        receipt_path = directory / 'transport-receipt.json'
        if archive.exists() or receipt_path.exists():
            require(archive.is_file() and receipt_path.is_file(), 'Existing archive/receipt pair is incomplete; preserve for inspection')
            receipt = read(receipt_path)
            require(receipt.get('ok') is True and receipt.get('manifest_sha256') == prepared['manifest_sha256']
                    and receipt.get('bytes') == archive.stat().st_size and receipt.get('sha256') == verifier.sha(archive)
                    and receipt.get('members') == len(manifest['files']) and receipt.get('local_archive') == str(archive),
                    'Existing G archive/receipt does not match exact cloud manifest')
            return archive, receipt_path, receipt
        remote_manifest = self.evidence / segment / 'delivery-manifest.json'
        # No additional archive is ever written to the cloud filesystem.
        code = '''import hashlib,json,sys,tarfile
from pathlib import Path
def require(value):
 if not value:raise ValueError('Original frozen archive source changed')
M=Path(%r);expected_manifest=%r
h=hashlib.sha256()
with M.open('rb') as f:
 for b in iter(lambda:f.read(65536),b''):h.update(b)
require(h.hexdigest()==expected_manifest)
m=json.loads(M.read_text(encoding='utf-8'))
with tarfile.open(fileobj=sys.stdout.buffer,mode='w|gz',dereference=True) as tar:
 for row in m['files']:
  p=Path(row['source']);require(p.is_file() and not p.is_symlink() and p.stat().st_size==row['bytes'])
  h=hashlib.sha256()
  with p.open('rb') as f:
   for b in iter(lambda:f.read(65536),b''):h.update(b)
  require(h.hexdigest()==row['sha256'])
  tar.add(p,arcname='segment/'+row['path'],recursive=False)
 tar.add(M,arcname='segment/manifest.json',recursive=False)
''' % (str(remote_manifest), prepared['manifest_sha256'])
        partial = directory / ('delivery.partial-' + uuid.uuid4().hex + '.tar.gz')
        channel = self.channel()
        channel.settimeout(1)
        h = hashlib.sha256()
        size = 0
        stderr = bytearray()
        deadline = time.monotonic() + 240
        try:
            channel.exec_command('python3 -')
            channel.sendall(code.encode('utf-8'))
            channel.shutdown_write()
            with partial.open('xb') as stream:
                while True:
                    require(time.monotonic() < deadline, 'Read-only archive stream observation expired; partial evidence retained')
                    if channel.recv_stderr_ready():
                        stderr.extend(channel.recv_stderr(4096))
                        require(len(stderr) <= 65536, 'Unexpected remote archive diagnostic size')
                    try:
                        block = channel.recv(65536)
                    except socket.timeout:
                        block = None
                    if block == b'':
                        break
                    if block:
                        stream.write(block)
                        h.update(block)
                        size += len(block)
                        require(size <= MAX_ARCHIVE_BYTES, 'Cloud segment archive exceeded frozen output plus metadata bound')
                    self.emit({'state': 'streaming_original_segment_to_G', 'segment': segment, 'archive_bytes': size}, force=False)
                stream.flush()
                os.fsync(stream.fileno())
            while channel.recv_stderr_ready():
                stderr.extend(channel.recv_stderr(4096))
            require(channel.recv_exit_status() == 0 and not stderr and size > 0,
                    'Cloud original archive stream failed; partial evidence retained')
        finally:
            channel.close()
        require(not archive.exists() and not receipt_path.exists(), 'Concurrent G archive creation detected')
        os.rename(partial, archive)
        receipt = {'ok': True, 'segment': segment, 'local_archive': str(archive),
                   'cloud_archive_created': False, 'transfer_mode': 'direct_stream_to_G',
                   'bytes': size, 'sha256': h.hexdigest(), 'members': len(manifest['files']),
                   'manifest_sha256': verifier.sha(manifest_path)}
        atomic_write(receipt_path, receipt)
        return archive, receipt_path, receipt

    def verify_local(self, directory, archive, receipt):
        extraction = directory / 'verified'
        manifest = verifier.verify_archive(archive, receipt, extraction)
        result = verifier.verify_segment(extraction, manifest)
        proof = receipt | result | {'ok': True, 'local_archive': str(archive), 'local_directory': str(extraction),
            'members_verified': len(manifest['files']), 'archive_gzip_CRC_verified': True,
            'no_native_business_executed_locally': True, 'whole_task_accepted': False, 'full_matrix_accepted': False,
            'LIVE_accepted': False, 'human_experience_accepted': False, 'hardware_FPS_accepted': False,
            'scope': 'one cloud software-rendered fixture language segment'}
        proof_path = extraction / 'local-backup-receipt.json'
        if proof_path.exists():
            require(read(proof_path) == proof, 'Existing G verification proof differs; originals retained')
        else:
            atomic_write(proof_path, proof)
        return proof_path, proof

    def upload_verified(self, proof_path, remote):
        require(remote == self.evidence / self.current_segment / 'local-backup-receipt.json', 'Receipt upload target changed')
        sftp = self.client.open_sftp()
        temporary = str(remote) + '.upload-' + uuid.uuid4().hex
        try:
            try:
                existing = sftp.open(str(remote), 'rb')
            except FileNotFoundError:
                existing = None
            if existing is not None:
                with existing:
                    require(existing.read(2 * 1024**2) == proof_path.read_bytes(), 'Existing cloud G proof differs; preserve it')
                return
            sftp.put(str(proof_path), temporary, confirm=True)
            with sftp.open(temporary, 'rb') as check:
                require(hashlib.sha256(check.read(2 * 1024**2)).hexdigest() == verifier.sha(proof_path), 'Uploaded G receipt SHA mismatch')
            sftp.rename(temporary, str(remote))
        except Exception:
            raise AttentionRequired('G receipt upload outcome needs read-only inspection; cleanup was not issued')
        finally:
            sftp.close()

    def recovered_cleaned(self, directory, segment, state):
        remote = self.evidence / segment
        receipt = self.get_json(remote / 'local-backup-receipt.json', directory / 'cloud-backup-receipt.json')
        cleanup = self.get_json(remote / 'local-storage-cleanup.json', directory / 'cloud-cleanup-receipt.json')
        require(receipt.get('ok') is True and isinstance(receipt.get('segment'), dict) and receipt['segment']['id'] == segment
                and cleanup.get('ok') is True and cleanup.get('segment') == segment
                and receipt.get('sha256') == cleanup.get('local_G_archive_sha256')
                and receipt.get('manifest_sha256') == cleanup.get('manifest_sha256'), 'Cloud cleanup/backup anchors differ')
        archive = Path(receipt['local_archive'])
        extraction = Path(receipt['local_directory'])
        require(archive.drive.upper() == extraction.drive.upper() == 'G:' and archive.is_file() and extraction.is_dir(),
                'Previously cleaned cloud evidence has no available original G backup')
        require(archive.stat().st_size == receipt['bytes'] and verifier.sha(archive) == receipt['sha256'], 'Prior original G archive changed')
        manifest = verifier.verify_archive(archive, receipt, extraction)
        verified = verifier.verify_segment(extraction, manifest)
        require(verified['segment']['id'] == segment and receipt['matrix_rows_verified'] == verified['matrix_rows_verified'],
                'Prior G native metadata verification differs')
        require(read(extraction / 'local-backup-receipt.json') == receipt, 'Cloud/local original G proof differs')
        self.emit({'state': 'prior_G_backup_and_cloud_cleanup_revalidated', 'segment': segment,
                   'matrix_rows': verified['matrix_rows_verified'], 'PNG_originals': 9})

    @staticmethod
    def required_counts(report):
        counts = {key: report.get(key) for key in ('required_segments', 'required_rows', 'required_PNGs')}
        require(counts == {'required_segments': 54, 'required_rows': 5832, 'required_PNGs': 486},
                'Cloud required product-locale matrix differs from the frozen scope')
        return counts

    def completed_report(self, report):
        counts = self.required_counts(report)
        self.emit({'state': 'all_required_fixture_segments_G_verified_and_cloud_cleaned',
                   **counts, 'full_fixture_matrix_rows': counts['required_rows'],
                   'PNG_originals': counts['required_PNGs'], 'formal_EXPERIMENT_pending': True,
                   'legacy_nonproduct_locale_evidence_retained': True})

    def wait_for_resources(self, report):
        resources = report.get('resource_deferred', {})
        require(isinstance(resources, dict) and resources.get('deferred') is True,
                'Resource deferral lacks an explicit authoritative gate')
        self.emit({'state': 'waiting_for_cloud_resource_and_G_backup_gate', 'segment': self.current_segment,
                   'resource_deferred': resources, 'no_startup_created': report.get('no_startup_created'),
                   'no_native_restart': True})
        time.sleep(POLL_SECONDS)

    def loop(self):
        self.connect()
        while True:
            state = self.status()
            counts = self.required_counts(state)
            self.emit({'state': 'observed_cloud_status', 'segment': self.current_segment,
                       **counts,
                       'unit': state.get('unit'), 'rows': state.get('rows'),
                       'completed_segments': state.get('completed_segments'),
                       'cleanup_receipts_present': state.get('cleanup_receipts_present'),
                       'resource_deferred': state.get('resource_deferred')})
            if self.args.once:
                return
            if self.is_live(state):
                require(state.get('startup_state') not in ('dispatch_failed_requires_inspection',
                            'dispatch_observation_timeout_requires_inspection'), 'Uncertain dispatch requires inspection')
                key = self.current_segment
                require(key is not None, 'Live native unit lacks an exact segment ID')
                self.wait_started.setdefault(key, time.monotonic())
                if time.monotonic() - self.wait_started[key] > 900:
                    # This does not stop or restart the cloud job. It only ends
                    # local observation and leaves the live exact handle intact.
                    raise AttentionRequired('Exact native unit remains live beyond observation budget; preserve it and inspect status')
                time.sleep(POLL_SECONDS)
                continue
            if state.get('resource_deferred', {}).get('deferred') is True and (
                    self.current_segment is None or state.get('local_cleanup_receipt_present') is True):
                self.wait_for_resources(state)
                continue
            if self.current_segment is None:
                launch = self.mutation('launch-next')
                if launch.get('all_required_fixture_segments_cleaned'):
                    self.completed_report(launch)
                    return
                if launch.get('launch_deferred_resources') is True:
                    self.wait_for_resources(launch)
                    continue
                require(launch.get('segment') or launch.get('controller_busy'), 'No exact dispatch result')
                time.sleep(POLL_SECONDS)
                continue
            segment = self.current_segment
            require(state.get('result_ok') is True and state.get('shutdown_resources_clean') is True,
                    'Native segment failed or ended without successful evidence; originals retained')
            require(state.get('unit', {}).get('MainPID') == 0 and state.get('unit', {}).get('ExecMainStatus') == 0,
                    'Exact native terminal status is unsuccessful or incomplete')
            directory = self.local_directory(segment)
            if state.get('local_cleanup_receipt_present'):
                self.recovered_cleaned(directory, segment, state)
            else:
                prepared = self.mutation('prepare-delivery', segment)
                require(prepared.get('action') == 'prepare-delivery' and prepared.get('segment') == segment,
                        'Delivery preparation did not return exact terminal segment')
                manifest_path = directory / 'delivery-manifest.json'
                manifest = self.get_json(self.evidence / segment / 'delivery-manifest.json', manifest_path)
                require(verifier.sha(manifest_path) == prepared['manifest_sha256'] and manifest['segment']['id'] == segment,
                        'Downloaded original manifest differs from cloud preparation')
                archive, _, receipt = self.direct_archive(directory, segment, manifest_path, manifest, prepared)
                proof_path, proof = self.verify_local(directory, archive, receipt)
                self.emit({'state': 'original_G_archive_verified', 'segment': segment, 'archive_bytes': proof['bytes'],
                           'matrix_rows_verified': proof['matrix_rows_verified'], 'PNG_CRC_deflate_verified': 9,
                           'independent_wire_command_rows_verified': proof['independent_wire_command_rows_verified']})
                remote_proof = self.evidence / segment / 'local-backup-receipt.json'
                self.upload_verified(proof_path, remote_proof)
                cleaned = self.mutation('cleanup', segment, remote_proof)
                require(cleaned.get('action') == 'cleanup' and cleaned.get('cleanup', {}).get('ok') is True,
                        'Cloud reclamation did not return a verified receipt')
                cleanup_receipt = cleaned['cleanup']
                path = directory / 'cloud-cleanup-receipt.json'
                if path.exists():
                    require(read(path) == cleanup_receipt, 'Existing cloud cleanup record differs')
                else:
                    atomic_write(path, cleanup_receipt)
                self.emit({'state': 'passed_originals_on_G_cloud_output_reclaimed', 'segment': segment,
                           'root_disk_bytes_reclaimed': cleanup_receipt.get('root_disk_bytes_reclaimed')})
            launched = self.mutation('launch-next')
            if launched.get('all_required_fixture_segments_cleaned'):
                self.completed_report(launched)
                return
            if launched.get('launch_deferred_resources') is True:
                self.wait_for_resources(launched)
                continue
            if launched.get('controller_busy'):
                time.sleep(POLL_SECONDS)
                continue
            require(launched.get('segment') and not launched.get('launch_suppressed'), 'Existing unresolved stage prevents new launch')
            self.emit({'state': 'next_exact_cloud_segment_observed', 'segment': launched['segment']['id'],
                       'unit': launched.get('unit'), 'dispatch_state': launched.get('dispatch_state')})
            time.sleep(POLL_SECONDS)


def lock_local(root):
    path = root / '.transport.lock'
    require(not path.is_symlink(), 'Linked local queue lock')
    stream = path.open('a+b')
    if path.stat().st_size == 0:
        stream.write(b'0')
        stream.flush()
    stream.seek(0)
    try:
        if os.name == 'nt':
            import msvcrt
            msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        stream.close()
        raise AttentionRequired('An existing local queue transport owns this output root')
    return stream


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cloud-host', required=True)
    parser.add_argument('--cloud-root', required=True)
    parser.add_argument('--private-config', type=Path, required=True)
    parser.add_argument('--local-root', type=Path, default=Path('outputs/pr13-tencent-20261009/pool-render-segment-r3-raw'))
    parser.add_argument('--controller', required=True)
    parser.add_argument('--once', action='store_true', help='Observe one exact status; do not transfer, reclaim or launch')
    args = parser.parse_args()
    transport = None
    lock = None
    try:
        transport = QueueTransport(args)
        lock = lock_local(transport.local)
        transport.loop()
        return 0
    except Exception as error:
        record = {'state': 'attention_required', 'error': type(error).__name__,
                  'reason': str(error) if isinstance(error, AttentionRequired) else 'Transport or metadata verification failed; original evidence retained',
                  'no_automatic_restart': True, 'whole_task_accepted': False, 'visual_final_review_pending': True}
        if transport is not None:
            transport.emit(record)
        else:
            print(json.dumps(record), flush=True)
        return 1
    finally:
        if transport is not None and transport.client is not None:
            transport.client.close()
        if lock is not None:
            lock.close()


if __name__ == '__main__':
    raise SystemExit(main())
