from pathlib import Path
import json

b = Path(__file__).parent
for old, new, replacements in [
    ('run-asset-composite-local-r3.py', 'run-asset-composite-local-r4.py', [('asset-composite-local-r3', 'asset-composite-local-r4')]),
    ('control-isolated-PG-wal-budget.py', 'control-isolated-PG-wal-budget-r2.py', [('wal-budget-control-20261105.json', 'wal-budget-control-20261105-r2.json'), ("+'-r1.original.json'", "+'-r2.original.json'")]),
    ('setup-asset-runtime114-file-transfer.py', 'setup-asset-runtime115-file-transfer.py', [('runtime-r114', 'runtime-r115')]),
    ('transfer-r114-stream-sftp.py', 'transfer-r115-stream-sftp.py', [('runtime-r114', 'runtime-r115')]),
    ('verify-r114-complete-stream.py', 'verify-r115-complete-stream.py', [('runtime-r114', 'runtime-r115')]),
    ('start-r114-from-verified-file.py', 'start-r115-from-verified-file.py', [('runtime-r114', 'runtime-r115')]),
    ('observe-asset-composite-r114.py', 'observe-asset-composite-r115.py', [('runtime-r114', 'runtime-r115')]),
    ('collect-asset-grouped-r114.py', 'collect-asset-grouped-r115.py', [('runtime-r114', 'runtime-r115')]),
]:
    path = b / new
    assert not path.exists()
    source = (b / old).read_text('utf-8')
    for before, after in replacements:
        assert before in source
        source = source.replace(before, after)
    compile(source, str(path), 'exec')
    path.write_text(source, encoding='utf-8')
print(json.dumps({'prepared': 'r115', 'prior_originals_unchanged': True, 'scope': 'same 114 cases; fixture reads actual cosmetic selection version'}))
