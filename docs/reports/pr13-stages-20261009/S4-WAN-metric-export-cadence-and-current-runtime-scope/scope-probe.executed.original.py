import json,subprocess,time,urllib.request,urllib.parse
from pathlib import Path
E=Path('/home/ubuntu/pr13-acceptance-20261009/evidence/WAN-metric-interval-current-backup-r1-20261014');expected='9300fdf0c8701ff2c03b232d4d29e58cfa80b6a5c8673979b7ba5fcccb9362e9';scope='d44e1a80-1a6a-4628-9ca3-21dbf81dea10'
def container():return json.loads(subprocess.check_output(['docker','inspect','fantasycard-cloud-server-1']))[0]
def counter():
 q='sum(http_server_request_duration_seconds_count{job="fantasycard",instance="otel-collector:9464",http_route="/health/ready",service_instance_id="'+scope+'"})'
 with urllib.request.urlopen('http://127.0.0.1:9090/api/v1/query?'+urllib.parse.urlencode({'query':q}),timeout=10) as r:rows=json.load(r)['data']['result']
 return float(rows[0]['value'][1]) if len(rows)==1 else None
assert container()['Id']==expected;before=counter();assert before is not None
with urllib.request.urlopen('http://127.0.0.1:8080/health/ready',timeout=10) as r:assert r.status==200
until=time.monotonic()+45;after=counter()
while after is None or after<=before:
 assert time.monotonic()<until,'Current process health request not exported within diagnostic bound';time.sleep(2);after=counter()
assert container()['Id']==expected;p=E/'current-runtime-metric-scope-health-probe.original.json';assert not p.exists();v={'ok':True,'actual_container_id':expected,'current_service_instance_id':scope,'original_old_service_instance_id_excluded':'dc9402ca-937a-4bc2-a275-cae5f2d43b01','current_scoped_health_counter_before':before,'current_scoped_health_counter_after':after,'actual_healthy_request_observed_by_current_scope':True,'gameplay_executed':False,'MAIN_accepted':False};p.write_text(json.dumps(v,indent=2)+'\n');print(json.dumps(v))
