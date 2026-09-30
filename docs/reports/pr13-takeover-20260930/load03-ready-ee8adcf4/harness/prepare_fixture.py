"""Copy seven byte-verified fixed-source dependencies beside preserved test wrappers."""
import hashlib
import json
from pathlib import Path
import shutil

root = Path(__file__).resolve().parents[1]
proof = json.loads((root / 'evidence/SOURCE_PROOF.json').read_text())
for entry in proof['files']:
    if not entry['path'].startswith('fixture/'):
        continue
    relative = entry['path'][len('fixture/'):]
    src = root / 'source/client' / relative
    assert hashlib.sha256(src.read_bytes()).hexdigest() == entry['sha256'], relative
    dst = root / entry['path']
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
print('Prepared seven fixed-source dependencies; no test execution counted.')
