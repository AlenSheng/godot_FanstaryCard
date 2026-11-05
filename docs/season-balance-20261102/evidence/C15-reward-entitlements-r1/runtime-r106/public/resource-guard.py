from pathlib import Path
import time,json,subprocess,shutil
root=Path('/home/ubuntu/season-balance-20261102-a03-runtime-r106');h=json.loads((root/'runtime-handle.json').read_text());cid=h['container_id']
with (root/'resource-guard.original.jsonl').open('x') as log:
 while True:
  p=json.loads(subprocess.check_output(['docker','inspect',cid]))[0];assert p['Config']['Labels']['com.fantasycard.task']==h['label']
  m=dict(l.split(':',1) for l in Path('/proc/meminfo').read_text().splitlines());d=shutil.disk_usage(root)
  row=dict(at=time.time(),available_ram=int(m['MemAvailable'].split()[0])*1024,free_disk=d.free,disk_fraction=d.free/d.total,state=p['State']['Status']);log.write(json.dumps(row)+'\n');log.flush()
  if p['State']['Status']=='exited':
   (root/'guard-terminal.original.json').write_text(json.dumps(dict(state='exited',exit_code=p['State']['ExitCode'],owned_runtime_only=True))+'\n');break
  reason='ResourceProtectionStop' if row['available_ram']<500*1024**2 or d.free<3*1024**3 or d.free/d.total<.05 else 'ObservationWindowStop' if time.time()-h['started_at']>600 else None
  if reason:
   subprocess.run(['docker','stop','--time','10',cid],check=True)
   (root/'guard-terminal.original.json').write_text(json.dumps(dict(state=reason,owned_runtime_only=True,**row))+'\n');break
  time.sleep(2)
