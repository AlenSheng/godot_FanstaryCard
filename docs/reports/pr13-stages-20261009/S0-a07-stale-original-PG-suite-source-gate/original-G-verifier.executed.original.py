"""Original PG provenance byte/XML audit; no native or statistics execution."""
import gzip
import hashlib
import json
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path

B = Path(__file__).parent
R = B.parents[1]
S = R / 'docs/reports/pr13-stages-20261009/S3-a07-current-numerical-postgres-nine'
OUT = B / 'A07-stale-PG-suite-original-G-audit-r1'
assert not OUT.exists()


def sha(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 ** 2), b''):
            h.update(chunk)
    return h.hexdigest()


receipt = json.loads((S / 'complete-original-G-receipt.json').read_bytes())
manifest_path = B / 'current-PG-numerical-R10-complete-originals-on-G/delivery-manifest.json'
manifest = json.loads(manifest_path.read_bytes())
assert sha(manifest_path) == receipt['manifest_sha256'] and len(manifest['files']) == 2199
G = Path(receipt['local_directory'])
archive = Path(receipt['local_archive'])
assert archive.stat().st_size == receipt['archive_bytes'] and sha(archive) == receipt['archive_sha256']
with gzip.open(archive, 'rb') as stream:
    while stream.read(1024 ** 2):
        pass
head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=R, text=True).strip()
source_members = 0
for row in manifest['files']:
    path = G / row['path']
    assert path.stat().st_size == row['bytes'] and sha(path) == row['sha256']
    if row['path'].startswith('frozen-source/'):
        relative = row['path'][len('frozen-source/'):]
        raw = subprocess.check_output(['git', 'show', head + ':' + relative], cwd=R)
        assert len(raw) == row['bytes'] and hashlib.sha256(raw).hexdigest() == row['sha256']
        source_members += 1
assert source_members == 328
result = json.loads((S / 'native-result.original.json').read_bytes())
assert result['ok'] and result['exit_code'] == 0 and not result['oom_killed']
assert result['owned_containers_removed'] and result['remaining_owned_fixture_schemas'] == 0
assert result['frozen_source_and_package_bytes_unchanged']
tree = ET.parse(S / 'native-nine.original.trx')
counters = {key: int(value) for key, value in tree.find('.//{*}Counters').attrib.items()}
assert counters['total'] == counters['executed'] == counters['passed'] == 9
assert counters['failed'] == counters['notExecuted'] == 0
required = {row.find('{*}TestMethod').attrib['name']: 1 for row in tree.findall('.//{*}UnitTest')}
assert len(required) == 9 and head != result['frozen_release_sha']
proof = {'ok': True, 'native_clean': True, 'owned_container_removed': True, 'source_inputs_match_git': True,
         'implementation_source_sha': head, 'actual_original_native_source_sha': result['frozen_release_sha'],
         'all_original_G_members_rehashed': 2199, 'current_Git_source_members': 328,
         'original_archive_SHA_and_CRC_rechecked': True, 'original_native_unskipped_passed_rows': 9,
         'actual_original_native_TRX_sha256': sha(S / 'native-nine.original.trx'),
         'actual_original_native_result_sha256': sha(S / 'native-result.original.json'),
         'actual_original_required_methods': required, 'native_reexecuted_or_new_samples_added': False,
         'scope': 'Actual original PostgreSQL suite provenance only; later Tencent guard must reject unchanged old source label',
         'MAIN_accepted': False}
OUT.mkdir()
(OUT / 'independent-G-audit.original.json').write_bytes((json.dumps(proof, indent=2) + '\n').encode())
print(json.dumps({key: value for key, value in proof.items() if key != 'actual_original_required_methods'}))
