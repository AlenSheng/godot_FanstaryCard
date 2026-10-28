import hashlib
import json
import subprocess
from pathlib import Path

E = Path('/home/ubuntu/pr13-acceptance-20261009/evidence/B12-unexplained-ledger-PG-r1-20261014')
OWNER = 'pr13-cap-b12-unexplained-ledger-scheduler-r1'
unit = Path('/etc/systemd/system')/(OWNER+'.service')
assert not unit.exists() and not (E/'dispatch.original.json').exists()
unit.write_text('[Unit]\nDescription=PR13 exact coordinator verdict faults QA admission reservation\n'
    '[Service]\nType=exec\nUser=root\nExecStart=/usr/bin/python3 '+str(E/'scheduler.original.py')+
    '\nRuntimeMaxSec=1850\nRestart=no\n')
(E/'scheduler-dispatch-intent.original.json').write_bytes((json.dumps({'owner':OWNER,
    'unit_sha256':hashlib.sha256(unit.read_bytes()).hexdigest(),
    'native_restarts':0,'automatic_dispatch_retry':False},indent=2)+'\n').encode())
subprocess.run(['systemctl','daemon-reload'],check=True)
r = subprocess.run(['systemctl','start','--no-block',OWNER])
(E/'scheduler-dispatch-receipt.original.json').write_bytes((json.dumps({'owner':OWNER,'exit_code':r.returncode},indent=2)+'\n').encode())
assert r.returncode==0
print(json.dumps({'ok':True,'scheduler_started':True,'owner':OWNER,'actual_native_handle_will_be_recorded_once':True}))
