import fcntl,hashlib,json,os,subprocess,time,urllib.request
from pathlib import Path
B=Path('/home/ubuntu/pr13-acceptance-20261009');E=B/'evidence/release-current-RAM-build-r2-20261014';R=Path('/opt/fantasycard-github');A=Path('/opt/fantasycard-app')
G_RECEIPT={'ok': True, 'revision': 'r1', 'local_directory': 'G:\\PR13Evidence\\Current-release-protected-candidate-r1', 'local_archive': 'G:\\Program Files\\GodotFiles\\godot_FanstaryCard\\outputs\\pr13-tencent-20261009\\Current-release-protected-candidate-r1-complete-original-G-backup\\complete-originals.tar.gz', 'production_database_and_private_protection_originals_included': True, 'streamed_without_cloud_archive': True, 'archive_bytes': 9404635, 'archive_sha256': '5b37690fd48461d1ba78a9c9ce783504327b86de400c75fb409280f30b20a09d', 'manifest_sha256': '5c8c62465945634298207b8d9f64415adadc30099a70bff1432d8d2620feead8', 'original_members': 401, 'all_original_members_SHA_verified': True, 'archive_gzip_CRC_verified': True, 'original_native_terminal_confirmed': True, 'no_owned_live_or_retained_containers': True, 'native_reexecuted_by_backup': False, 'cloud_originals_not_cleaned_by_backup': True, 'local_operations': 'byte SHA CRC and original JSON metadata only', 'MAIN_accepted': False}
def run(args,check=True,timeout=45):return subprocess.run(args,capture_output=True,check=check,timeout=timeout)
def docker(*args,**kw):return run(['docker',*args],**kw)
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def write(p,v):assert not p.exists();p.write_bytes((json.dumps(v,indent=2)+'\n').encode())
QUERY="BEGIN READ ONLY; SET LOCAL statement_timeout='10s'; SELECT json_build_object('players',(SELECT count(*) FROM players),'wallets',(SELECT count(*) FROM player_wallets),'gold_total',(SELECT coalesce(sum(gold),0) FROM player_wallets),'equipment',(SELECT count(*) FROM equipments),'ledger',(SELECT count(*) FROM economy_ledger),'settlements',(SELECT count(*) FROM match_settlements),'pending_holds',(SELECT count(*) FROM settlement_asset_holds WHERE state='Pending'),'active_non_bot_members',(SELECT count(*) FROM match_players p JOIN matches m ON m.match_id=p.match_id WHERE NOT p.is_bot AND p.state IN ('Assigned','Ready','Active') AND m.status IN ('Starting','Running'))); ROLLBACK;"
def assets():
 raw=docker('exec','fantasycard-cloud-postgres-1','psql','-X','-U','fantasycard','-d','fantasycard','-At','-v','ON_ERROR_STOP=1','-c',QUERY).stdout.decode()
 return next(json.loads(l) for l in raw.splitlines() if l.startswith('{'))
def healthy():
 try:
  with urllib.request.urlopen('http://127.0.0.1:8080/health/ready',timeout=10) as r:
   if r.status!=200:return False
  q=run(['curl','--fail','--silent','--show-error','--max-time','10','--resolve','www.relicbound.cn:443:127.0.0.1','https://www.relicbound.cn/health/ready'],False)
  if q.returncode!=0 or q.stdout.strip()!=b'Healthy':return False
  for path in ['/admin','/api/admin/client-settings']:
   q=run(['curl','--silent','--max-time','10','--resolve','www.relicbound.cn:443:127.0.0.1','--output','/dev/null','--write-out','%{http_code}','https://www.relicbound.cn'+path],False)
   if q.returncode!=0 or q.stdout!=b'404':return False
  return True
 except Exception:return False
def replace(p,text):
 q=p.with_name(p.name+'.current-runtime-r1.tmp');assert not q.exists();q.write_text(text);q.chmod(0o600);q.replace(p)
