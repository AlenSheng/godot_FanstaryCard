import json,math,subprocess,sys,time,urllib.request,urllib.parse
from pathlib import Path
QUERIES = {
    'cpu': '100*(1-avg(rate(node_cpu_seconds_total{job="node",instance="node-exporter:9100",mode="idle"}[1m])))',
    'memory_available': '100*node_memory_MemAvailable_bytes{job="node",instance="node-exporter:9100"}/node_memory_MemTotal_bytes{job="node",instance="node-exporter:9100"}',
    'memory_available_bytes': 'node_memory_MemAvailable_bytes{job="node",instance="node-exporter:9100"}',
    'disk_available': '100*node_filesystem_avail_bytes{job="node",instance="node-exporter:9100",mountpoint="/"}/node_filesystem_size_bytes{job="node",instance="node-exporter:9100",mountpoint="/"}',
    'actor_wait': 'histogram_quantile(0.95,sum(rate(fantasycard_room_actor_command_wait_milliseconds_bucket{job="fantasycard",instance="otel-collector:9464"}[5m])) by (le))',
    'server_humans_in_room': 'fantasycard_rooms_humans_active{job="fantasycard",instance="otel-collector:9464"}',
}
def metrics(base, timeout_seconds=3):
    result = dict.fromkeys(QUERIES)
    # One snapshot and one bounded network round trip for all independent
    # measurements; the label exists only in this query's result vector.
    query = ' or '.join('label_replace(('+expression+'),"pr13_metric","'+key+'","",".*")'
                        for key,expression in QUERIES.items())
    try:
        with urllib.request.urlopen(base.rstrip('/')+'/api/v1/query?'+urllib.parse.urlencode({'query':query}),timeout=timeout_seconds) as r:
            rows=json.load(r)['data']['result']
        for key in result:
            matches=[row for row in rows if row.get('metric',{}).get('pr13_metric')==key]
            if len(matches)!=1: continue
            value=float(matches[0]['value'][1])
            result[key]=value if math.isfinite(value) else None
    except (OSError, ValueError, KeyError, IndexError, TypeError): pass
    return result

METRIC_SCOPE='d44e1a80-1a6a-4628-9ca3-21dbf81dea10'
EXPECTED_CONTAINER='9300fdf0c8701ff2c03b232d4d29e58cfa80b6a5c8673979b7ba5fcccb9362e9'
for key in ['actor_wait','server_humans_in_room']:
 QUERIES[key]=QUERIES[key].replace('instance=\"otel-collector:9464\"','instance=\"otel-collector:9464\",service_instance_id=\"'+METRIC_SCOPE+'\"')
R='/opt/fantasycard-github';c=json.loads(subprocess.check_output(['docker','inspect','fantasycard-cloud-server-1']))[0];expected='sha256:7c13e8ebbfec9a554dfd20a8d78ee223e15a4286c4875606ae82e7d46d226ef2';assert c['Image']==expected and c['State']['Running'];revision=c['Config']['Labels']['org.opencontainers.image.revision'];assert revision=='d2805757db7330ede4ff0bad1972697fe397e90b';head=subprocess.check_output(['git','-C',R,'rev-parse','HEAD'],text=True).strip();assert not subprocess.check_output(['git','-C',R,'diff','--name-only',revision,head,'--','server/src','server/config','protocol']).strip()
start=time.monotonic()
with urllib.request.urlopen('http://127.0.0.1:8080/health/ready',timeout=10) as h:health=h.status
v={'readonly':True,'actual_server_image':c['Image'],'actual_container_id':c['Id'],'actual_runtime_revision':revision,'actual_checkout_sha':head,'current_product_source_equal':True,'health_status':health,'health_elapsed_ms':(time.monotonic()-start)*1000,'at_unix_ms':int(time.time()*1000),'resources':metrics('http://127.0.0.1:9090',timeout_seconds=10)}
assert c['Id']==EXPECTED_CONTAINER
env=dict(x.split('=',1) for x in c['Config']['Env']);assert env.get('OTEL_METRIC_EXPORT_INTERVAL')=='1000'
v['actual_metric_export_interval_ms']=1000;v['current_metric_service_instance_id']=METRIC_SCOPE
with urllib.request.urlopen('http://127.0.0.1:9090/api/v1/query?'+urllib.parse.urlencode({'query':'up{job=\"fantasycard\",instance=\"otel-collector:9464\"}'}),timeout=10) as response:up=json.load(response)['data']['result']
assert len(up)==1 and float(up[0]['value'][1])==1;v['game_metrics_exporter_up']=1
if len(sys.argv)>1 and sys.argv[1]=='assets':
 query="BEGIN READ ONLY; SET LOCAL statement_timeout='10s'; SELECT json_build_object('players',(SELECT count(*) FROM players),'wallets',(SELECT count(*) FROM player_wallets),'gold_total',(SELECT coalesce(sum(gold),0) FROM player_wallets),'equipment',(SELECT count(*) FROM equipments),'ledger',(SELECT count(*) FROM economy_ledger),'settlements',(SELECT count(*) FROM match_settlements),'pending_holds',(SELECT count(*) FROM settlement_asset_holds WHERE state='Pending'),'active_non_bot_members',(SELECT count(*) FROM match_players p JOIN matches m ON m.match_id=p.match_id WHERE NOT p.is_bot AND p.state IN ('Assigned','Ready','Active') AND m.status IN ('Starting','Running'))); ROLLBACK;"
 raw=subprocess.check_output(['docker','exec','fantasycard-cloud-postgres-1','psql','-X','-U','fantasycard','-d','fantasycard','-At','-v','ON_ERROR_STOP=1','-c',query],text=True);v['assets']=next(json.loads(l) for l in raw.splitlines() if l.startswith('{'))
print(json.dumps(v))
