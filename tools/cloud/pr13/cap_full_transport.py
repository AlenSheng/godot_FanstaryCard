"""Stream the fixed PR13 B08.4 cloud experiment originals to local G.

Native execution and contract validation remain on the Tencent host. Local
work only verifies archived bytes, JSON metadata, gzip CRC, raw SHA and row
counts. --once observes status without cloud writes. --max-units 2 bounds the
first continuation to Water B1/B2 without changing the full 360-unit scope.
Mutation uncertainty is observed, never automatically redispatched. Failed
originals remain untouched and cannot become accepted through this tool.
"""

import argparse
from collections import Counter
import gzip
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shlex
import socket
import sys
import tarfile
import time
import uuid

import paramiko

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from tools.cloud.pr13.pool_segment_transport import (
    AttentionRequired, atomic_write, lock_local, read, require, transport_factory,
)
from tools.pr13_pool_render_evidence import resolve_member, safe_parts, sha


HOST = '43.172.70.182'
CLOUD_ROOT = '/home/ubuntu/pr13-acceptance-20261009'
GROUP = 'cap-experiment-full-r2'
SOURCE = 'b0423bfe6fedc3f034ba12c8400df5ebb8713f32'
UNIT_RE = r'(Mage|Priest|Guardian)-(O1|O6|E1|BOSS)-(Fire|Wood|Earth|Metal|Water)-L(0|5)-B([012])'
BLOCK = 65536
POLL_SECONDS = 30
METADATA_RESERVE = 16 * 1024**2
MAX_RAW_BYTES = 2 * 1024**3
ARMS = ('BaselinePurple', 'SingleOrangeHead')
OUTCOMES = ('Victory', 'Death', 'Censored', 'Error')


def unit_contract(name):
    match = re.fullmatch(UNIT_RE, name or '')
    require(match is not None, 'Unknown experiment unit')
    hero, group, element, level, block = match.groups()
    return {'unit': name, 'hero': hero, 'group': group, 'element': element,
            'level': int(level), 'block': int(block),
            'seed_start': 440001 + 1000 * int(block), 'samples': 1000}


def verify_archive(archive, receipt, destination, manifest_limit):
    """Read outer gzip to EOF; safely extract only manifest-listed originals."""
    require(archive.is_file() and not archive.is_symlink(), 'Missing or linked G archive')
    require(archive.stat().st_size == receipt['bytes'] and sha(archive) == receipt['sha256'],
            'G archive byte count or SHA differs')
    with gzip.open(archive, 'rb') as stream:
        for _ in iter(lambda: stream.read(BLOCK), b''):
            pass
    destination.mkdir(parents=True, exist_ok=True)
    require(not destination.is_symlink(), 'Linked G extraction root')
    members = {}
    total = 0
    with tarfile.open(archive, mode='r|gz') as stream:
        for member in stream:
            require(member.isfile(), 'Tar links, directories and special entries rejected')
            parts = safe_parts(member.name)
            require(len(parts) > 1 and parts[0] == 'unit', 'Wrong cap archive root')
            name = PurePosixPath(*parts[1:]).as_posix()
            require(name not in members and len(members) < 10000, 'Duplicate or excessive archive members')
            total += member.size
            require(0 <= member.size <= manifest_limit and total <= manifest_limit,
                    'Archive exceeds frozen output and metadata budget')
            path = resolve_member(destination, name)
            path.parent.mkdir(parents=True, exist_ok=True)
            existing = path.exists()
            require(not existing or path.is_file(), 'G extraction destination is not a file')
            source = stream.extractfile(member)
            require(source is not None, 'Archive original member is absent')
            digest = hashlib.sha256()
            size = 0
            target = None if existing else path.open('xb')
            try:
                for block in iter(lambda: source.read(BLOCK), b''):
                    digest.update(block)
                    size += len(block)
                    if target is not None:
                        target.write(block)
            finally:
                source.close()
                if target is not None:
                    target.close()
            require(size == member.size == path.stat().st_size and sha(path) == digest.hexdigest(),
                    'Extracted original member differs')
            members[name] = {'bytes': size, 'sha256': digest.hexdigest()}
    manifest_path = resolve_member(destination, 'manifest.json')
    require(manifest_path.is_file() and sha(manifest_path) == receipt['manifest_sha256'],
            'Frozen manifest missing or changed')
    manifest = read(manifest_path)
    rows = manifest['files']
    require(len(rows) == receipt['members'] and len(members) == len(rows) + 1,
            'Archive/manifest original member count differs')
    names = set()
    for row in rows:
        name = row['path']
        safe_parts(name)
        require(name != 'manifest.json' and name not in names, 'Duplicate manifest original path')
        names.add(name)
        require(members.get(name) == {'bytes': row['bytes'], 'sha256': row['sha256']},
                'Archived original size/SHA differs from frozen manifest')
    require(set(members) == names | {'manifest.json'}, 'Unlisted archive member')
    files = {p.relative_to(destination).as_posix() for p in destination.rglob('*') if p.is_file()}
    require(files - {'local-backup-receipt.json'} == set(members), 'Unlisted local extracted original')
    return manifest


