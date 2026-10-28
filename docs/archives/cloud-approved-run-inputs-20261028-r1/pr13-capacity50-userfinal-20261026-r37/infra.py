import pathlib,subprocess,json,os,time,secrets,hashlib,socket,urllib.request,traceback
O=pathlib.Path('/home/ubuntu/pr13-capacity50-userfinal-20261026-r37');tag='pr13-capacity50-r37';owner='01a152f7-f2a2-7b12-a4c5-a22b38ee9cd3';commands=[];images={'pg':'sha256:d3e1620b530c944afa6e887d22eb899824da68e19c52024bf98f5220c88a65b2','app':'sha256:e647601a9fa6dd7e1934907699f7d9c58c0965da2116b1325b826ba458ee6a3e','otel':'sha256:1ab0baba0ee3695d823c46653d8a6e8894896e668ce8bd7ebe002e948d827bc7','prom':'sha256:3b1d5be5c3eef4f027665ddaa3b1a7de8a58d96a0a6de5dd45629afd267ecaf0'}
def run(args,timeout=30):
 i=len(commands);r=subprocess.run(args,capture_output=True,timeout=timeout);(O/('infra-v2-'+str(i)+'.stdout.private.original.log')).write_bytes(r.stdout);(O/('infra-v2-'+str(i)+'.stderr.private.original.log')).write_bytes(r.stderr);commands.append({'args':args,'exit':r.returncode});assert r.returncode==0,'command failed '+str(i);return r.stdout
