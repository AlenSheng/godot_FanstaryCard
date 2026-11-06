from pathlib import Path
import base64,hashlib,io,json,shlex,subprocess,sys,tarfile
stage=Path(__file__).parent/'journey-client-cloud-r7';index=sys.argv[1];target=stage/('observation-'+index+'.original.json');assert not target.exists()
source='''from pathlib import Path
import base64,hashlib,io,json,subprocess,tarfile
root=Path('/home/ubuntu/season-balance-20261102-journey-client-r7');out=root/'output';result={'root_exists':root.exists(),'files':sorted(p.name for p in out.iterdir()) if out.exists() else []}
for name in ['handle.json','terminal.original.json','cleanup.original.json','case-results.json']:
 if (out/name).exists():result[name]=json.loads((out/name).read_text())
if 'handle.json' in result:
 row=subprocess.run(['docker','inspect',result['handle.json']['container_id']],capture_output=True,text=True)
 if row.returncode==0:result['live_state']=json.loads(row.stdout)[0]['State']
if (out/'cleanup.original.json').exists():
 buffer=io.BytesIO()
 with tarfile.open(fileobj=buffer,mode='w:gz') as archive:
  for p in sorted(out.iterdir()):
   if p.is_file():archive.add(p,arcname=p.name)
 data=buffer.getvalue();result['archive_sha256']=hashlib.sha256(data).hexdigest();result['archive_base64']=base64.b64encode(data).decode()
print(json.dumps(result))
'''
command='sudo -n python3 -c '+shlex.quote('import base64;exec(base64.b64decode('+repr(base64.b64encode(source.encode()).decode())+'))')
r=subprocess.run(['ssh','-i',r'C:\Users\SHENGJIAHAO\.ssh\gpt-deploy-release.pem','-o','BatchMode=yes','-o','StrictHostKeyChecking=yes','-o','ConnectTimeout=12','ubuntu@43.172.70.182',command],capture_output=True,text=True,timeout=40)
target.write_text(json.dumps({'returncode':r.returncode,'stdout':r.stdout,'stderr':r.stderr},indent=2)+'\n',encoding='utf-8')
assert r.returncode==0,r.stderr
data=json.loads(r.stdout)
if data.get('archive_base64'):
 raw=base64.b64decode(data.pop('archive_base64'));assert hashlib.sha256(raw).hexdigest()==data['archive_sha256'];(stage/'public.tar.gz').write_bytes(raw);public=stage/'public';assert not public.exists();public.mkdir()
 with tarfile.open(fileobj=io.BytesIO(raw),mode='r:gz') as archive:
  for item in archive.getmembers():
   assert item.isfile() and item.name==Path(item.name).name
   (public/item.name).write_bytes(archive.extractfile(item).read())
print(json.dumps(data,indent=2))
if (stage/'public/import.stderr.original.log').exists():print((stage/'public/import.stderr.original.log').read_text('utf-8')[-8000:])
if (stage/'public/test.stderr.original.log').exists():print((stage/'public/test.stderr.original.log').read_text('utf-8')[-8000:])
