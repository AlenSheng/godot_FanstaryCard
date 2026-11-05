from pathlib import Path
import base64,hashlib,io,json,re,shlex,shutil,subprocess,tarfile,sys

sys.stdout.reconfigure(encoding='utf-8')
repo=Path.cwd();base=Path(__file__).parent;work=base/'journey-client-cloud-r5'
assert not work.exists();work.mkdir()
project=work/'project';project.mkdir();pins={};pending=['tests/test_journey_reward_controller.gd','ui/main.gd','tests/ui_visual_review.gd','audio/sound_service.gd'] + [p.relative_to(repo/'client').as_posix() for p in (repo/'client/assets/audio').glob('*.wav')]
while pending:
    name=pending.pop()
    if 'client/'+name in pins:continue
    if chr(37) in name:continue
    raw=(repo/'client'/name).read_bytes();pins['client/'+name]=hashlib.sha256(raw).hexdigest()
    target=project/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(raw)
    if target.suffix=='.tscn':pending+=re.findall(r'path="res://([^"]+)"',raw.decode('utf-8-sig'))
    if target.suffix=='.gd':pending+=re.findall(r'(?:preload|load)\(\s*"res://([^"]+)"',raw.decode('utf-8-sig'))+re.findall(r'extends\s+"res://([^"]+)"',raw.decode('utf-8-sig'))
for source in list((repo/'client/data').glob('*.json'))+list((repo/'client/data/locales').glob('*.json')):
    name=source.relative_to(repo/'client');target=project/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source,target);pins['client/'+name.as_posix()]=hashlib.sha256(source.read_bytes()).hexdigest()
audit=json.loads((base/'runtime-r108/collection-audit.json').read_text('utf-8'))
target=project/'tests/journey-reward-client';target.mkdir(parents=True)
for source in (base/'runtime-r108/public/results/journey-reward-client').iterdir():
    raw=source.read_bytes();assert hashlib.sha256(raw).hexdigest()==audit['files']['results/journey-reward-client/'+source.name];(target/source.name).write_bytes(raw)
(project/'project.godot').write_text('[application]\nconfig/name="Journey controller cloud isolated fixture"\n[autoload]\nGame="*res://state/game_store.gd"\nSound="*res://audio/sound_service.gd"\n[rendering]\nrenderer/rendering_method="gl_compatibility"\n',encoding='utf-8')
shutil.copyfile(base/'journey-controller-native-r2/run.gd',project/'run.gd')
runner=(project/'run.gd').read_text('utf-8')
runner=runner.replace('    var script = load', '    var ui_scripts = ["res://ui/main.gd", "res://ui/reference_ui.gd", "res://ui/season_journey_reward_view.gd", "res://ui/season_cosmetic_art.gd", "res://tests/ui_visual_review.gd"]\n    for path in ui_scripts:\n        var candidate = load(path)\n        if candidate == null or not candidate.can_instantiate():\n            quit(3)\n            return\n    var script = load')
(project/'run.gd').write_text(runner,encoding='utf-8')

(work/'source-pin.json').write_text(json.dumps(pins,indent=2)+'\n',encoding='utf-8')
buffer=io.BytesIO()
with tarfile.open(fileobj=buffer,mode='w:gz') as archive:
    for source in sorted(project.rglob('*')):
        if source.is_file():archive.add(source,arcname=source.relative_to(project).as_posix())
