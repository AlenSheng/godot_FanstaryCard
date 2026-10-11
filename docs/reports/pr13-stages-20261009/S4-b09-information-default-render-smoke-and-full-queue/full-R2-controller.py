import ast,base64,gzip,hashlib,importlib.util,json,os,tarfile,time
from pathlib import Path,PurePosixPath
B=Path(__file__).parent;OUT=B/'information-default-render-full972-r2';RUNDIR=B/'b09-information-default-render-full972-r2-runners';plan=json.loads((RUNDIR/'plan.json').read_bytes());assert not OUT.exists();OUT.mkdir();spec=importlib.util.spec_from_file_location('controlled_full_render_original_stream',B/'b08_lifecycle_r4_G_transport_gc_r2.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);m.OUT=OUT;base=m.load('backup_failed_tuning_equivalence_r1_to_G.py')
until=time.monotonic()+14400;smoke=B/'information-smoke-R5-passed-originals-on-G/local-backup-receipt.json'
while not smoke.exists():
 assert time.monotonic()<until;print(json.dumps({'waiting_for_R4_complete_G_receipt':True,'native_dispatched':False}),flush=True);time.sleep(15)
g=json.loads(smoke.read_bytes());assert g['ok'] and g['passed_development_smoke'] and g['all_original_members_SHA_verified'] and g['archive_gzip_CRC_verified'];assert m.sha(Path(g['local_archive']))==g['sha256']
def remote(code,target=None):
 c=base.connect()
 try:
  ch=c.get_transport().open_session(timeout=45);ch.exec_command('python3 -');ch.sendall(code.encode());ch.shutdown_write();return m.receive(ch,target)
 finally:c.close()
def json_remote(code):
 raw,_,err=remote(code);assert not err;return json.loads(raw)
def readonly(code):
 import paramiko
 for attempt in range(6):
  try:return json_remote(code)
  except (paramiko.SSHException,EOFError,OSError,TimeoutError):
   if attempt==5:raise
   time.sleep(5)
setup=r'''
import fcntl,json,subprocess
from pathlib import Path
B=Path('/home/ubuntu/pr13-acceptance-20261009');P=B/'evidence/information-default-render-full972-r2';H=B/'evidence/pool-render-segments-r3/scheduling-hold.json';E=B/'evidence/b09-information-default-render-smoke-r5-20261011'
with (B/'evidence/shared-resource-coordination.lock').open('a') as lock:
 fcntl.flock(lock.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB);hold=json.loads(H.read_bytes());assert hold['active'] and hold['owner']=='pr13-cap-b09-information-default-render-smoke-r5-20261011';state=dict(x.split('=',1) for x in subprocess.check_output(['systemctl','show',hold['owner'],'--property=MainPID,ActiveState,ExecMainStatus'],text=True).splitlines());assert state['MainPID']=='0' and state['ActiveState']=='inactive' and state['ExecMainStatus']=='0';native=json.loads((E/'run-result.json').read_bytes());assert native['ok'] and native['independent_control_validation_passed'];assert not P.exists();P.mkdir();(P/'previous-smoke-hold.original.json').write_bytes(H.read_bytes());(P/'smoke-G-original.json').write_text(json.dumps(G,indent=2)+'\n');(P/'plan.json').write_text(json.dumps(PLAN,indent=2)+'\n');hold.update(owner='pr13-information-default-render-full972-r2',reason='Both locales of the frozen 972 observation information/default matrix; old pool queue preserved');temporary=H.with_name('information-full972-hold.tmp');assert not temporary.exists();temporary.write_text(json.dumps(hold)+'\n');temporary.replace(H);print(json.dumps({'ok':True,'no_native_started_by_setup':True}))
'''
assert json_remote('G='+repr(g)+'\nPLAN='+repr(plan)+'\n'+setup)['ok']
for unit in plan['units']:
 A=unit['attempt'];LOCAL=OUT/unit['locale'];LOCAL.mkdir();runner=(RUNDIR/unit['runner']).read_bytes();assert hashlib.sha256(runner).hexdigest()==unit['runner_sha256'];ast.parse(runner)
 dispatch=r'''
import base64,hashlib,json,subprocess
from pathlib import Path
B=Path('/home/ubuntu/pr13-acceptance-20261009');E=B/'evidence'/A;W=B/'work'/A;S=B/'evidence/b09-information-default-render-smoke-r5-20261011';assert not E.exists() and not W.exists();assert json.loads((B/'evidence/pool-render-segments-r3/scheduling-hold.json').read_bytes())['owner']=='pr13-information-default-render-full972-r2';E.mkdir();W.mkdir();raw=base64.b64decode(DATA,validate=True);assert hashlib.sha256(raw).hexdigest()==UNIT['runner_sha256'];(E/'runner.py').write_bytes(raw)
for name in ('validator.py','corpus.json'):(E/name).write_bytes((S/name).read_bytes())
meta=json.loads((S/'inputs.json').read_bytes());meta.update(development_smoke=False,locale=UNIT['locale'],runner_sha256=UNIT['runner_sha256'],shared_client_source_root='/home/ubuntu/pr13-acceptance-20261009/work/b09-information-default-render-smoke-r5-20261011/source');(E/'inputs.json').write_text(json.dumps(meta,indent=2)+'\n');owner='pr13-cap-'+A;body='[Unit]\nDescription=PR13 frozen information/default full locale\n[Service]\nType=exec\nUser=root\nExecStart=/usr/bin/python3 '+str(E/'runner.py')+'\nRuntimeMaxSec=6000\nRestart=no\n';path=Path('/etc/systemd/system')/(owner+'.service');assert not path.exists();(E/'dispatch-intent.json').write_text(json.dumps({'owner':owner,'runner_sha256':UNIT['runner_sha256'],'no_automatic_retry':True,'expected_rows':486,'expected_PNGs':27})+'\n');p=subprocess.run(['sudo','-n','tee',str(path)],input=body.encode(),capture_output=True,timeout=35);assert p.returncode==0 and path.read_text()==body;p=subprocess.run(['sudo','-n','systemctl','daemon-reload'],capture_output=True,timeout=35);assert p.returncode==0;p=subprocess.run(['sudo','-n','systemctl','start','--no-block',owner],capture_output=True,text=True,timeout=35);result={'ok':p.returncode==0,'owner':owner,'no_completion_claimed':True};(E/'dispatch-result.json').write_text(json.dumps(result)+'\n');print(json.dumps(result));assert result['ok']
'''
 (LOCAL/'local-dispatch-intent.json').write_text(json.dumps({'unit':unit,'no_automatic_retry':True})+'\n',encoding='utf-8');v=json_remote('A='+repr(A)+'\nUNIT='+repr(unit)+'\nDATA='+repr(base64.b64encode(runner).decode())+'\n'+dispatch);(LOCAL/'cloud-dispatch-result.original.json').write_text(json.dumps(v)+'\n',encoding='utf-8');print(json.dumps(v),flush=True)
 status_code='A='+repr(A)+'\n'+r'''
import json,subprocess
from pathlib import Path
B=Path('/home/ubuntu/pr13-acceptance-20261009');E=B/'evidence'/A;R=Path('/dev/shm/pr13-'+A);p=E/'run-result.json';q=R/'checkpoint.json';print(json.dumps({'state':dict(x.split('=',1) for x in subprocess.check_output(['systemctl','show','pr13-cap-'+A,'--property=MainPID,ActiveState,ExecMainStatus'],text=True).splitlines()),'result':json.loads(p.read_bytes()) if p.exists() else None,'rows':json.loads(q.read_bytes())['rows'] if q.exists() else 0,'started':(E/'run-started.json').exists()}))
'''
 while True:
  v=readonly(status_code);(LOCAL/'last-observation.json').write_text(json.dumps(v,indent=2)+'\n',encoding='utf-8')
  if v['result'] is not None:break
  assert v['state']['ActiveState']=='active' and time.monotonic()<until,'Exact native terminal requires audit; never restart';print(json.dumps({'observing':unit['locale'],'rows':v['rows'],'required_rows':486}),flush=True);time.sleep(15)
 assert v['result']['ok'] and v['state']['MainPID']=='0' and v['state']['ActiveState']=='inactive' and v['state']['ExecMainStatus']=='0'
 collect=r'''
import gzip,hashlib,io,json,subprocess,sys,tarfile
from pathlib import Path
B=Path('/home/ubuntu/pr13-acceptance-20261009');E=B/'evidence'/A;RAM=Path('/dev/shm/pr13-'+A)
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def manifest():
 native=json.loads((E/'run-result.json').read_bytes());assert native['ok'] and native['rows']==486 and native['PNGs']==27 and native['source_and_corpus_unchanged'] and native['strict_engine_log_clean'];files=[]
 for root,prefix in ((E,'metadata'),(RAM,'outputs')):
  for p in sorted(root.rglob('*')):
   assert not p.is_symlink()
   if p.is_file():files.append({'source':str(p),'path':prefix+'/'+p.relative_to(root).as_posix(),'bytes':p.stat().st_size,'sha256':sha(p)})
 assert sum(x['bytes'] for x in files)<128*1024**2
 return {'unit':UNIT,'files':files,'shared_source_and_R4_driver_G_archive_sha256':SHARED_G,'MAIN_accepted':False}
'''
 prefix='A='+repr(A)+'\nUNIT='+repr(unit)+'\nSHARED_G='+repr(g['sha256'])+'\n';raw,_,err=remote(prefix+collect+'\nsys.stdout.write(json.dumps(manifest(),indent=2)+"\\n")\n');assert not err;manifest=json.loads(raw);(LOCAL/'delivery-manifest.json').write_bytes(raw);mh=hashlib.sha256(raw).hexdigest();archive=LOCAL/'delivery.private.tar.gz'
 stream=prefix+collect+'\nEXPECTED='+repr(mh)+'\n'+r'''
v=manifest();raw=(json.dumps(v,indent=2)+'\n').encode();assert hashlib.sha256(raw).hexdigest()==EXPECTED
class Sink:
 def __init__(self):self.n=0;self.h=hashlib.sha256()
 def write(self,b):n=sys.stdout.buffer.write(b);assert n==len(b);self.n+=n;self.h.update(b);return n
 def flush(self):sys.stdout.buffer.flush()
sink=Sink()
with gzip.GzipFile(fileobj=sink,mode='wb',compresslevel=1,mtime=0) as gz:
 with tarfile.open(fileobj=gz,mode='w|') as t:
  i=tarfile.TarInfo('manifest.json');i.size=len(raw);t.addfile(i,io.BytesIO(raw))
  for row in v['files']:
   p=Path(row['source']);assert sha(p)==row['sha256'];i=tarfile.TarInfo(row['path']);i.size=row['bytes'];i.mode=0o600
   with p.open('rb') as f:t.addfile(i,f)
sink.flush();assert manifest()==v;sys.stderr.write('ACK '+json.dumps({'bytes':sink.n,'sha256':sink.h.hexdigest(),'manifest_sha256':EXPECTED,'members':len(v['files'])})+'\n')
'''
 with archive.open('xb') as f:_,count,err=remote(stream,f);f.flush();os.fsync(f.fileno())
 assert len(err.splitlines())==1 and err.startswith(b'ACK ');ack=json.loads(err[4:]);assert ack['bytes']==count==archive.stat().st_size and ack['sha256']==m.sha(archive) and ack['manifest_sha256']==mh and ack['members']==len(manifest['files']);DEST=LOCAL/'verified';DEST.mkdir();expected={x['path']:x for x in manifest['files']};seen=set()
 with tarfile.open(archive,'r|gz') as t:
  for item in t:
   p=PurePosixPath(item.name);assert item.isfile() and not p.is_absolute() and '..' not in p.parts and '\\' not in item.name and item.name not in seen;seen.add(item.name);data=t.extractfile(item).read()
   if item.name=='manifest.json':assert data==raw;continue
   row=expected[item.name];assert len(data)==item.size==row['bytes'] and hashlib.sha256(data).hexdigest()==row['sha256'];p=DEST/item.name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(data)
 assert seen==set(expected)|{'manifest.json'}
 with gzip.open(archive,'rb') as f:
  for _ in iter(lambda:f.read(65536),b''):pass
 from tools.pr13_pool_render_evidence import png_validate
 images=list((DEST/'outputs').glob('*.png'));assert len(images)==27
 for p in images:png_validate(p)
 proof={'ok':True,'unit':unit,'local_directory':str(DEST),'local_archive':str(archive),'sha256':m.sha(archive),'bytes':archive.stat().st_size,'manifest_sha256':mh,'members_verified':len(expected),'archive_gzip_CRC_verified':True,'all_original_members_SHA_verified':True,'original_PNG_CRC_verified':27,'actual_rows':486,'visual_review_pending':True,'actual_PID1_terminal_proof_pending':True,'MAIN_accepted':False};(LOCAL/'local-backup-receipt.json').write_text(json.dumps(proof,indent=2)+'\n',encoding='utf-8');print(json.dumps({'locale_G_closed':unit['locale'],'rows':486,'PNGs':27,'MAIN_accepted':False}),flush=True)
(OUT/'complete.json').write_text(json.dumps({'ok':True,'locales':2,'rows':972,'PNGs':54,'visual_review_and_actual_PID1_proof_pending':True,'MAIN_accepted':False})+'\n',encoding='utf-8');print(json.dumps({'ok':True,'full_matrix_originals_G_closed':True,'rows':972,'PNGs':54,'MAIN_accepted':False}),flush=True)
