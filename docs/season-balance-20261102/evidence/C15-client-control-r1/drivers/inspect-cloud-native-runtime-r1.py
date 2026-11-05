from pathlib import Path
import base64,json,shlex,subprocess

base=Path(__file__).parent
target=base/'cloud-native-runtime-readonly-r1.original.json'
assert not target.exists()
source='''from pathlib import Path
import hashlib,json,os,shutil,subprocess
p=Path('/usr/local/bin/godot')
memory={line.split(':')[0]:int(line.split()[1])*1024 for line in Path('/proc/meminfo').read_text().splitlines() if len(line.split())>1 and line.split()[1].isdigit()}
d=shutil.disk_usage('/home/ubuntu')
print(json.dumps({'available_ram':memory['MemAvailable'],'disk_free':d.free,'disk_ratio':d.free/d.total,'engine_exists':p.is_file(),'engine_path':str(p.resolve()),'engine_sha256':hashlib.sha256(p.read_bytes()).hexdigest() if p.is_file() else None,'owned_native_processes':subprocess.check_output(['pgrep','-a','-f','[g]odot']).decode() if any('godot' in q.name.lower() for q in []) else subprocess.run(['pgrep','-a','-f','[g]odot'],capture_output=True,text=True).stdout}))
'''
command='python3 -c '+shlex.quote('import base64;exec(base64.b64decode('+repr(base64.b64encode(source.encode()).decode())+'))')
r=subprocess.run(['ssh','-i',r'C:\Users\SHENGJIAHAO\.ssh\gpt-deploy-release.pem','-o','BatchMode=yes','-o','StrictHostKeyChecking=yes','-o','ConnectTimeout=12','ubuntu@43.172.70.182',command],capture_output=True,text=True,timeout=40)
target.write_text(json.dumps({'returncode':r.returncode,'stdout':r.stdout,'stderr':r.stderr},indent=2)+'\n',encoding='utf-8')
print(target.read_text('utf-8'))
assert r.returncode==0
