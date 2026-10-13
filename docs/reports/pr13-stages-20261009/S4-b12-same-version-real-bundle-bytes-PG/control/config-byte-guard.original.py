import json
import sys
from pathlib import Path
import pr13_stages

try:
    result = pr13_stages.config_identity(Path(sys.argv[1]))
except ValueError as error:
    print(json.dumps({'state': 'Rejected', 'reason': str(error)}))
    raise SystemExit(3)
else:
    print(json.dumps({'state': 'Valid', **result}))
