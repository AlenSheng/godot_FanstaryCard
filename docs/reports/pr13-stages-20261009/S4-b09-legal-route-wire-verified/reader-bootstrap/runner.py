import hashlib,json,os,subprocess,time,urllib.request
from pathlib import Path
B=Path('/home/ubuntu/pr13-acceptance-20261009');GIT=Path('/opt/fantasycard-github');A='b09-legal-route-receive-r4-20261011';OWNER='pr13-cap-'+A;E=B/'evidence'/A;W=B/'work'/A;S=W/'source';R=Path('/dev/shm/pr13-'+A);OLD=B/'work/b09-legal-route-r3-20261011/source';NATIVE=Path('/dev/shm/pr13-b09-legal-route-r3-20261011');RELEASE='6e65d45b1f7b823853f72963d5ff1436fc46fc4e';NATIVE_SHA='5b66fc0cb601a7bf7a3b2439daea1a3a9db0f438';IMAGE='sha256:180f524270f6ac28d2fe0ff29707fb392387d7b766f731e41fda1e45e8230520'
def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for d in iter(lambda:f.read(65536),b''):h.update(d)
 return h.hexdigest()
def command(args):return subprocess.check_output(args,timeout=30)
def docker(*a):return command(['sudo','-n','docker',*map(str,a)])
def save(p,v):
 assert not p.exists();p.write_text(json.dumps(v,indent=2)+'\n')
def owned(cid):
 v=json.loads(docker('inspect',cid))[0];assert v['Id']==cid and v['Config']['Labels']['codex.owner']==OWNER;return v
state=dict(x.split('=',1) for x in command(['systemctl','show',OWNER,'--property=MainPID,LoadState,ActiveState']).decode().splitlines());assert state['LoadState']=='loaded' and int(state['MainPID'])==os.getpid() and state['ActiveState']=='active'
assert command(['git','-C',str(GIT),'rev-parse','HEAD']).decode().strip()==RELEASE
assert not command(['git','-C',str(GIT),'diff','--name-only',NATIVE_SHA,RELEASE,'--','server','protocol']).strip()
original=json.loads((B/'evidence/b09-legal-route-r3-20261011/run-result.json').read_bytes());assert original['source_and_packages_unchanged'] is True and original['owned_container_removed'] is True
phase=json.loads((NATIVE/'phase-progress.json').read_bytes());assert all(x['exit_code']==0 for x in phase) and len(phase)==9
assert not E.exists() and not W.exists() and not R.exists();E.mkdir();S.mkdir(parents=True);R.mkdir(mode=0o777)
files={}
for p in sorted((OLD/'client').rglob('*')):
 assert not p.is_symlink()
 if p.is_file():
  name=p.relative_to(OLD).as_posix();q=S/name;q.parent.mkdir(parents=True,exist_ok=True);os.link(p,q);files[name]=sha(p)
changed='client/tests/test_monster_pool_legal_route_vectors.gd';q=S/changed;q.unlink();body=command(['git','-C',str(GIT),'show',RELEASE+':'+changed]);q.write_bytes(body);files[changed]=sha(q)
native_files={p.name:sha(p) for p in NATIVE.iterdir() if p.is_file()};save(E/'inputs.json',{'reader_source_sha':RELEASE,'native_original_source_sha':NATIVE_SHA,'client_files':files,'native_original_files':native_files,'numeric_or_NET_executed':False,'only_current_client_fixture_changed':True,'old_native_source_not_relabelled_current':True});save(E/'runner.original-context.json',{'unit':OWNER,'MainPID':os.getpid(),'at':time.time(),'native_Godot_receive_only':True})
cid=None;result={'ok':False,'attempt':A,'reader_source_sha':RELEASE,'native_original_source_sha':NATIVE_SHA,'NET_or_numeric_generation_executed':False,'MAIN_accepted':False,'LIVE_accepted':False}
try:
 mem=next(int(x.split()[1])*1024 for x in Path('/proc/meminfo').read_text().splitlines() if x.startswith('MemAvailable:'));assert mem>=500000000+768*1024**2+32*1024**2
 cid=docker('create','--name',OWNER,'--label','codex.owner='+OWNER,'--network','none','--memory','768m','--memory-swap','768m','--cpus','1','--read-only','--tmpfs','/tmp:rw,size=134217728','--user','1000:1000','-e','HOME=/tmp/test-home','-e','FANTASYCARD_SERVER_URL=http://127.0.0.1:1','-e','PR13_LEGAL_ROUTE_GODOT_MODE=receive','-e','PR13_LEGAL_ROUTE_SOURCE='+NATIVE_SHA,'-e','PR13_LEGAL_ROUTE_DIRECTORY=/native-originals','-e','PR13_LEGAL_ROUTE_GODOT_RESULT=/output/native-result.json','-v',str(S/'client')+':/client:ro','-v',str(NATIVE)+':/native-originals:ro','-v',str(R)+':/output',IMAGE,'godot','--headless','--audio-driver','Dummy','--path','/client','--script','res://tests/run_monster_pool_legal_route_vectors.gd').decode().strip();owned(cid);result['container_id']=cid
 with (R/'engine.log').open('xb') as log:p=subprocess.run(['sudo','-n','docker','start','-a',cid],stdout=log,stderr=subprocess.STDOUT,timeout=180)
 info=owned(cid);text=(R/'engine.log').read_text(errors='replace');v=json.loads((R/'native-result.json').read_bytes()) if (R/'native-result.json').exists() else {};clean=not any(x.lower() in text.lower() for x in ('SCRIPT ERROR','Parse Error','Failed to load script','ObjectDB instances were leaked','resources still in use'))
 result.update(exit_code=p.returncode,native=v,strict_engine_log_clean=clean,oom_killed=info['State']['OOMKilled']);result['ok']=p.returncode==0 and v.get('ok') is True and clean and not result['oom_killed'] and v['native_rows_received']==72 and v['original_native_frames_received']==189 and v['original_replay_frames_received']==45
except Exception as x:result.update(error=type(x).__name__,detail=str(x),all_failed_originals_retained=True)
finally:
 if cid:
  info=owned(cid)
  if info['State']['Running']:docker('stop','--time','10',cid)
  owned(cid);docker('rm',cid);result['owned_container_removed']=True
 result['current_client_inputs_unchanged']=all(sha(S/n)==h for n,h in files.items());result['old_native_originals_unchanged']=all(sha(NATIVE/n)==h for n,h in native_files.items());result['ok']=result['ok'] and result['current_client_inputs_unchanged'] and result['old_native_originals_unchanged']
 save(E/'run-result.json',result)
print(json.dumps(result));raise SystemExit(0 if result['ok'] else 1)
