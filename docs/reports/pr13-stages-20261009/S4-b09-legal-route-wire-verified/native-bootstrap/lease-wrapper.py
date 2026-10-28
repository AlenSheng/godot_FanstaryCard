import hashlib,json,os,sys,time
from pathlib import Path
B=Path('/home/ubuntu/pr13-acceptance-20261009');A='b09-legal-route-r3-20261011';BOOT=B/'evidence/b09-legal-route-bootstrap-r3-20261011';E=B/'evidence'/A;OWNER='pr13-cap-'+A
assert os.environ.get('PR13_B09_LEGAL_ROUTE_LEASE')==OWNER
until=time.monotonic()+7200
while not (BOOT/'admission.json').exists():
 assert time.monotonic()<until,'Readiness lease ended before explicit root admission; no native started'
 time.sleep(5)
v=json.loads((BOOT/'admission.json').read_bytes());assert v['attempt']==A and v['explicit_root_admission'] is True and v['B08_full_G_backup_and_cleanup_verified'] is True and v['cap_previous_original_G_closed'] is True and v['full_Nuget_G_cache_restored_verified'] is True
assert hashlib.sha256((E/'runner.py').read_bytes()).hexdigest()==v['runner_sha256']
assert hashlib.sha256((E/'inputs.json').read_bytes()).hexdigest()==v['inputs_sha256']
os.execv('/usr/bin/python3',['/usr/bin/python3',str(E/'runner.py')])