def verify_unit(directory, manifest, unit):
    """Verify retained rows and metadata; do not execute combat or its oracle."""
    expected = unit_contract(unit)
    require(manifest.get('kind') == GROUP and manifest.get('unit') == unit
            and manifest.get('source_sha') == SOURCE, 'Wrong original manifest unit/source')
    native = directory / 'outputs' / unit / 'native'
    summary = read(native / 'summary.json')
    original = read(native / 'manifest.json')
    validation = read(directory / 'outputs' / unit / 'validation.json')
    result = read(directory / 'metadata/result.json')
    prereg = read(directory / 'metadata/preregistration.json')
    require(original['source_sha'] == SOURCE and summary['source_sha'] == SOURCE
            and validation['source_sha'] == SOURCE and result['source_sha'] == SOURCE,
            'Original execution metadata source differs')
    require(all(original[k] == expected[v] for k, v in (
        ('hero', 'hero'), ('group', 'group'), ('element', 'element'),
        ('equipment_level', 'level'), ('block_index', 'block'),
        ('seed_start', 'seed_start'), ('samples', 'samples'))), 'Original seed/stratum differs')
    require(prereg.get('unit') == result.get('unit') == unit, 'Native unit metadata differs')
    require(summary.get('passed') is True and validation.get('ok') is True and result.get('ok') is True,
            'Native experiment or cloud independent validator failed')
    require(result.get('exit_code') == 0 and result.get('oom_killed') is False
            and result.get('owned_container_removed') is True,
            'Native terminal lifecycle did not complete successfully')
    require(result.get('compiled_runtime_unchanged_and_identical_to_original') is True
            and result.get('source_subset_inputs_unchanged') is True,
            'Frozen compiled runtime or 372 source inputs changed')
    require(summary['rows'] == validation['encounters'] == manifest['native_encounters'] == 2000
            and validation['pairs'] == 1000, 'Frozen full-unit encounter/pair count differs')
    casts, ticks = summary['actual_casts'], summary['actual_ticks']
    require(type(casts) is int and type(ticks) is int and casts >= 0 and ticks >= 0,
            'Invalid native event counts')
    require(casts == validation['actual_casts'] == manifest['native_casts']
            and ticks == validation['actual_ticks'] == manifest['native_ticks'],
            'Native and independent cloud event counts differ')
    controls = validation.get('negative_controls', [])
    require({c.get('name') for c in controls} == {
        'wrong-resistance-cap', 'wrong-conversion-stage', 'wrong-shield-overflow', 'candidate-policy-enabled'
    } and len(controls) == 4 and all(c.get('rejected') is True for c in controls),
            'Cloud independent validator controls missing or unsuccessful')
    for metadata in (summary, validation, result):
        require(metadata.get('main_acceptance_granted') is False, 'Metadata unexpectedly grants MAIN')
    require(summary.get('full_experiment_complete') is False
            and summary.get('required_cases_accepted') is False
            and validation.get('whole_experiment_complete') is False,
            'One unit incorrectly claims full formal acceptance')
    require(original.get('candidate_activation') is False, 'Production candidate activation observed')
    parts = summary['event_parts']
    require(isinstance(parts, list) and parts, 'No original native event parts')
    names = set()
    rows_total = bytes_total = 0
    outcomes = Counter()
    pair_keys = set()
    files = [('encounters.jsonl.gz', summary, summary['rows'])]
    for part in parts:
        require(re.fullmatch(r'cap-events-[0-9]{3,}\.jsonl\.gz', part['path']) is not None
                and part['path'] not in names, 'Duplicate or unsafe original event part')
        names.add(part['path'])
        files.append((part['path'], part, part['events']))
    for name, metadata, expected_rows in files:
        path = resolve_member(native, name)
        require(path.stat().st_size == metadata['stored_bytes'] and sha(path) == metadata['stored_sha256'],
                'Stored inner gzip bytes/SHA differs')
        digest = hashlib.sha256()
        count = size = 0
        with gzip.open(path, 'rb') as stream:
            while True:
                line = stream.readline(2 * 1024**2 + 1)
                if not line:
                    break
                require(len(line) <= 2 * 1024**2 and line.endswith(b'\n'), 'Unexpected original JSONL line')
                row = json.loads(line)
                require(isinstance(row, dict), 'Original JSONL row is not an object')
                digest.update(line)
                count += 1
                size += len(line)
                require(size <= MAX_RAW_BYTES, 'Original inner gzip exceeds frozen raw budget')
                if name == 'encounters.jsonl.gz':
                    key = (row.get('Seed'), row.get('Profile'))
                    require(row.get('Hero') == expected['hero'] and row.get('Group') == expected['group']
                            and row.get('SeedBlock') == expected['block']
                            and type(key[0]) is int and expected['seed_start'] <= key[0] < expected['seed_start'] + 1000
                            and key[1] in ARMS and key not in pair_keys and row.get('Outcome') in OUTCOMES,
                            'Duplicate or incorrect original encounter identity/outcome')
                    pair_keys.add(key)
                    outcomes[row['Outcome']] += 1
        require(digest.hexdigest() == metadata['raw_sha256'] and size == metadata['raw_bytes']
                and count == expected_rows, 'Original inner gzip CRC/raw SHA/row count differs')
        if name != 'encounters.jsonl.gz':
            rows_total += count
            bytes_total += size
    require(rows_total == casts + ticks and bytes_total <= MAX_RAW_BYTES,
            'All original event counts or frozen aggregate raw budget differ')
    require(pair_keys == {(seed, arm) for seed in range(expected['seed_start'], expected['seed_start'] + 1000) for arm in ARMS}
            and dict(outcomes) == validation['outcomes'], 'Missing paired original or retained outcome mismatch')
    archived_gzip = {r['path'] for r in manifest['files'] if r['path'].endswith('.jsonl.gz')}
    expected_gzip = {'outputs/' + unit + '/native/' + name for name, _, _ in files}
    require(archived_gzip == expected_gzip, 'Unreferenced/missing original inner gzip')
    return {'unit': unit, 'source_sha': SOURCE, 'raw_encounters_verified': len(pair_keys),
            'raw_pairs_verified': 1000, 'raw_events_verified': rows_total,
            'actual_casts_verified': casts, 'actual_ticks_verified': ticks,
            'original_outcomes_verified': dict(outcomes), 'inner_gzip_files_verified': len(files),
            'inner_gzip_CRC_raw_SHA_counts_verified': True,
            'runtime_identical_to_original': True, 'source_subset_files_verified_by_cloud': 372}


