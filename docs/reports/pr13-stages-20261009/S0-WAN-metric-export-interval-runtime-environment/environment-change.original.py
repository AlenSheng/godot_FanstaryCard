import fcntl,hashlib,json,subprocess,time,urllib.request,urllib.parse
from pathlib import Path
B=Path('/home/ubuntu/pr13-acceptance-20261009');E=B/'evidence/WAN-metric-interval-current-backup-r1-20261014';R=Path('/opt/fantasycard-github')
IMAGE='sha256:7c13e8ebbfec9a554dfd20a8d78ee223e15a4286c4875606ae82e7d46d226ef2'
QUERY="BEGIN READ ONLY; SET LOCAL statement_timeout='10s'; SELECT json_build_object('players',(SELECT count(*) FROM players),'wallets',(SELECT count(*) FROM player_wallets),'gold_total',(SELECT coalesce(sum(gold),0) FROM player_wallets),'equipment',(SELECT count(*) FROM equipments),'ledger',(SELECT count(*) FROM economy_ledger),'settlements',(SELECT count(*) FROM match_settlements),'pending_holds',(SELECT count(*) FROM settlement_asset_holds WHERE state='Pending'),'active_non_bot_members',(SELECT count(*) FROM match_players p JOIN matches m ON m.match_id=p.match_id WHERE NOT p.is_bot AND p.state IN ('Assigned','Ready','Active') AND m.status IN ('Starting','Running'))); ROLLBACK;"
def run(a,timeout=45):return subprocess.run(a,capture_output=True,check=True,timeout=timeout)
def inspect(name):return json.loads(run(['docker','inspect',name]).stdout)[0]
def assets():
 out=run(['docker','exec','fantasycard-cloud-postgres-1','psql','-X','-U','fantasycard','-d','fantasycard','-At','-v','ON_ERROR_STOP=1','-c',QUERY]).stdout.decode()
 return next(json.loads(l) for l in out.splitlines() if l.startswith('{'))
def health():
 try:
  with urllib.request.urlopen('http://127.0.0.1:8080/health/ready',timeout=10) as h:return h.status==200
 except OSError:return False
def private(p,data):assert not p.exists();p.write_bytes(data);p.chmod(0o600)
lock=Path('/tmp/fantasycard-update.lock').open('r+b');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
with (B/'evidence/shared-resource-coordination.lock').open('a') as coordination:
 fcntl.flock(coordination,fcntl.LOCK_EX);assert not (E/'telemetry-env-change.original.json').exists()
 proof=json.loads((E/'backup.original.json').read_bytes());backup=Path(proof['fresh_private_backup']['path']);assert backup.stat().st_size==proof['fresh_private_backup']['bytes'] and hashlib.sha256(backup.read_bytes()).hexdigest()==proof['fresh_private_backup']['sha256']
 # The caller freezes and verifies this exact private original on G before dispatch.
 assert proof['fresh_private_backup']['sha256']=='7a551312657b366d1f8c16300d52f6b6e5524830a7e938ee30d172165839dc6f'
 listing=subprocess.run(['docker','exec','-i','fantasycard-cloud-postgres-1','pg_restore','--list'],input=backup.read_bytes(),capture_output=True,check=True,timeout=45);assert listing.stdout
 old=inspect('fantasycard-cloud-server-1');assert old['Image']==IMAGE and old['Id']==proof['actual_original_container_id'];env=dict(v.split('=',1) for v in old['Config']['Env']);assert 'OTEL_METRIC_EXPORT_INTERVAL' not in env
 assert hashlib.sha256(json.dumps(env,sort_keys=True).encode()).hexdigest()==proof['original_environment_SHA256'];before=assets();assert before==proof['original_assets'] and before['active_non_bot_members']==before['pending_holds']==0
 with urllib.request.urlopen('http://127.0.0.1:9090/api/v1/query?'+urllib.parse.urlencode({'query':'fantasycard_realtime_connections_active{job="fantasycard",instance="otel-collector:9464"}'}),timeout=10) as h:connections=json.load(h)['data']['result']
 assert len(connections)==1 and float(connections[0]['value'][1])==0
 pg_id=inspect('fantasycard-cloud-postgres-1')['Id'];override=B/'secrets/WAN-metric-interval-r1.override.json';old_private=B/'secrets/WAN-metric-before-environment-r1.original.json';private(old_private,json.dumps(env).encode())
 def set_override(values):
  value={'services':{'server':{'image':IMAGE,'environment':{k:v.replace('$','$$') for k,v in values.items()}}}}
  data=json.dumps(value).encode()
  if override.exists():override.write_bytes(data);override.chmod(0o600)
  else:private(override,data)
 def compose(*a):return run(['docker','compose','-f',str(R/'server/compose.cloud.yaml'),'-f',str(override),'--env-file',str(R/'server/.env'),*a],timeout=180)
 expected=dict(env,OTEL_METRIC_EXPORT_INTERVAL='1000');set_override(expected);configured=json.loads(compose('config','--format','json').stdout)['services']['server']['environment'];assert all(str(configured.get(k,''))==v for k,v in expected.items())
 intent={'only_changed_environment_key':'OTEL_METRIC_EXPORT_INTERVAL','new_value':'1000','old_value_absent':True,'actual_image':IMAGE,'old_container_id':old['Id'],'before_assets':before,'fresh_private_backup_SHA256':proof['fresh_private_backup']['sha256'],'automatic_mutation_retry':False};p=E/'telemetry-env-change-intent.original.json';assert not p.exists();p.write_text(json.dumps(intent,indent=2)+'\n');changed=False;result={'ok':False,'MAIN_accepted':False}
 try:
  changed=True;compose('up','-d','--no-deps','--no-build','--pull','never','server');deadline=time.monotonic()+120
  while not health():assert time.monotonic()<deadline;time.sleep(2)
  c=inspect('fantasycard-cloud-server-1');actual=dict(v.split('=',1) for v in c['Config']['Env']);assert c['Image']==IMAGE and actual==expected and inspect('fantasycard-cloud-postgres-1')['Id']==pg_id;after=assets();assert after==before
  run(['curl','--fail','--silent','--show-error','--max-time','10','--resolve','www.relicbound.cn:443:127.0.0.1','https://www.relicbound.cn/health/ready'])
  result.update(ok=True,actual_new_container_id=c['Id'],actual_image_id=IMAGE,only_changed_environment_key='OTEL_METRIC_EXPORT_INTERVAL',actual_export_interval_ms=1000,all_other_environment_and_temporary_limits_preserved=True,postgres_container_unchanged=True,before_assets=before,after_assets=after,strict_origin_HTTPS_health_status=200,old_environment_preserved_privately_for_exact_restore=True,temporary_test_setting=True,rollback_performed=False)
 except Exception as error:
  result.update(original_failure_retained=True,error=type(error).__name__,detail=str(error))
  if changed:
   set_override(env);compose('up','-d','--no-deps','--no-build','--pull','never','server');deadline=time.monotonic()+120
   while not health():assert time.monotonic()<deadline;time.sleep(2)
   assert dict(v.split('=',1) for v in inspect('fantasycard-cloud-server-1')['Config']['Env'])==env;result.update(rollback_performed=True,rollback_healthy=True)
 finally:
  if result['ok'] or result.get('rollback_healthy'):override.unlink()
  result['private_override_removed']=not override.exists();p=E/'telemetry-env-change.original.json';assert not p.exists();p.write_text(json.dumps(result,indent=2)+'\n')
 print(json.dumps(result));assert result['ok']