lock=Path('/tmp/fantasycard-update.lock').open('r+b');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
with (B/'evidence/shared-resource-coordination.lock').open('a') as coordination:
 fcntl.flock(coordination,fcntl.LOCK_EX)
 assert not (E/'activation.original.json').exists(),'Inspect existing outcome; never repeat unknown activation'
 build=json.loads((E/'runtime-image-build.original.json').read_bytes());probe=json.loads((E/'restored-live-backup-probe.original.json').read_bytes())
 assert build['ok'] and probe['ok'] and probe['owned_probe_containers_removed'] and probe['private_probe_environment_removed']
 assert G_RECEIPT['ok'] and G_RECEIPT['all_original_members_SHA_verified'] and G_RECEIPT['archive_gzip_CRC_verified'] and G_RECEIPT['production_database_and_private_protection_originals_included']
 assert sha(E/'candidate-complete-original-manifest.original.json')==G_RECEIPT['manifest_sha256']
 old=json.loads(docker('inspect','fantasycard-cloud-server-1').stdout)[0];assert old['Image']==probe['original_live_image_id']
 source=build['source_sha'];image=build['image_id']
 head=run(['git','-c','safe.directory='+str(R),'-C',str(R),'rev-parse','HEAD']).stdout.decode().strip()
 assert not run(['git','-c','safe.directory='+str(R),'-C',str(R),'diff','--name-only',source,head,'--','server/src','server/config','protocol']).stdout.strip()
 before=assets();assert before==probe['after_live_assets'] and before['active_non_bot_members']==before['pending_holds']==0
 backup=Path(probe['backup']['path']);assert backup.stat().st_size==probe['backup']['bytes'] and sha(backup)==probe['backup']['sha256']
 env=dict(v.split('=',1) for v in old['Config']['Env']);pg_id=json.loads(docker('inspect','fantasycard-cloud-postgres-1').stdout)[0]['Id']
 private_override=B/'secrets/current-runtime-activation-r1.override.json';assert not private_override.exists()
 def override(which):
  value={'services':{'server':{'image':which,'environment':{k:v.replace('$','$$') for k,v in env.items()}}}}
  replace(private_override,json.dumps(value))
 def compose(*args):return docker('compose','-f',str(R/'server/compose.cloud.yaml'),'-f',str(private_override),'--env-file',str(R/'server/.env'),*args,timeout=180)
 override(image)
 resolved=json.loads(compose('config','--format','json').stdout);configured=resolved['services']['server']['environment']
 assert all(str(configured.get(k,''))==v for k,v in env.items()),'Preserve exact production environment and temporary test limits'
 rollback_tag='fantasycard-pr13-rollback:before-current-d280-'+old['Id'][:10];docker('tag',old['Image'],rollback_tag)
 old_markers={name:(A/name).read_text() if (A/name).exists() else None for name in ['deployed-runtime-commit','deployed-git-commit']}
 write(E/'activation-intent.original.json',{'old_image_id':old['Image'],'new_image_id':image,'source_sha':source,'current_git_sha':head,'old_container_id':old['Id'],'rollback_tag':rollback_tag,
    'old_environment_sha256':hashlib.sha256(json.dumps(env,sort_keys=True).encode()).hexdigest(),'private_override_sha256':sha(private_override),'backup':probe['backup'],'G_candidate_archive_sha256':G_RECEIPT['archive_sha256'],'before_assets':before,'automatic_activation_retry':False})
 changed=False;result={'ok':False,'source_sha':source,'current_git_sha':head,'old_image_id':old['Image'],'new_image_id':image,'rollback_image_tag':rollback_tag,'before_assets':before,'MAIN_accepted':False}
 try:
  changed=True;compose('up','-d','--no-deps','--no-build','--pull','never','server')
  deadline=time.monotonic()+120
  while not healthy():assert time.monotonic()<deadline,'Current runtime readiness/admin perimeter';time.sleep(2)
  c=json.loads(docker('inspect','fantasycard-cloud-server-1').stdout)[0];assert c['Image']==image and c['Config']['Labels']['org.opencontainers.image.revision']==source
  actual_env=dict(v.split('=',1) for v in c['Config']['Env']);assert actual_env==env
  assert json.loads(docker('inspect','fantasycard-cloud-postgres-1').stdout)[0]['Id']==pg_id
  after=assets();assert after==before
  replace(A/'deployed-runtime-commit',source+'\n');replace(A/'deployed-git-commit',head+'\n')
  result.update(ok=True,actual_new_container_id=c['Id'],actual_runtime_revision=source,current_release_product_source_equal=True,
    environment_exactly_preserved=True,temporary_test_limits_preserved=True,postgres_container_unchanged=True,after_assets=after,asset_invariants_preserved=True,
    internal_health_status=200,strict_origin_HTTPS_health_status=200,public_admin_perimeter_status=404,production_activated=True,rollback_performed=False)
 except Exception as error:
  result.update(error=type(error).__name__,detail=str(error),original_failure_retained=True)
  if changed:
   override(old['Image']);compose('up','-d','--no-deps','--no-build','--pull','never','server');deadline=time.monotonic()+120
   while not healthy():assert time.monotonic()<deadline,'Original image rollback readiness';time.sleep(2)
   c=json.loads(docker('inspect','fantasycard-cloud-server-1').stdout)[0];assert c['Image']==old['Image']
   for name,text in old_markers.items():
    if text is not None:replace(A/name,text)
   result.update(rollback_performed=True,rollback_healthy=True,production_activated=False)
 finally:
  if result['ok'] or result.get('rollback_healthy'):private_override.unlink()
  result['private_activation_override_removed']=not private_override.exists();write(E/'activation.original.json',result)
 print(json.dumps(result));assert result['ok'],'Original failed activation retained'