class CapTransport:
    def __init__(self, args):
        require(args.cloud_host == HOST and args.cloud_root == CLOUD_ROOT,
                'Cloud host/root differs from the authorized Tencent acceptance host')
        self.args = args
        self.evidence = PurePosixPath(args.cloud_root) / 'evidence' / GROUP
        require(PurePosixPath(args.controller) in (self.evidence / 'controller.py',
                                                 self.evidence / 'controller-revision2.py'),
                'Only the explicit owned cloud controller.py is supported')
        self.local = args.local_root.resolve()
        require(self.local.drive.upper() == 'G:' and not self.local.is_symlink(),
                'Original evidence must remain in an unlinked local G directory')
        self.local.mkdir(parents=True, exist_ok=True)
        config = args.private_config.read_text(encoding='utf-8-sig')
        match = re.search(r'set "FANTASYCARD_CLOUD_KEY=(.*?)"', config, re.IGNORECASE)
        require(match is not None, 'Private cloud key configuration is missing')
        self._key = os.path.expandvars(match[1])
        require(Path(self._key).is_file(), 'Private configured cloud key unavailable')
        self.client = None
        self.current = None
        self.last_emit = 0
        self.deadline = time.monotonic() + args.hours * 3600
        self.finished = set()

    def emit(self, data, force=True):
        now = time.monotonic()
        if not force and now - self.last_emit < POLL_SECONDS:
            return
        record = {'at_unix': time.time(), 'whole_task_accepted': False,
                  'full_formal_pending': True, 'capacity_tests_deferred': True} | data
        log = self.local / 'transport-log.jsonl'
        require(not log.is_symlink(), 'Linked local transport log')
        with log.open('a', encoding='utf-8', newline='\n') as stream:
            stream.write(json.dumps(record, ensure_ascii=False) + '\n')
        atomic_write(self.local / 'transport-progress.json', record)
        print(json.dumps(record, ensure_ascii=False), flush=True)
        self.last_emit = now

    def connect(self):
        if self.client is not None:
            self.client.close()
        self.client = paramiko.SSHClient()
        self.client.load_system_host_keys(str(Path.home() / '.ssh/known_hosts'))
        self.client.set_missing_host_key_policy(paramiko.RejectPolicy())
        self.client.connect(HOST, username='ubuntu', key_filename=self._key,
                            look_for_keys=False, allow_agent=False, timeout=10,
                            banner_timeout=12, auth_timeout=12, transport_factory=transport_factory)
        self.client.get_transport().set_keepalive(5)

    def channel(self):
        if self.client is None or self.client.get_transport() is None or not self.client.get_transport().is_active():
            self.connect()
        return self.client.get_transport().open_session(timeout=10)

    def request(self, action, unit=None, receipt=None):
        command = ['python3', self.args.controller, action, '--root', self.args.cloud_root]
        if unit is not None:
            unit_contract(unit)
            command += ['--unit', unit]
        if receipt is not None:
            command += ['--receipt-file', str(receipt)]
        if action == 'launch-next':
            command += ['--output-budget-bytes', str(self.args.output_budget_bytes)]
        channel = self.channel()
        channel.settimeout(60)
        try:
            channel.exec_command(' '.join(shlex.quote(value) for value in command))
            stdout = channel.makefile('rb').read(2 * 1024**2)
            stderr = channel.makefile_stderr('rb').read(65536)
            require(channel.recv_exit_status() == 0 and not stderr,
                    'Cloud controller action failed; original state requires inspection')
            result = json.loads(stdout.decode('utf-8'))
            require(isinstance(result, dict) and result.get('ok') is True,
                    'Cloud controller returned unsuccessful state')
            return result
        finally:
            channel.close()

    def status(self):
        try:
            result = self.request('status')
        except AttentionRequired:
            raise
        except Exception:
            self.connect()
            result = self.request('status')  # Read-only observation, never a restart.
        require(result.get('total_units') == 360 and result.get('adopted_units') == 88
                and result.get('full_formal_pending') is True, 'Frozen full experiment scope changed')
        self.current = result.get('current')
        return result

    @staticmethod
    def live(current):
        state = (current or {}).get('unit_status', {})
        return state.get('MainPID', 0) != 0 or state.get('ActiveState') in (
            'active', 'activating', 'deactivating', 'reloading')

    def mutate(self, action, unit=None, receipt=None):
        try:
            return self.request(action, unit, receipt)
        except Exception:
            observed = None
            try:
                observed = self.status()
            except Exception:
                pass
            self.emit({'state': 'mutation_outcome_requires_exact_inspection', 'action': action,
                       'unit': unit, 'native_live_observed': bool(observed and self.live(observed.get('current'))),
                       'no_mutation_retry': True})
            raise AttentionRequired('Uncertain mutation was not repeated; inspect its exact unit status')

    def directory(self, unit):
        unit_contract(unit)
        path = self.local / unit
        require(path.resolve().is_relative_to(self.local) and not path.is_symlink(), 'Unsafe local unit path')
        path.mkdir(exist_ok=True)
        return path

    def get_json(self, remote, destination):
        require(remote.is_relative_to(self.evidence), 'Metadata read outside owned cloud evidence')
        temporary = destination.with_name(destination.name + '.download-' + uuid.uuid4().hex)
        self.channel().close()  # Establish/revalidate the authenticated connection.
        sftp = self.client.open_sftp()
        try:
            attributes = sftp.lstat(str(remote))
            require(attributes.st_size <= 2 * 1024**2, 'Cloud metadata exceeds its bound')
            sftp.get(str(remote), str(temporary), prefetch=False)
        finally:
            sftp.close()
        data = read(temporary)
        if destination.exists():
            require(sha(destination) == sha(temporary), 'Existing local metadata differs; both originals retained')
            temporary.unlink()
        else:
            os.rename(temporary, destination)
        return data

    def stream_archive(self, directory, unit, manifest_path, manifest, prepared):
        archive = directory / 'delivery.private.tar.gz'
        receipt_path = directory / 'transport-receipt.json'
        budget = prepared['output_budget_bytes']
        require(type(budget) is int and 96 * 1024**2 <= budget <= 512 * 1024**2
                and manifest['output_budget_bytes'] == budget
                and manifest['metadata_reserve_bytes'] == prepared['metadata_reserve_bytes'] == METADATA_RESERVE,
                'Original unit output/metadata budget differs')
        if archive.exists() or receipt_path.exists():
            require(archive.is_file() and receipt_path.is_file(), 'Incomplete prior G archive/receipt retained')
            receipt = read(receipt_path)
            require(receipt.get('ok') is True and receipt.get('unit') == unit
                    and receipt.get('manifest_sha256') == prepared['manifest_sha256']
                    and receipt.get('bytes') == archive.stat().st_size and receipt.get('sha256') == sha(archive)
                    and receipt.get('members') == len(manifest['files'])
                    and receipt.get('output_budget_bytes') == budget, 'Prior G archive proof differs')
            return archive, receipt
        remote_manifest = self.evidence / 'units' / unit / 'delivery-manifest.json'
        code = '''import hashlib,json,sys,tarfile
from pathlib import Path
def require(v):
 if not v:raise ValueError('Frozen cap archive source changed')
def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(65536),b''):h.update(b)
 return h.hexdigest()
M=Path(%r);require(sha(M)==%r);m=json.loads(M.read_text(encoding='utf-8'))
with tarfile.open(fileobj=sys.stdout.buffer,mode='w|gz',dereference=True) as t:
 for row in m['files']:
  p=Path(row['source']);require(p.is_file() and not p.is_symlink() and p.stat().st_size==row['bytes'] and sha(p)==row['sha256'])
  t.add(p,arcname='unit/'+row['path'],recursive=False)
 t.add(M,arcname='unit/manifest.json',recursive=False)
''' % (str(remote_manifest), prepared['manifest_sha256'])
        partial = directory / ('delivery.partial-' + uuid.uuid4().hex + '.tar.gz')
        channel = self.channel()
        channel.settimeout(1)
        digest = hashlib.sha256()
        size = 0
        stderr = bytearray()
        deadline = time.monotonic() + 900
        limit = budget + METADATA_RESERVE
        try:
            channel.exec_command('python3 -')
            channel.sendall(code.encode('utf-8'))
            channel.shutdown_write()
            with partial.open('xb') as stream:
                while True:
                    require(time.monotonic() < deadline, 'Archive observation expired; partial originals retained')
                    if channel.recv_stderr_ready():
                        stderr.extend(channel.recv_stderr(4096))
                        require(len(stderr) <= 65536, 'Excessive cloud archive diagnostic')
                    try:
                        block = channel.recv(BLOCK)
                    except socket.timeout:
                        block = None
                    if block == b'':
                        break
                    if block:
                        stream.write(block)
                        digest.update(block)
                        size += len(block)
                        require(size <= limit, 'Archive exceeded frozen output and metadata budget')
                    self.emit({'state': 'streaming_original_cloud_unit_to_G', 'unit': unit, 'archive_bytes': size}, force=False)
                stream.flush()
                os.fsync(stream.fileno())
            while channel.recv_stderr_ready():
                stderr.extend(channel.recv_stderr(4096))
            require(channel.recv_exit_status() == 0 and not stderr and size > 0,
                    'Cloud archive stream failed; partial original evidence retained')
        finally:
            channel.close()
        require(not archive.exists() and not receipt_path.exists(), 'Concurrent G archive detected')
        os.rename(partial, archive)
        receipt = {'ok': True, 'unit': unit, 'source_sha': SOURCE, 'local_archive': str(archive),
                   'cloud_archive_created': False, 'transfer_mode': 'direct_stream_to_G',
                   'bytes': size, 'sha256': digest.hexdigest(), 'members': len(manifest['files']),
                   'manifest_sha256': sha(manifest_path), 'output_budget_bytes': budget}
        atomic_write(receipt_path, receipt)
        return archive, receipt

    def local_verify(self, directory, unit, archive, receipt):
        extraction = directory / 'verified'
        manifest = verify_archive(archive, receipt, extraction, receipt['output_budget_bytes'] + METADATA_RESERVE)
        verified = verify_unit(extraction, manifest, unit)
        proof = receipt | verified | {'ok': True, 'members_verified': len(manifest['files']),
            'archive_gzip_CRC_verified': True, 'all_original_members_sha256_verified': True,
            'local_directory': str(extraction), 'no_native_business_executed_locally': True,
            'whole_task_accepted': False, 'full_formal_pending': True, 'MAIN_accepted': False}
        path = extraction / 'local-backup-receipt.json'
        if path.exists():
            require(read(path) == proof, 'Prior local proof differs; originals retained')
        else:
            atomic_write(path, proof)
        return path, proof

    def upload_proof(self, proof_path, unit):
        remote = self.evidence / 'units' / unit / 'local-backup-receipt.json'
        temporary = str(remote) + '.upload-' + uuid.uuid4().hex
        sftp = self.client.open_sftp()
        try:
            try:
                existing = sftp.open(str(remote), 'rb')
            except FileNotFoundError:
                existing = None
            if existing is not None:
                with existing:
                    require(existing.read(2 * 1024**2) == proof_path.read_bytes(), 'Cloud backup receipt differs')
            else:
                sftp.put(str(proof_path), temporary, confirm=True)
                with sftp.open(temporary, 'rb') as stream:
                    require(hashlib.sha256(stream.read(2 * 1024**2)).hexdigest() == sha(proof_path),
                            'Uploaded G proof SHA differs')
                sftp.rename(temporary, str(remote))
        except Exception:
            raise AttentionRequired('G proof upload uncertain; cloud cleanup was not issued')
        finally:
            sftp.close()
        return remote

    def finalize(self, current):
        unit = current['unit']
        unit_contract(unit)
        state = current['unit_status']
        result = current.get('result') or {}
        require(not self.live(current) and state.get('MainPID') == 0 and state.get('ExecMainStatus') == 0,
                'Exact native unit is not successful and terminal')
        require(result.get('ok') is True, 'Failed/missing native result preserved; no next launch')
        require(not current.get('cleanup_verified'), 'Previously cleaned current unit needs reconciliation')
        directory = self.directory(unit)
        prepared = self.mutate('prepare-delivery', unit)
        require(prepared.get('unit') == unit, 'Delivery unit differs from observed terminal handle')
        remote = self.evidence / 'units' / unit / 'delivery-manifest.json'
        manifest_path = directory / 'delivery-manifest.json'
        manifest = self.get_json(remote, manifest_path)
        require(sha(manifest_path) == prepared['manifest_sha256'], 'Downloaded original manifest SHA differs')
        archive, receipt = self.stream_archive(directory, unit, manifest_path, manifest, prepared)
        path, proof = self.local_verify(directory, unit, archive, receipt)
        self.emit({'state': 'original_cloud_unit_G_verified', 'unit': unit,
                   'raw_events_verified': proof['raw_events_verified'], 'raw_encounters_verified': 2000,
                   'archive_bytes': proof['bytes']})
        remote_proof = self.upload_proof(path, unit)
        cleanup = self.mutate('cleanup', unit, remote_proof)
        remote_cleanup = self.evidence / 'units' / unit / 'local-storage-cleanup.json'
        cleanup_proof = self.get_json(remote_cleanup, directory / 'cloud-cleanup-receipt.json')
        require(cleanup_proof.get('ok') is True and cleanup_proof.get('unit') == unit,
                'Cloud cleanup proof lacks exact successful unit')
        self.finished.add(unit)
        self.emit({'state': 'original_G_verified_and_cloud_output_reclaimed', 'unit': unit,
                   'new_units_this_session': len(self.finished),
                   'cleanup_verified': cleanup.get('ok') is True})

    def loop(self):
        self.connect()
        while True:
            state = self.status()
            current = state.get('current')
            self.emit({'state': 'observed_exact_cloud_experiment_status',
                       'current': current, 'native_completed_units': state['logical_verified_units'] + int(
                           bool(current and current.get('result', {}) and current['result'].get('ok') is True)),
                       'raw_G_verified_units': state.get('logical_verified_units'),
                       'adopted_units': state['adopted_units'], 'total_units': state['total_units'],
                       'remaining_units': state.get('remaining_units'), 'next_pending': state.get('next_pending')})
            if self.args.once:
                return
            if time.monotonic() >= self.deadline:
                self.emit({'state': 'observation_budget_ended', 'exact_native_job_left_untouched': True})
                return
            if self.live(current):
                require(current.get('unit') and current.get('systemd_unit'), 'Live native job lacks exact identity')
                time.sleep(POLL_SECONDS)
                continue
            if current is not None:
                self.finalize(current)
                continue
            if len(self.finished) >= self.args.max_units:
                self.emit({'state': 'bounded_continuation_complete', 'new_units_G_verified': len(self.finished),
                           'remaining_full_scope_units': state.get('remaining_units'),
                           'no_next_unit_dispatched': True})
                return
            if state.get('next_pending') is None:
                require(state.get('logical_verified_units') == 360, 'Pending scope missing without 360 G proofs')
                self.emit({'state': 'all_360_original_units_G_verified', 'encounters': 720000,
                           'full_statistics_and_applicability_pending': True})
                return
            launched = self.mutate('launch-next')
            if launched.get('launch_deferred_resources') is True:
                require(launched.get('no_startup_created') is True, 'Resource deferral must prove no dispatch')
                self.emit({'state': 'resource_gate_deferred', 'no_native_restart': True,
                           'resource_deferred': launched.get('resource_deferred')})
            else:
                dispatch = launched.get('dispatch_state') or launched.get('startup_state')
                require(dispatch == 'dispatch_observed' or launched.get('started') is True,
                        'Uncertain startup requires inspection; no redispatch')
                name = launched.get('unit')
                unit_contract(name)
                require(launched.get('systemd_unit'), 'Started unit lacks its exact systemd identity')
                observed = None
                # A slow systemd startup receives read-only observations. Neither
                # an observation timeout nor Prepared state dispatches it again.
                for attempt in range(3):
                    observed = self.status()
                    candidate = observed.get('current')
                    require(candidate is not None and candidate.get('unit') == name
                            and candidate.get('systemd_unit') == launched['systemd_unit'],
                            'Observed startup unit differs from exact dispatch')
                    if self.live(candidate) or (candidate.get('result') or {}).get('ok') is True:
                        break
                    if attempt < 2:
                        time.sleep(POLL_SECONDS)
                require(self.live(observed.get('current')) or (observed['current'].get('result') or {}).get('ok') is True,
                        'Exact startup observation remains uncertain; preserved without redispatch')
                self.emit({'state': 'next_exact_native_cloud_unit_observed', 'current': observed['current']})
            time.sleep(POLL_SECONDS)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cloud-host', required=True)
    parser.add_argument('--cloud-root', required=True)
    parser.add_argument('--controller', required=True)
    parser.add_argument('--private-config', type=Path, required=True)
    parser.add_argument('--local-root', type=Path, default=Path('outputs/pr13-tencent-20261009/cap-experiment-full-r2-raw'))
    parser.add_argument('--once', action='store_true', help='Observe exact status; no cloud writes or native starts')
    parser.add_argument('--max-units', type=int, default=272, help='Bound new units, preserving all 360 formal units')
    parser.add_argument('--hours', type=float, default=48, help='Observation lifetime; native jobs left intact at deadline')
    parser.add_argument('--output-budget-bytes', type=int, default=96 * 1024**2)
    args = parser.parse_args()
    transport = lock = None
    try:
        require(1 <= args.max_units <= 272 and 0 < args.hours <= 48, 'Invalid continuation bound')
        require(96 * 1024**2 <= args.output_budget_bytes <= 512 * 1024**2, 'Output budget outside frozen scope')
        transport = CapTransport(args)
        lock = lock_local(transport.local)
        transport.loop()
        return 0
    except Exception as error:
        record = {'state': 'attention_required', 'error': type(error).__name__,
                  'reason': str(error) if isinstance(error, AttentionRequired) else 'Transport or original metadata verification failed; retained for inspection',
                  'no_automatic_restart': True, 'whole_task_accepted': False, 'full_formal_pending': True}
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
