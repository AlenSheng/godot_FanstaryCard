import importlib.util
import json
import subprocess
import time
from pathlib import Path

E = Path('/home/ubuntu/pr13-acceptance-20261009/evidence/Empty-ready-wire-PG-r1-20261014')
OWNER = 'pr13-cap-empty-ready-wire-scheduler-r1'
spec = importlib.util.spec_from_file_location('original_owned_controller',E/'controller.original.py')
m = importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
actual = dict(line.split('=',1) for line in subprocess.check_output(['systemctl','show',OWNER,
    '--property=MainPID,ActiveState'],text=True).splitlines())
assert actual['ActiveState']=='active'
start = time.monotonic()
while True:
    result = m.launch()
    print(json.dumps(result),flush=True)
    if result.get('started'):
        assert not (E/'scheduler-dispatched.original.json').exists()
        (E/'scheduler-dispatched.original.json').write_bytes((json.dumps(result,indent=2)+'\n').encode())
        break
    assert result.get('resource_deferred') and time.monotonic()-start < 1800
    time.sleep(5)
