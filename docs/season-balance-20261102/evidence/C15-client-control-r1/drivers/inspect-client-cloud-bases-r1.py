from pathlib import Path
import base64,json,shlex,subprocess
base=Path(__file__).parent;target=base/'client-cloud-bases-r1.original.json';assert not target.exists()
source='''from pathlib import Path
import hashlib,json,shutil,subprocess
root=Path('/home/ubuntu/season-balance-20261102-journey-client-r5');out=root/'output';d=shutil.disk_usage('/home/ubuntu')
data={'r5_exists':root.exists(),'disk_free':d.free,'disk_ratio':d.free/d.total,'files':sorted(p.name for p in out.iterdir()) if out.exists() else [],'bases':{}}
for n in ['handle.json','terminal.original.json','cleanup.original.json','case-results.json']:
 if (out/n).exists():data[n]=json.loads((out/n).read_text())
for name in ['/opt/fantasycard-github/client','/home/ubuntu/pr13-acceptance-20261009/work/cap-RENDER-r7-inputs/client']:
 p=Path(name);data['bases'][name]={'exists':p.is_dir(),'safe_frame_exists':(p/'assets/generated/ui/safe_slot_frame_locked.png').is_file(),'cue_exists':(p/'assets/audio/ui_click.wav').is_file()}
print(json.dumps(data))
'''
command='sudo -n python3 -c '+shlex.quote('import base64;exec(base64.b64decode('+repr(base64.b64encode(source.encode()).decode())+'))')
r=subprocess.run(['ssh','-i',r'C:\Users\SHENGJIAHAO\.ssh\gpt-deploy-release.pem','-o','BatchMode=yes','-o','StrictHostKeyChecking=yes','-o','ConnectTimeout=12','ubuntu@43.172.70.182',command],capture_output=True,text=True,timeout=35)
target.write_text(json.dumps({'returncode':r.returncode,'stdout':r.stdout,'stderr':r.stderr},indent=2)+'\n',encoding='utf-8');print(target.read_text('utf-8'))
