from pathlib import Path
import base64,gzip,hashlib,json,shlex,subprocess

stage=Path(__file__).parent/'journey-native-cloud-r4';manifest=json.loads((stage/'manifest.json').read_text('utf-8'));base=stage.parent
extras={n:hashlib.sha256((base/'journey-client-cloud-r6/project'/n).read_bytes()).hexdigest() for n in ('project.godot','run.gd')}
audit=json.loads((base/'runtime-r108/collection-audit.json').read_text('utf-8'))
for p in (base/'runtime-r108/public/results/journey-reward-client').iterdir():extras['tests/journey-reward-client/'+p.name]=audit['files']['results/journey-reward-client/'+p.name]
manifest['extras']=extras
packed=gzip.compress(json.dumps(manifest).encode(),mtime=0);assert len(packed)<12000
metadata="""from pathlib import Path
import base64,hashlib,json,shutil
root=Path('/home/ubuntu/season-balance-20261102-journey-native-r4');root.mkdir(exist_ok=True)
d=shutil.disk_usage(root);assert d.free>=3*1024**3+8*1024**2 and d.free/d.total>=.05
p=root/'metadata.json.gz';assert not p.exists();data=base64.b64decode(DATA);assert hashlib.sha256(data).hexdigest()==SHA;p.write_bytes(data)
print(json.dumps({'name':p.name,'bytes':len(data),'sha256':SHA,'native_started':False}))
""".replace('DATA',repr(base64.b64encode(packed).decode())).replace('SHA',repr(hashlib.sha256(packed).hexdigest()))
(stage/'upload-metadata.py').write_text(metadata,encoding='utf-8')
(stage/'complete-manifest.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')
for p in sorted(stage.glob('upload-*.py')):
 target=stage/(p.stem+'.transport.original.json');assert not target.exists()
 source=p.read_text('utf-8');command='python3 -c '+shlex.quote('import base64;exec(base64.b64decode('+repr(base64.b64encode(source.encode()).decode())+'))');assert len(command)<30000
 r=subprocess.run(['ssh','-i',r'C:\Users\SHENGJIAHAO\.ssh\gpt-deploy-release.pem','-o','BatchMode=yes','-o','StrictHostKeyChecking=yes','-o','ConnectTimeout=12','ubuntu@43.172.70.182',command],stdin=subprocess.DEVNULL,capture_output=True,text=True,timeout=40)
 target.write_text(json.dumps({'returncode':r.returncode,'stdout':r.stdout,'stderr':r.stderr},indent=2)+'\n',encoding='utf-8');print(json.dumps({'file':p.name,'returncode':r.returncode}),flush=True);assert r.returncode==0,r.stderr
