import json,subprocess,time,shutil,os
from pathlib import Path
root=Path('/home/ubuntu/season-balance-20261102-a03-storage-r91');h=json.loads((root/'sdk-handle.json').read_text());cid=h['container_id']
with (root/'resource-guard.original.jsonl').open('x') as log:
 while True:
  p=json.loads(subprocess.check_output(['docker','inspect',cid]))[0]
  assert p['Config']['Labels']['com.fantasycard.task']=='season-balance-20261102-a03-storage-r91'
  m={l.split(':')[0]:int(l.split()[1])*1024 for l in Path('/proc/meminfo').read_text().splitlines() if len(l.split())>1 and l.split()[1].isdigit()};d=shutil.disk_usage(root)
  row={'at':time.time(),'available_ram':m['MemAvailable'],'free_disk':d.free,'disk_fraction':d.free/d.total,'state':p['State']['Status']};log.write(json.dumps(row)+'\n');log.flush()
  if p['State']['Status']=='exited':
   (root/'guard-terminal.original.json').write_text(json.dumps({'state':'exited','exit_code':p['State']['ExitCode'],'owned_sdk_only':True})+'\n');break
  if m['MemAvailable']<500*1024**2 or d.free<3*1024**3 or d.free/d.total<.05:
   subprocess.run(['docker','stop','--time','10',cid],check=True)
   (root/'guard-terminal.original.json').write_text(json.dumps({'state':'ResourceProtectionStop','owned_sdk_only':True,**row})+'\n');break
  time.sleep(2)
