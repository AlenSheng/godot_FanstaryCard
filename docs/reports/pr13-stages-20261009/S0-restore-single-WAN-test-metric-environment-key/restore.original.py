import fcntl,json,subprocess,time,urllib.request,urllib.parse
from pathlib import Path
B=Path('/home/ubuntu/pr13-acceptance-20261009');E=B/'evidence/WAN-metric-interval-current-backup-r1-20261014';R=Path('/opt/fantasycard-github')
IMAGE='sha256:7c13e8ebbfec9a554dfd20a8d78ee223e15a4286c4875606ae82e7d46d226ef2'
QUERY="BEGIN READ ONLY; SET LOCAL statement_timeout='10s'; SELECT json_build_object('players',(SELECT count(*) FROM players),'wallets',(SELECT count(*) FROM player_wallets),'gold_total',(SELECT coalesce(sum(gold),0) FROM player_wallets),'equipment',(SELECT count(*) FROM equipments),'ledger',(SELECT count(*) FROM economy_ledger),'settlements',(SELECT count(*) FROM match_settlements),'pending_holds',(SELECT count(*) FROM settlement_asset_holds WHERE state='Pending'),'active_non_bot_members',(SELECT count(*) FROM match_players p JOIN matches m ON m.match_id=p.match_id WHERE NOT p.is_bot AND p.state IN ('Assigned','Ready','Active') AND m.status IN ('Starting','Running'))); ROLLBACK;"
def run(a,timeout=45):return subprocess.run(a,capture_output=True,check=True,timeout=timeout)
def inspect(name):return json.loads(run(['docker','inspect',name]).stdout)[0]
def assets():
 out=run(['docker','exec','fantasycard-cloud-postgres-1','psql','-X','-U','fantasycard','-d','fantasycard','-At','-v','ON_ERROR_STOP=1','-c',QUERY]).stdout.decode();return next(json.loads(l) for l in out.splitlines() if l.startswith('{'))
def healthy():
 try:
  with urllib.request.urlopen('http://127.0.0.1:8080/health/ready',timeout=10) as h:return h.status==200
 except OSError:return False
lock=Path('/tmp/fantasycard-update.lock').open('r+b');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
with (B/'evidence/shared-resource-coordination.lock').open('a') as coordination:
 fcntl.flock(coordination,fcntl.LOCK_EX);assert not (E/'telemetry-env-restored.original.json').exists()
 old_record=json.loads((B/'secrets/WAN-metric-before-environment-r1.original.json').read_bytes());assert 'OTEL_METRIC_EXPORT_INTERVAL' not in old_record
 c=inspect('fantasycard-cloud-server-1');assert c['Image']==IMAGE and c['State']['Running'];current=dict(v.split('=',1) for v in c['Config']['Env']);assert current.get('OTEL_METRIC_EXPORT_INTERVAL')=='1000';expected=dict(current);expected.pop('OTEL_METRIC_EXPORT_INTERVAL')
 before=assets();assert before['pending_holds']==before['active_non_bot_members']==0
 with urllib.request.urlopen('http://127.0.0.1:9090/api/v1/query?'+urllib.parse.urlencode({'query':'sum(fantasycard_realtime_connections_active{job="fantasycard",instance="otel-collector:9464"})'}),timeout=10) as r:rows=json.load(r)['data']['result']
 assert len(rows)==1 and float(rows[0]['value'][1])==0,'No real clients may remain during restoration'
 pg_id=inspect('fantasycard-cloud-postgres-1')['Id'];override=B/'secrets/WAN-metric-interval-restore-r1.override.json';assert not override.exists()
 def set_override(env):
  override.write_text(json.dumps({'services':{'server':{'image':IMAGE,'environment':{k:v.replace('$','$$') for k,v in env.items()}}}}));override.chmod(0o600)
 def compose(*args):return run(['docker','compose','-f',str(R/'server/compose.cloud.yaml'),'-f',str(override),'--env-file',str(R/'server/.env'),*args],timeout=180)
 set_override(expected);resolved=json.loads(compose('config','--format','json').stdout)['services']['server']['environment'];assert 'OTEL_METRIC_EXPORT_INTERVAL' not in resolved and all(str(resolved.get(k,''))==v for k,v in expected.items())
 intent=E/'telemetry-env-restore-intent.original.json';assert not intent.exists();intent.write_text(json.dumps({'old_container_id':c['Id'],'before_assets':before,'only_restored_key':'OTEL_METRIC_EXPORT_INTERVAL','all_current_other_environment_preserved':True,'automatic_retry':False},indent=2)+'\n');result={'ok':False,'MAIN_accepted':False}
 try:
  compose('up','-d','--no-deps','--no-build','--pull','never','server');deadline=time.monotonic()+120
  while not healthy():assert time.monotonic()<deadline;time.sleep(2)
  c=inspect('fantasycard-cloud-server-1');assert c['Image']==IMAGE and dict(v.split('=',1) for v in c['Config']['Env'])==expected and inspect('fantasycard-cloud-postgres-1')['Id']==pg_id;after=assets();assert before==after
  run(['curl','--fail','--silent','--show-error','--max-time','10','--resolve','www.relicbound.cn:443:127.0.0.1','https://www.relicbound.cn/health/ready'])
  result.update(ok=True,restored_original_metric_interval_key_absence=True,actual_container_id=c['Id'],all_current_other_environment_and_test_limits_preserved=True,postgres_unchanged=True,before_assets=before,after_assets=after,strict_origin_HTTPS_health_status=200,rollback_performed=False)
 except Exception as error:
  result.update(error=type(error).__name__,detail=str(error),original_failure_retained=True);set_override(current);compose('up','-d','--no-deps','--no-build','--pull','never','server');deadline=time.monotonic()+120
  while not healthy():assert time.monotonic()<deadline;time.sleep(2)
  assert dict(v.split('=',1) for v in inspect('fantasycard-cloud-server-1')['Config']['Env'])==current;result.update(rollback_performed=True,rollback_healthy=True)
 finally:
  if result['ok'] or result.get('rollback_healthy'):override.unlink()
  result['private_override_removed']=not override.exists();p=E/'telemetry-env-restored.original.json';assert not p.exists();p.write_text(json.dumps(result,indent=2)+'\n')
 print(json.dumps(result));assert result['ok']
