from pathlib import Path
import base64,hashlib,io,json,shlex,subprocess,tarfile

stage=Path(__file__).parent/'journey-native-cloud-r4';out=stage/'start.stdout.original.log';assert not out.exists()
meta=json.loads((stage/'complete-manifest.json').read_text('utf-8'))
assert all(hashlib.sha256(Path(n).read_bytes()).hexdigest()==h for n,h in meta['current'].items())
chunks=len(list(stage.glob('upload-[0-9]*.py')))
for index in range(chunks):
 original=stage/f'upload-{index:03}.transport.original.json'
 retry=stage/f'part-{index:03}.bin.retry1.transport.original.json'
 record=json.loads((retry if retry.exists() else original).read_text('utf-8'));assert record['returncode']==0
 uploaded=json.loads(record['stdout']);part=(stage/'delta.tar.gz').read_bytes()[index*12000:(index+1)*12000]
 assert uploaded['name']==f'part-{index:03}.bin' and uploaded['sha256']==hashlib.sha256(part).hexdigest() and uploaded['bytes']==len(part)
assert json.loads((stage/'metadata.json.gz.retry1.transport.original.json').read_text('utf-8'))['returncode']==0
source=r'''from pathlib import Path
import base64,gzip,hashlib,io,json,os,shutil,subprocess,tarfile,time
transfer=Path('/home/ubuntu/season-balance-20261102-journey-native-r4');root=transfer/'run';assert not root.exists();root.mkdir()
output=root/'output';output.mkdir();output.chmod(0o777)
meta=json.loads(gzip.decompress((transfer/'metadata.json.gz').read_bytes()))
payload=b''.join((transfer/f'part-{index:03}.bin').read_bytes() for index in range(CHUNKS))
assert len(payload)==meta['delta_bytes'] and hashlib.sha256(payload).hexdigest()==meta['delta_sha256']
base=Path('/home/ubuntu/season-balance-20261102-journey-client-r7/input')
def record(name,value):
 p=output/name;assert not p.exists();p.write_text(json.dumps(value,indent=2)+chr(10))
def resources():
 m={s.split(':')[0]:int(s.split()[1])*1024 for s in Path('/proc/meminfo').read_text().splitlines() if len(s.split())>1 and s.split()[1].isdigit()};d=shutil.disk_usage(root)
 return {'ram':m['MemAvailable'],'disk':d.free,'ratio':d.free/d.total}
samples=[]
for _ in range(3):samples.append(resources());time.sleep(1)
record('admission.original.json',samples)
assert all(s['ram']>=1800*1024**2 and s['disk']>=3*1024**3+8*1024**2 and s['ratio']>=.05 for s in samples)
owner='season-balance-20261102-journey-native-r4'
def docker(*args):return subprocess.check_output(['docker',*args],stderr=subprocess.STDOUT).decode().strip()
assert not docker('ps','-aq','--filter','label=com.fantasycard.task='+owner)
input_dir=root/'input';input_dir.mkdir()
for name,digest in meta['old'].items():
 relative=name.removeprefix('client/');p=base/relative;assert hashlib.sha256(p.read_bytes()).hexdigest()==digest
 target=input_dir/relative;target.parent.mkdir(parents=True,exist_ok=True);os.link(p,target)
for name,digest in meta['extras'].items():
 p=base/name;assert hashlib.sha256(p.read_bytes()).hexdigest()==digest
 target=input_dir/name;target.parent.mkdir(parents=True,exist_ok=True);os.link(p,target)
with tarfile.open(fileobj=io.BytesIO(payload),mode='r:gz') as archive:
 members=archive.getmembers();assert {m.name for m in members}=={n.removeprefix('client/') for n in meta['changed']}
 for item in members:
  assert item.isfile() and not Path(item.name).is_absolute() and '..' not in Path(item.name).parts
  p=input_dir/item.name;p.unlink();p.write_bytes(archive.extractfile(item).read())
assert all(hashlib.sha256((input_dir/n.removeprefix('client/')).read_bytes()).hexdigest()==h for n,h in meta['current'].items())
record('input-verification.original.json',{'files':len(meta['current']),'changed':meta['changed'],'delta_sha256':meta['delta_sha256'],'base':str(base),'all_current_source_bytes_verified':True,'old_files_unlinked_before_changes':True})
runner=input_dir/'runner.py'
runner.write_text("""from pathlib import Path
import hashlib,json,shutil,subprocess
p=Path('/tmp/project');shutil.copytree('/input',p);(p/'runner.py').unlink()
engine=shutil.which('godot');assert engine
version=subprocess.check_output([engine,'--headless','--version'],text=True).strip();digest=hashlib.sha256(Path(engine).read_bytes()).hexdigest()
Path('/output/engine.json').write_text(json.dumps({'path':engine,'version':version,'sha256':digest}))
assert version=='4.7.2.stable.official.ed1daf0bf' and digest=='8d106cbe6144c2dc7e881d61d2429c1a8a76e6b22ef48bd5e48dcf934953f71e'
for name,args in [('import',['--editor','--import','--quit']),('test',['--script','res://run.gd'])]:
 r=subprocess.run(['nice','-n','10',engine,'--headless','--audio-driver','Dummy','--path',str(p),*args],capture_output=True,text=True,timeout=90)
 Path('/output/'+name+'.stdout.original.log').write_text(r.stdout);Path('/output/'+name+'.stderr.original.log').write_text(r.stderr)
 print(json.dumps({'stage':name,'exit_code':r.returncode}),flush=True)
 if r.returncode or 'ERROR:' in r.stdout+r.stderr:raise SystemExit(2)
shutil.copyfile(p/'case-results.json','/output/case-results.json')
""")
current=resources();assert current['ram']>=1800*1024**2 and current['disk']>=3*1024**3+8*1024**2 and current['ratio']>=.05
image='sha256:180f524270f6ac28d2fe0ff29707fb392387d7b766f731e41fda1e45e8230520'
cid=docker('create','--name',owner,'--label','com.fantasycard.task='+owner,'--network','none','--read-only','--memory','1200m','--memory-swap','1200m','--cpus','1','--pids-limit','256','--tmpfs','/tmp:rw,nosuid,nodev,size=134217728','--user','1000:1000','--log-driver','json-file','--log-opt','max-size=1m','--log-opt','max-file=1','-e','HOME=/tmp/home','-e','XDG_DATA_HOME=/tmp/data','-e','XDG_CONFIG_HOME=/tmp/config','-e','XDG_CACHE_HOME=/tmp/cache','-e','FANTASYCARD_SERVER_URL=http://127.0.0.1:9','-v',str(input_dir)+':/input:ro','-v',str(output)+':/output','--entrypoint','python3',image,'/input/runner.py')
record('handle.json',{'container_id':cid,'owner':owner,'image':image,'delta_sha256':meta['delta_sha256']});docker('start',cid);start=time.monotonic();guard=[];failure=None
while True:
 state=json.loads(docker('inspect',cid))[0]['State'];sample=resources();guard.append(sample)
 if state['Status']=='exited':break
 if sample['ram']<500*1024**2 or sample['disk']<3*1024**3 or sample['ratio']<.05 or time.monotonic()-start>210:
  failure=sample;docker('kill',cid);state=json.loads(docker('inspect',cid))[0]['State'];break
 time.sleep(1)
record('resource-guard.original.json',guard);record('terminal.original.json',{'state':state,'guard_failure':failure})
(output/'container.original.log').write_text(docker('logs',cid))
row=json.loads(docker('inspect',cid))[0];assert row['Config']['Labels']['com.fantasycard.task']==owner and row['State']['Status']=='exited';record('inspect.original.json',row)
docker('rm',cid)
assert all(hashlib.sha256((base/n.removeprefix('client/')).read_bytes()).hexdigest()==h for n,h in meta['old'].items())
assert all(hashlib.sha256((base/n).read_bytes()).hexdigest()==h for n,h in meta['extras'].items())
record('cleanup.original.json',{'container_removed':True,'all_original_input_bytes_unchanged':True,'source_count':len(meta['old']),'extra_count':len(meta['extras'])})
buffer=io.BytesIO()
with tarfile.open(fileobj=buffer,mode='w:gz') as archive:
 for p in sorted(output.iterdir()):
  if p.is_file():archive.add(p,arcname=p.name)
data=buffer.getvalue();print(json.dumps({'sha256':hashlib.sha256(data).hexdigest(),'archive_base64':base64.b64encode(data).decode()}))
'''.replace('CHUNKS',str(chunks))
(stage/'remote.original.py').write_text(source,encoding='utf-8')
command='sudo -n python3 -c '+shlex.quote('import base64;exec(base64.b64decode('+repr(base64.b64encode(source.encode()).decode())+'))');assert len(command)<30000
r=subprocess.run(['ssh','-i',r'C:\Users\SHENGJIAHAO\.ssh\gpt-deploy-release.pem','-o','BatchMode=yes','-o','StrictHostKeyChecking=yes','-o','ConnectTimeout=12','-o','ServerAliveInterval=15','-o','ServerAliveCountMax=12','ubuntu@43.172.70.182',command],stdin=subprocess.DEVNULL,capture_output=True,text=True,timeout=270)
out.write_text(r.stdout,encoding='utf-8');(stage/'start.stderr.original.log').write_text(r.stderr,encoding='utf-8');assert r.returncode==0,(r.returncode,r.stderr[-2500:])
data=json.loads(r.stdout);raw=base64.b64decode(data['archive_base64']);assert hashlib.sha256(raw).hexdigest()==data['sha256'];(stage/'public.tar.gz').write_bytes(raw)
public=stage/'public';assert not public.exists();public.mkdir()
with tarfile.open(fileobj=io.BytesIO(raw),mode='r:gz') as archive:
 for item in archive.getmembers():
  assert item.isfile() and item.name==Path(item.name).name
  (public/item.name).write_bytes(archive.extractfile(item).read())
assert all(hashlib.sha256(Path(n).read_bytes()).hexdigest()==h for n,h in meta['current'].items())
for name in ['terminal.original.json','case-results.json','import.stderr.original.log','test.stderr.original.log']:
 if (public/name).exists():print(name,(public/name).read_text('utf-8')[-7000:])
