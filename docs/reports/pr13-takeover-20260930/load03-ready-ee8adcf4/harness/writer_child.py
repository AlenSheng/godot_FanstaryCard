"""Real owned process that writes supplied model status and JSONL to real files."""
import json
import os
from pathlib import Path
import sys
for line in sys.stdin:
    request=json.loads(line)
    if request.get('quit'):break
    status=request['status'];status['pid']=os.getpid();path=Path(request['path'])
    path.write_text(json.dumps(status))
    Path(str(path)+'.status.json').write_text(json.dumps(status))
    audit=Path(str(path)+'.telemetry.jsonl')
    with audit.open('a' if request.get('append') else 'w') as f:
        for row in request['audit']:f.write(json.dumps(row)+'\n')
    print(json.dumps({'pid':os.getpid(),'status_path':str(path),'status_seq':status['status_seq']}),flush=True)