payload=buffer.getvalue();assert len(payload)<16*1024**2;(work/'input.tar.gz').write_bytes(payload)
remote=r'''from pathlib import Path
import base64,hashlib,io,json,os,shutil,subprocess,tarfile,time
root=Path('/home/ubuntu/season-balance-20261102-journey-client-r5')
assert not root.exists();root.mkdir();output=root/'output';output.mkdir()
reserve=500*1024**2;disk_floor=3*1024**3;admission=1800*1024**2
def resources():
 m={s.split(':')[0]:int(s.split()[1])*1024 for s in Path('/proc/meminfo').read_text().splitlines() if len(s.split())>1 and s.split()[1].isdigit()};d=shutil.disk_usage(root)
 return {'available_ram':m['MemAvailable'],'disk_free':d.free,'disk_ratio':d.free/d.total}
def record(name,value):
 p=output/name;assert not p.exists();p.write_text(json.dumps(value,indent=2)+'\n')
samples=[]
for _ in range(3):samples.append(resources());time.sleep(1)
record('admission.original.json',samples)
assert all(x['available_ram']>=admission and x['disk_free']>=disk_floor+8*1024**2 and x['disk_ratio']>=.05 for x in samples),'cloud resource admission rejected before container start'
payload=base64.b64decode(PAYLOAD);assert hashlib.sha256(payload).hexdigest()==PAYLOAD_SHA
input_dir=root/'input';input_dir.mkdir()
with tarfile.open(fileobj=io.BytesIO(payload),mode='r:gz') as archive:
 for item in archive.getmembers():
  assert item.isfile() and not Path(item.name).is_absolute() and '..' not in Path(item.name).parts
  p=input_dir/item.name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(archive.extractfile(item).read())
runner=input_dir/'runner.py'
runner.write_text("""from pathlib import Path
import hashlib,json,os,shutil,subprocess
p=Path('/tmp/project');shutil.copytree('/input',p);p.joinpath('runner.py').unlink()
engine=shutil.which('godot');assert engine
version=subprocess.check_output([engine,'--headless','--version'],text=True).strip()
Path('/output/engine.json').write_text(json.dumps({'path':engine,'version':version,'sha256':hashlib.sha256(Path(engine).read_bytes()).hexdigest()}))
assert version.startswith('4.7.2.')
for name,args in [('import',['--editor','--import','--quit']),('test',['--script','res://run.gd'])]:
 r=subprocess.run([engine,'--headless','--audio-driver','Dummy','--path',str(p),*args],capture_output=True,text=True,timeout=90)
 Path('/output/'+name+'.stdout.original.log').write_text(r.stdout);Path('/output/'+name+'.stderr.original.log').write_text(r.stderr)
 print(json.dumps({'stage':name,'exit_code':r.returncode}),flush=True)
 if r.returncode or 'ERROR:' in r.stdout+r.stderr:raise SystemExit(2)
shutil.copyfile(p/'case-results.json','/output/case-results.json')
""")
os.chmod(output,0o777)
current=resources();assert current['available_ram']>=admission and current['disk_free']>=disk_floor+8*1024**2 and current['disk_ratio']>=.05
owner='season-balance-20261102-journey-client-r5'
image='sha256:180f524270f6ac28d2fe0ff29707fb392387d7b766f731e41fda1e45e8230520'
def docker(*args):return subprocess.check_output(['docker',*args],stderr=subprocess.STDOUT).decode().strip()
assert not docker('ps','-aq','--filter','label=com.fantasycard.task='+owner)
cid=docker('create','--name',owner,'--label','com.fantasycard.task='+owner,'--network','none','--read-only','--memory','1200m','--memory-swap','1200m','--cpus','1','--pids-limit','256','--tmpfs','/tmp:rw,nosuid,nodev,size=134217728','--shm-size','16m','--user','1000:1000','--log-driver','json-file','--log-opt','max-size=1m','--log-opt','max-file=1','-e','HOME=/tmp/home','-e','XDG_DATA_HOME=/tmp/data','-e','XDG_CONFIG_HOME=/tmp/config','-e','XDG_CACHE_HOME=/tmp/cache','-e','FANTASYCARD_SERVER_URL=http://127.0.0.1:9','-v',str(input_dir)+':/input:ro','-v',str(output)+':/output', '--entrypoint','python3',image,'/input/runner.py')
handle={'container_id':cid,'owner':owner,'image':image,'payload_sha256':PAYLOAD_SHA};record('handle.json',handle)
docker('start',cid);started=time.monotonic();guard=[];guard_failure=None
while True:
 state=json.loads(docker('inspect',cid))[0]['State'];sample=resources();guard.append(sample)
 if state['Status']=='exited':break
 if sample['available_ram']<reserve or sample['disk_free']<disk_floor or sample['disk_ratio']<.05 or time.monotonic()-started>210:
  guard_failure={'sample':sample,'elapsed':time.monotonic()-started};docker('kill',cid);state=json.loads(docker('inspect',cid))[0]['State'];break
 time.sleep(1)
record('resource-guard.original.json',guard)
record('terminal.original.json',{'state':state,'guard_failure':guard_failure})
output.joinpath('container.original.log').write_text(docker('logs',cid))
row=json.loads(docker('inspect',cid))[0];assert row['Config']['Labels']['com.fantasycard.task']==owner and row['State']['Status']=='exited'
record('inspect.original.json',row)
docker('rm',cid);record('cleanup.original.json',{'container_removed':True,'input_retained':True})
out=io.BytesIO()
with tarfile.open(fileobj=out,mode='w:gz') as archive:
 for p in sorted(output.iterdir()):
  if p.is_file():archive.add(p,arcname=p.name)
raw=out.getvalue();print(json.dumps({'sha256':hashlib.sha256(raw).hexdigest(),'archive_base64':base64.b64encode(raw).decode()}))
'''
remote=remote.replace('PAYLOAD_SHA',repr(hashlib.sha256(payload).hexdigest())).replace('PAYLOAD',repr(base64.b64encode(payload).decode()))
(work/'remote.original.py').write_text(remote,encoding='utf-8')
command='sudo -n python3 -'
r=subprocess.run(['ssh','-i',r'C:\Users\SHENGJIAHAO\.ssh\gpt-deploy-release.pem','-o','BatchMode=yes','-o','StrictHostKeyChecking=yes','-o','ConnectTimeout=12','-o','ServerAliveInterval=15','-o','ServerAliveCountMax=12','ubuntu@43.172.70.182',command],input=remote,capture_output=True,text=True,timeout=600)
(work/'transport.stdout.original.log').write_text(r.stdout,encoding='utf-8');(work/'transport.stderr.original.log').write_text(r.stderr,encoding='utf-8')
assert r.returncode==0,(r.returncode,r.stderr[-2000:])
data=json.loads(r.stdout);raw=base64.b64decode(data['archive_base64']);assert hashlib.sha256(raw).hexdigest()==data['sha256'];(work/'public.tar.gz').write_bytes(raw)
public=work/'public';public.mkdir()
with tarfile.open(fileobj=io.BytesIO(raw),mode='r:gz') as archive:
    for item in archive.getmembers():
        assert item.isfile() and Path(item.name).name==item.name
        (public/item.name).write_bytes(archive.extractfile(item).read())
assert all(hashlib.sha256((repo/name).read_bytes()).hexdigest()==digest for name,digest in pins.items())
print((public/'terminal.original.json').read_text('utf-8'))
for name in ['container.original.log','import.stderr.original.log','test.stderr.original.log','case-results.json']:
    if (public/name).exists():print(name,(public/name).read_text('utf-8')[-5000:])