labels=['--label','pr13.round=current-capacity50-userfinal-r37','--label','pr13.owner='+owner];base=['docker','run','-d','--pull','never',*labels,'--log-driver','json-file','--log-opt','max-size=10m','--log-opt','max-file=2','--cpu-shares','256'];created=[]
try:
 os.nice(10);s=os.statvfs('/');assert s.f_bavail*s.f_frsize>=3000000000 and 100*s.f_bavail/s.f_blocks>=5
 for port in [18591,18593,18594,18595,18596]:
  q=socket.socket();q.bind(('127.0.0.1',port));q.close()
 names=run(['docker','ps','-a','--format','{{.Names}}']).decode().splitlines();assert not any(tag+'-'+kind in names for kind in ['pg','app','otel','prom'])
 for kind,image in images.items():assert json.loads(run(['docker','image','inspect',image]))[0]['Id']==image
 for name in ['pg-data','runtime','prom-data','results']:(O/name).mkdir(mode=0o777)
 for name in ['runtime','prom-data','results']:os.chmod(O/name,0o777)
 password=secrets.token_hex(24);(O/'pg.env').write_text('POSTGRES_USER=pr13_rebuild\nPOSTGRES_DB=ready_stop_capacity50_r37\nPOSTGRES_PASSWORD='+password+'\n');os.chmod(O/'pg.env',0o600)
 # Literal line endings are checked before any container consumes an env file.
 pgtext=(O/'pg.env').read_text().replace('\\n','\n');(O/'pg.env').write_text(pgtext)
 server={'ASPNETCORE_ENVIRONMENT':'Development','ASPNETCORE_URLS':'http://127.0.0.1:18591','Identity__EnableLocalAuth':'true','AllowedHosts':'localhost;127.0.0.1','ConnectionStrings__Postgres':'Host=127.0.0.1;Port=18593;Database=ready_stop_capacity50_r37;Username=pr13_rebuild;Password='+password+';Pooling=true','Diagnostics__LocalMetricsFile':'/own/server-metrics.jsonl','Persistence__MaxPoolSize':'16','Persistence__MinPoolSize':'1','ProtobufHttp__AllowLegacyJson':'false','Realtime__AllowLegacyAccessTokenQuery':'false','OTEL_EXPORTER_OTLP_ENDPOINT':'http://127.0.0.1:18594','OTEL_METRIC_EXPORT_INTERVAL':'1000','RequestLimits__AuthPermitLimit':'500','RequestLimits__EconomyWritePermitLimit':'3000','RequestLimits__MarketReadPermitLimit':'10000','RequestLimits__RealtimeCommandsPerSecond':'30'}
 (O/'server.env').write_text('\n'.join(k+'='+v for k,v in server.items()).replace('\\n','\n')+'\n');os.chmod(O/'server.env',0o600)
 node=json.loads(run(['docker','inspect','fantasycard-cloud-node-exporter-1']))[0];node_ip=node['NetworkSettings']['Networks']['fantasycard-cloud_default']['IPAddress'];assert node_ip.startswith('172.')
 otel="""receivers:
  otlp:
    protocols:
      grpc:
        endpoint: 127.0.0.1:18594
processors:
  memory_limiter:
    check_interval: 1s
    limit_mib: 96
    spike_limit_mib: 24
  batch:
    timeout: 1s
    send_batch_size: 256
exporters:
  prometheus:
    endpoint: 127.0.0.1:18595
    resource_to_telemetry_conversion:
      enabled: true
service:
  pipelines:
    metrics:
      receivers: [otlp]
      processors: [memory_limiter, batch]
      exporters: [prometheus]
"""
 prom='global:\n  scrape_interval: 2s\n  evaluation_interval: 2s\nscrape_configs:\n  - job_name: fantasycard\n    static_configs:\n      - targets: ["127.0.0.1:18595"]\n        labels:\n          instance: otel-collector:9464\n  - job_name: node\n    static_configs:\n      - targets: ["'+node_ip+':9100"]\n        labels:\n          instance: node-exporter:9100\n'
 prom=prom.replace('\\n','\n');(O/'otel.yaml').write_text(otel);(O/'prom.yaml').write_text(prom);os.chmod(O/'otel.yaml',0o644);os.chmod(O/'prom.yaml',0o644)
 run(['docker','network','create','--internal',*labels,tag+'-net'])
 pg=run([*base,'--name',tag+'-pg','--network',tag+'-net','--memory','512m','--pids-limit','128','--env-file',str(O/'pg.env'),'--mount','type=bind,source='+str(O/'pg-data')+',target=/var/lib/postgresql','-p','127.0.0.1:18593:5432',images['pg']]).decode().strip();created.append(pg)
 for attempt in range(60):
  r=subprocess.run(['docker','exec',tag+'-pg','pg_isready','-U','pr13_rebuild','-d','ready_stop_capacity50_r37'],capture_output=True)
  if r.returncode==0:break
  time.sleep(.5)
 else:raise RuntimeError('owned PG not ready')
 ot=run([*base,'--name',tag+'-otel','--network','host','--memory','128m','--pids-limit','64','--read-only','--mount','type=bind,source='+str(O/'otel.yaml')+',target=/etc/otelcol/config.yaml,readonly',images['otel'],'--config=/etc/otelcol/config.yaml']).decode().strip();created.append(ot)
 pr=run([*base,'--name',tag+'-prom','--network','host','--memory','256m','--pids-limit','64','--mount','type=bind,source='+str(O/'prom.yaml')+',target=/etc/prometheus/prometheus.yml,readonly','--mount','type=bind,source='+str(O/'prom-data')+',target=/prometheus',images['prom'],'--config.file=/etc/prometheus/prometheus.yml','--web.listen-address=127.0.0.1:18596','--storage.tsdb.path=/prometheus','--storage.tsdb.retention.time=2h']).decode().strip();created.append(pr)
 pginspect=json.loads(run(['docker','inspect',tag+'-pg']))[0];ip=pginspect['NetworkSettings']['Networks'][tag+'-net']['IPAddress'];q=socket.create_connection((ip,5432),timeout=3);q.close();envtext=(O/'server.env').read_text();envtext=envtext.replace('Host=127.0.0.1;Port=18593;','Host='+ip+';Port=5432;');(O/'server.env').write_text(envtext);os.chmod(O/'server.env',0o600)
 app=run([*base,'--name',tag+'-app','--network','host','--pid','host','--memory','1536m','--pids-limit','256','--read-only','--tmpfs','/tmp:rw,nosuid,size=64m','--env-file',str(O/'server.env'),'--mount','type=bind,source='+str(O/'runtime')+',target=/own',images['app']]).decode().strip();created.append(app)
 for attempt in range(90):
  try:
   with urllib.request.urlopen('http://127.0.0.1:18591/health/ready',timeout=2) as r:assert r.status==200;r.read(4096);break
  except Exception:time.sleep(.5)
 else:raise RuntimeError('owned APP not ready')
 sql="""CREATE FUNCTION pr13_owned_match_budget() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN PERFORM pg_advisory_xact_lock(20261026,40); IF (SELECT count(*) FROM matches)>=40 THEN RAISE EXCEPTION 'owned current-round remaining cumulative world budget40 exhausted'; END IF; RETURN NEW; END $$; CREATE TRIGGER pr13_owned_match_budget BEFORE INSERT ON matches FOR EACH ROW EXECUTE FUNCTION pr13_owned_match_budget();"""
 run(['docker','exec',tag+'-pg','psql','-v','ON_ERROR_STOP=1','-U','pr13_rebuild','-d','ready_stop_capacity50_r37','-c',sql])
 metadata=[]
 for cid in created:
  x=json.loads(run(['docker','inspect',cid]))[0];metadata.append({'id':x['Id'],'name':x['Name'],'image':x['Image'],'PID':x['State']['Pid'],'running':x['State']['Running'],'env_sha256':hashlib.sha256(json.dumps(sorted(x['Config']['Env'])).encode()).hexdigest(),'memory_limit':x['HostConfig']['Memory'],'PID_mode':x['HostConfig']['PidMode'],'network_mode':x['HostConfig']['NetworkMode']})
 result={'ok':True,'containers':metadata,'owned_API':'http://127.0.0.1:18591','owned_prometheus':'http://127.0.0.1:18596','real_node_exporter_target':node_ip+':9100','metric_label_aliases_only_no_synthetic_values':True,'temporary_capacity_limits':{'auth':500,'write':3000,'read':10000,'realtime':30,'owned_bypass':False},'world_budget':40,'commands':commands}
except BaseException as e:
 result={'ok':False,'error_type':type(e).__name__,'error':str(e),'created_ids':created,'commands':commands};(O/'infra-error-v2.original.log').write_text(traceback.format_exc())
(O/'infra-terminal.original.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result),flush=True)
