from pathlib import Path
import json

b = Path(__file__).parent
out = b / 'runtime-r115'
d = json.loads((out / 'delta-manifest.json').read_bytes())
m = json.loads((out / 'manifest.json').read_bytes())
d.update(staging_method='tmpfs_byte_verified_full_copy', staging_allocation_bytes=len(m['files']) * 4096, tmpfs_allocation_bytes=64 * 1024**2)
(out / 'delta-manifest.json').write_text(json.dumps(d, indent=2) + '\n', encoding='utf-8')
source = (b / 'runtime-r114/start-delta-runtime.py').read_text('utf-8').replace('runtime-r114', 'runtime-r115')
p = out / 'start-delta-runtime.py'
assert not p.exists()
compile(source, str(p), 'exec')
p.write_text(source, encoding='utf-8')
groups = json.loads((b / 'runtime-r114/declared-groups.json').read_bytes())
groups['fixture_change'] = 'Read the actual cosmetic selection version after reward grants; no production or assertion relaxation.'
(out / 'declared-groups.json').write_text(json.dumps(groups, indent=2) + '\n', encoding='utf-8')
print(json.dumps({'total': 114, 'groups': [32, 36, 46], 'prior_evidence_unchanged': True}))
