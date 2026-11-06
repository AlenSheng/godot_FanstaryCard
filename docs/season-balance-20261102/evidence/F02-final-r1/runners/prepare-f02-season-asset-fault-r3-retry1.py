from pathlib import Path
import json
base=Path(__file__).parent
r=json.loads((base/'f02-season-asset-fault-r3-pre-retry-r1/result.original.json').read_bytes())
assert r['new_root_exists'] is False and r['owned_PG_running'] and len(r['active_tagged_containers'])==1
terminal=json.loads((base/'f02-season-asset-fault-cloud-r3/owned-local-terminal.original.json').read_bytes());assert terminal['exit']!=0 and terminal['guard'] is None
p=base/'run-f02-season-asset-fault-cloud-r3-retry1.py';assert not p.exists()
s=(base/'run-f02-season-asset-fault-cloud-r3.py').read_text(encoding='utf-8');needle="out=base/'f02-season-asset-fault-cloud-r3'";assert s.count(needle)==1
p.write_text(s.replace(needle,"out=base/'f02-season-asset-fault-cloud-r3-retry1'"),encoding='utf-8')
print('Transport retry prepared after authoritative root/container absence; failed transport inputs retained.')
