import json
import sys
from pathlib import Path
import pr13_stages

C = Path('/control')
mode = sys.argv[1]
if mode == 'baseline':
    path = C / 'published/client/data/catalog.json'
else:
    path = C / 'candidate-catalogs' / (mode + '.json')
try:
    policy = pr13_stages.default_policy(path)
except ValueError as error:
    print(json.dumps({'state': 'Blocked', 'mode': mode, 'reason': str(error)}))
    raise SystemExit(3)
else:
    print(json.dumps({'state': 'ValidDefault', 'mode': mode, 'actual_policy': policy}))
