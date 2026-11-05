from pathlib import Path
import base64,gzip,hashlib,json,shlex,subprocess

stage=Path(__file__).parent/'journey-native-cloud-r4';payload=(stage/'delta.tar.gz').read_bytes();meta=(stage/'complete-manifest.json').read_bytes()
parts=[(f'part-{index:03}.bin',payload[offset:offset+12000]) for index,offset in enumerate(range(0,len(payload),12000))]
parts.append(('metadata.json.gz',gzip.compress(json.dumps(json.loads(meta)).encode(),mtime=0)))
for name,data in parts:
 original=stage/('upload-'+name.removeprefix('part-').removesuffix('.bin')+'.transport.original.json')
 if name.startswith('part-') and original.exists() and json.loads(original.read_text('utf-8'))['returncode']==0:continue
 record=stage/(name+'.retry1.transport.original.json');assert not record.exists()
 source='''from pathlib import Path
import base64,hashlib,json,shutil
root=Path('/home/ubuntu/season-balance-20261102-journey-native-r4');assert root.exists() and not (root/'run').exists()
d=shutil.disk_usage(root);assert d.free>=3*1024**3+8*1024**2 and d.free/d.total>=.05
p=root/_NAME_;assert not p.exists();data=base64.b64decode(_DATA_);assert hashlib.sha256(data).hexdigest()==_SHA_;p.write_bytes(data)
print(json.dumps({'name':p.name,'bytes':len(data),'sha256':_SHA_,'native_started':False}))
'''.replace('_NAME_',repr(name)).replace('_DATA_',repr(base64.b64encode(data).decode())).replace('_SHA_',repr(hashlib.sha256(data).hexdigest()))
 compile(source,name,'exec');(stage/(name+'.retry1.py')).write_text(source,encoding='utf-8')
 command='python3 -c '+shlex.quote('import base64;exec(base64.b64decode('+repr(base64.b64encode(source.encode()).decode())+'))');assert len(command)<30000
 r=subprocess.run(['ssh','-i',r'C:\Users\SHENGJIAHAO\.ssh\gpt-deploy-release.pem','-o','BatchMode=yes','-o','StrictHostKeyChecking=yes','-o','ConnectTimeout=12','ubuntu@43.172.70.182',command],stdin=subprocess.DEVNULL,capture_output=True,text=True,timeout=40)
 record.write_text(json.dumps({'returncode':r.returncode,'stdout':r.stdout,'stderr':r.stderr},indent=2)+'\n',encoding='utf-8');print(json.dumps({'file':name,'returncode':r.returncode}),flush=True);assert r.returncode==0
