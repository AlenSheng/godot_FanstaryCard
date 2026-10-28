import pathlib,subprocess,json,hashlib,tarfile,os,time,traceback,urllib.request,shutil
O=pathlib.Path('/home/ubuntu/pr13-normal-mixed-current-20261025-r20');A=pathlib.Path('/var/tmp/fc-current-mixed-full-evidence-20261025-r20');tag='pr13-normal-mixed-r20';owner='01a152f7-f2a2-7b12-a4c5-a22b38ee9cd3';os.nice(19);A.mkdir(mode=0o700);stopped=[]
def inspect(cid):return json.loads(subprocess.check_output(['docker','inspect',cid]))[0]
def owned(x):assert x['Config']['Labels']['pr13.owner']==owner and x['Config']['Labels']['pr13.round']=='current-normal-mixed-r20' and x['Name'].startswith('/'+tag+'-')
try:
 native=inspect(tag+'-normal-mixed3');owned(native);assert not native['State']['Running'];J=next((O/'results/normal-mixed3/coordinator').glob('*'));report=json.loads((J/'report.json').read_text());assert report['clients']==10 and type(report['outcome']['passed']) is bool
 M=O/'study-container-metadata';M.mkdir(mode=0o700)
 ids=subprocess.check_output(['docker','ps','-aq','--filter','label=pr13.round=current-normal-mixed-r20']).decode().splitlines()
 for cid in ids:
  x=inspect(cid);owned(x);(M/(x['Id']+'.inspect.private.original.json')).write_text(json.dumps(x,indent=2)+chr(10));r=subprocess.run(['docker','logs',cid],capture_output=True);(M/(x['Id']+'.stdout.private.original.log')).write_bytes(r.stdout);(M/(x['Id']+'.stderr.private.original.log')).write_bytes(r.stderr)
  if x['State']['Running']:assert x['Name'] in ['/'+tag+'-'+kind for kind in ['app','otel','prom','pg']]
 for kind in ['app','otel','prom']:
  x=inspect(tag+'-'+kind);owned(x)
  if x['State']['Running']:r=subprocess.run(['docker','stop','--time','25',x['Id']],capture_output=True,timeout=40);assert r.returncode==0;stopped.append(x['Name'])
 pg=inspect(tag+'-pg');owned(pg);assert pg['State']['Running'];B=O/'study-owned-DB-export';B.mkdir(mode=0o700);db='ready_stop_normal_mixed_r20';p=B/(db+'.dump')
 with p.open('xb') as out,(B/'pg_dump.stderr.original.log').open('xb') as err:r=subprocess.run(['docker','exec',pg['Id'],'pg_dump','-U','pr13_rebuild','-d',db,'--format=custom','--no-owner','--no-acl'],stdout=out,stderr=err,timeout=120)
 assert r.returncode==0;data=p.read_bytes();assert data[:5]==b'PGDMP';audit=subprocess.check_output(['docker','exec',pg['Id'],'psql','-At','-U','pr13_rebuild','-d',db,'-c',"SELECT 'matches',count(*) FROM matches UNION ALL SELECT 'settlements',count(*) FROM match_settlements UNION ALL SELECT 'pending_holds',count(*) FROM settlement_asset_holds WHERE state='Pending'"]).decode();export={'ok':True,'database':db,'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest(),'audit':audit,'formal_PG_not_read_or_dumped':True};export['membership']=json.loads(subprocess.check_output(['docker','exec',pg['Id'],'psql','-At','-U','pr13_rebuild','-d',db,'-c',"SELECT json_build_object('settlements',(SELECT count(*) FROM match_settlements),'pending_holds',(SELECT count(*) FROM settlement_asset_holds WHERE state='Pending'),'settled_user_ids',(SELECT coalesce(json_agg(DISTINCT player_id),'[]'::json) FROM match_settlements))"]));(B/'terminal.original.json').write_text(json.dumps(export,indent=2)+chr(10));r=subprocess.run(['docker','stop','--time','25',pg['Id']],capture_output=True,timeout=40);assert r.returncode==0;stopped.append(pg['Name'])
 assert not subprocess.check_output(['docker','ps','-q','--filter','label=pr13.round=current-normal-mixed-r20']).strip();P=pathlib.Path('/home/ubuntu/pr13-resource100-admission-20261025-r18/project');assert subprocess.check_output(['git','-C',str(P),'rev-parse','HEAD']).decode().strip()=='2eecaf49c1b081bcba5fb5d95d2c620df7e1f9d9';(M/'actual-source-delta.private.original.patch').write_bytes(subprocess.check_output(['git','-C',str(P),'diff','--binary','HEAD']));(M/'actual-source-status.private.original.paths0').write_bytes(subprocess.check_output(['git','-C',str(P),'status','--porcelain=v1','-z','--untracked-files=all']))
 with urllib.request.urlopen('http://127.0.0.1:8080/health/ready',timeout=5) as r:assert r.status==200;r.read(4096)
 # Preserve authored/generated source-side inputs outside the immutable Git
 # blobs before disposing of the temporary checkout; import caches regenerate.
 tracked=set(subprocess.check_output(['git','-C',str(P),'ls-files','-z']).decode().split(chr(0)));untracked=set(subprocess.check_output(['git','-C',str(P),'ls-files','--others','--exclude-standard','-z']).decode().split(chr(0)))-{''}
 for root,dirs,names in os.walk(P/'client',followlinks=False):
  dirs[:]=[n for n in dirs if n not in ('.git','.godot')]
  for name in names:
   f=pathlib.Path(root,name);assert not f.is_symlink();rel=f.relative_to(P).as_posix()
   if rel not in tracked:untracked.add(rel)
 for rel in sorted(untracked):
  f=P/rel;assert f.resolve().is_relative_to(P) and f.is_file() and not f.is_symlink();dest=M/'source-nonGit-inputs'/rel;dest.parent.mkdir(parents=True,exist_ok=True);assert not dest.exists();shutil.copyfile(f,dest)
 files=[];excluded={'project','pg-data','prom-data','prom-data-r6','engine-cache','editor-config'}
 for root,dirs,names in os.walk(O,followlinks=False):
  dirs[:]=[n for n in dirs if n not in excluded and not pathlib.Path(root,n).is_symlink()]
  for name in names:
   f=pathlib.Path(root,name)
   if name.startswith('study-backup-controller') or not f.is_file() or f.is_symlink():continue
   b=f.read_bytes();files.append({'path':f.relative_to(O).as_posix(),'bytes':len(b),'sha256':hashlib.sha256(b).hexdigest()})
 raw=(json.dumps({'source_root':str(O),'files':files,'database_export':export,'owned_services_stopped_for_stable_snapshot':stopped,'formal_ready_HTTP':200},indent=2)+chr(10)).encode();(A/'manifest.original.json').write_bytes(raw);archive=A/'evidence.original.tar.xz'
 with tarfile.open(archive,'w:xz',preset=3) as t:
  t.add(A/'manifest.original.json',arcname='_backup_manifest.original.json',recursive=False)
  for row in files:t.add(O/row['path'],arcname=row['path'],recursive=False)
 h=hashlib.sha256()
 with archive.open('rb') as f:
  while b:=f.read(1024**2):h.update(b)
 result={'ok':True,'archive':str(archive),'bytes':archive.stat().st_size,'sha256':h.hexdigest(),'manifest_SHA256':hashlib.sha256(raw).hexdigest(),'members':len(files),'logical_source_bytes':sum(r['bytes'] for r in files),'actual_cloud_native_clients':10,'joint_capacity_passed':False,'database_export':export,'formal_ready_HTTP':200,'source_and_databases_retained_until_G_backup_verification':True,'owned_services_stopped':stopped}
except BaseException as e:result={'ok':False,'error_type':type(e).__name__,'error':str(e),'stopped':stopped};(A/'error.original.log').write_text(traceback.format_exc())
(A/'terminal.original.json').write_text(json.dumps(result,indent=2)+chr(10))
