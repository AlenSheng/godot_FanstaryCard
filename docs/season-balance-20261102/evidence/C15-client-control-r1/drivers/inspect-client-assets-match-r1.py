from pathlib import Path
import base64,json,shlex,subprocess
base=Path(__file__).parent;target=base/'client-assets-match-r1.original.json';assert not target.exists()
pins=json.loads((base/'journey-client-cloud-r6/source-pin.json').read_text('utf-8'));assets={n.removeprefix('client/'):h for n,h in pins.items() if Path(n).suffix in ('.png','.wav')}
source='''from pathlib import Path
import hashlib,json
root=Path('/home/ubuntu/pr13-acceptance-20261009');candidates=[root/'work/cap-RENDER-r7-inputs/client']
for parent in [root,root/'work',root/'evidence',root/'shared']:
 if parent.is_dir():
  for p in parent.iterdir():
   if p.is_dir() and 'UI-final-effect-final-r1-20261016' in p.name:candidates.append(p/'client')
assets=ASSET_PINS
matched={};missing={}
for name,digest in assets.items():
 for base in candidates:
  p=base/name
  if p.is_file() and hashlib.sha256(p.read_bytes()).hexdigest()==digest:matched[name]=str(base);break
 else:missing[name]=digest
print(json.dumps({'bases':[str(p) for p in candidates],'matched':matched,'missing':missing}))
'''.replace('ASSET_PINS',repr(assets))
command='sudo -n python3 -c '+shlex.quote('import base64;exec(base64.b64decode('+repr(base64.b64encode(source.encode()).decode())+'))')
r=subprocess.run(['ssh','-i',r'C:\Users\SHENGJIAHAO\.ssh\gpt-deploy-release.pem','-o','BatchMode=yes','-o','StrictHostKeyChecking=yes','-o','ConnectTimeout=12','ubuntu@43.172.70.182',command],capture_output=True,text=True,timeout=40)
target.write_text(json.dumps({'returncode':r.returncode,'stdout':r.stdout,'stderr':r.stderr},indent=2)+'\n',encoding='utf-8');print(target.read_text('utf-8'))
