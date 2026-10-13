import hashlib
import json
import sys
from pathlib import Path
import pr13_stages

root = Path(__file__).resolve().parents[1]
version = (root / 'server/config/generated/fantasycard.config.version.txt').read_text().strip()
if sys.argv[1] == 'positive':
    checks = []
    for side, published in [('server', 'server/config/generated'), ('client', 'client/data/generated')]:
        for suffix in ['bytes', 'sha256', 'version.txt']:
            name = 'fantasycard.config.' + suffix
            original = (root / published / name).read_bytes()
            exported = (root / 'original-export' / side / name).read_bytes()
            assert original == exported
            checks.append({'side': side, 'name': name, 'byte_equal': True,
                           'sha256': hashlib.sha256(exported).hexdigest()})
    print(json.dumps({'state': 'ValidExport', 'version': version, 'actual_native_generated_files': checks}))
elif sys.argv[1] == 'negative':
    output = root / 'source-mismatch-stage'
    assert not output.exists()
    try:
        pr13_stages.freeze(output, config_export=root / 'changed-export')
    except ValueError as error:
        assert str(error) == 'Source re-export differs from frozen published config'
        assert not output.exists()
        print(json.dumps({'state': 'Blocked', 'reason': str(error), 'runtime_stage_created': output.exists()}))
        raise SystemExit(3)
    else:
        raise AssertionError('Current source/export mismatch accepted')
else:
    raise ValueError('Unknown declared control mode')
