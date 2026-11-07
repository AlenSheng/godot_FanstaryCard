from pathlib import Path
import gzip,hashlib,io,json,os,shutil,struct,subprocess,sys,tarfile,threading,time

label='season-balance-20261107-f03-minimal-app-r4'
root=Path('/home/ubuntu')/label;upload=Path('/home/ubuntu')/(label+'-upload')
assert not root.exists();root.mkdir(mode=0o700);public=root/'public';public.mkdir()
created=[];schema=None;private_env=None;new_image=None;new_tag='fantasycard-f03-minimal:app-candidate-r4';stop=threading.Event();breach=threading.Event()
def run(args,**kwargs):return subprocess.check_output(args,stderr=subprocess.PIPE,timeout=40,**kwargs)
def resources():
    m=dict(x.split(':',1) for x in Path('/proc/meminfo').read_text().splitlines());disk=shutil.disk_usage(root)
    r=dict(available_ram=int(m['MemAvailable'].split()[0])*1024,free_disk=disk.free,disk_fraction=disk.free/disk.total)
    r['ok']=r['available_ram']>=500*1024**2 and r['free_disk']>=3*1024**3 and r['disk_fraction']>=.05;return r
def guard(extra=0):
    r=resources();assert r['ok'] and r['free_disk']>=3*1024**3+extra and not breach.is_set();return r
def inspect(cid):return json.loads(run(['docker','inspect',cid]))[0]
def production_state():
    rows=[]
    for cid in run(['docker','ps','-q','--filter','label=com.docker.compose.project=fantasycard-cloud']).decode().split():
        item=inspect(cid);service=(item['Config'].get('Labels') or {}).get('com.docker.compose.service')
        rows.append(dict(id=cid,service=service,image=item['Image'],started=item['State']['StartedAt'],running=item['State']['Running']))
    return sorted(rows,key=lambda r:r['id'])
def watcher():
    with (public/'resources.original.jsonl').open('x') as log:
        while not stop.wait(.5):
            r=resources();log.write(json.dumps(r)+'\n');log.flush()
            if not r['ok']:
                breach.set()
                for cid in list(created):
                    try:
                        item=inspect(cid)
                        if item['Config']['Labels'].get('com.fantasycard.task')==label and item['State']['Running']:
                            subprocess.run(['docker','kill',cid],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=10)
                    except Exception:pass
                return
before=production_state();(public/'production-before.original.json').write_text(json.dumps(before,indent=2)+'\n')
thread=threading.Thread(target=watcher,daemon=True);thread.start();result=None
try:
    first=guard(64*1024**2);assert first['available_ram']>=700*1024**2
    assert not run(['docker','ps','-a','-q','--filter','label=com.fantasycard.task='+label]).strip()
    assert subprocess.run(['docker','image','inspect',new_tag],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL).returncode!=0
    assert run(['findmnt','-n','-o','FSTYPE','--target',str(upload)]).decode().strip()=='tmpfs'
    raw=(upload/'stream.bin').read_bytes();length=struct.unpack('!I',raw[:4])[0];manifest=json.loads(raw[4:4+length]);payload=raw[4+length:]
    assert manifest['task']==label and len(payload)==manifest['payload_bytes'] and hashlib.sha256(payload).hexdigest()==manifest['payload_sha256']
    body=gzip.decompress(payload);assert len(body)==manifest['tar_bytes'] and manifest['expanded_bytes']<16*1024**2
    files=manifest['payload_files'];assert len(files)==18 and 'CANDIDATE-NOT-YET-VALIDATED.txt' in files
    with tarfile.open(fileobj=io.BytesIO(body),mode='r:') as archive:
        assert len(archive.getmembers())==18
        for member in archive.getmembers():
            assert member.isfile() and member.name in files and '/' not in member.name and member.mode==0o644 and member.uid==member.gid==1654
            assert hashlib.sha256(archive.extractfile(member).read()).hexdigest()==files[member.name]
    base=manifest['base_image'];base_info=json.loads(run(['docker','image','inspect',base]))[0]
    assert base_info['Id']==base and not base_info['Config'].get('Volumes') and base_info['Config'].get('User')=='1654'
    assert base_info['Config']['WorkingDir']=='/app' and base_info['Config']['Entrypoint']==['dotnet','FantasyCard.Server.dll']
    env_names=[v.split('=',1)[0].upper() for v in base_info['Config'].get('Env',[])]
    assert not any(any(term in name for term in ['PASSWORD','APIKEY','API_KEY','SECRET','TOKEN','CONNECTIONSTRING']) for name in env_names)
    (public/'input-manifest.original.json').write_text(json.dumps(manifest,indent=2)+'\n')
    cid=run(['docker','create','--name','fc-f03-app4-builder-r1','--label','com.fantasycard.task='+label,'--network','none',base]).decode().strip();created.append(cid)
    guard();run(['docker','cp','-',cid+':/app/'],input=body)
    guard();new_image=run(['docker','commit','--change','LABEL org.opencontainers.image.revision='+manifest['compiled_source'],
        '--change','LABEL com.fantasycard.task='+label,'--change','LABEL fantasycard.candidate=true',cid,new_tag]).decode().strip()
    image=json.loads(run(['docker','image','inspect',new_image]))[0]
    assert image['Id']!=base and image['Config']['User']=='1654' and image['RootFS']['Layers'][:-1]==base_info['RootFS']['Layers']
    (public/'candidate-image.original.json').write_text(json.dumps(dict(id=new_image,base=base,size=image['Size'],user=image['Config']['User'],working_dir=image['Config']['WorkingDir'],entrypoint=image['Config']['Entrypoint'],layers=image['RootFS']['Layers'],revision=image['Config']['Labels']['org.opencontainers.image.revision']),indent=2)+'\n')
    outputs={}
    commands={
        'hashes':['sha256sum',*['/app/'+name for name in sorted(files)]],
        'inventory':['find','/app','-type','f','-printf','%P\n'],
        'runtimes':['dotnet','--list-runtimes'],
        'sdks':['dotnet','--list-sdks'],
    }
    for name,command in commands.items():
        guard();args=['docker','create','--name','fc-f03-app4-'+name+'-r1','--label','com.fantasycard.task='+label,
            '--read-only','--network','none','--user','1654:1654','--cap-drop','ALL','--security-opt','no-new-privileges:true',
            '--cpus','1','--memory','128m','--memory-swap','128m','--pids-limit','64','--entrypoint',command[0],new_image,*command[1:]]
        utility=run(args).decode().strip();created.append(utility);output=run(['docker','start','-a',utility]).decode();item=inspect(utility)
        assert item['State']['ExitCode']==0 and not item['State']['Running']
        assert item['HostConfig']['ReadonlyRootfs'] and item['HostConfig']['NetworkMode']=='none' and item['Config']['User']=='1654:1654'
        outputs[name]=output;(public/(name+'.stdout.original.log')).write_text(output)
    actual={line.split('  ',1)[1].removeprefix('/app/'):line.split('  ',1)[0] for line in outputs['hashes'].splitlines()}
    assert actual==files and set(outputs['inventory'].splitlines())==set(files)
    assert 'Microsoft.NETCore.App 10.' in outputs['runtimes'] and 'Microsoft.AspNetCore.App 10.' in outputs['runtimes'] and not outputs['sdks'].strip()
    import re,secrets,uuid
    pg='803968e390014540be88f60b9ac43203946d0145bf886fc61d9d9d4d04bc3b1a'
    pginfo=inspect(pg);assert pginfo['State']['Running'] and pginfo['Config']['Labels']['com.fantasycard.task']=='season-balance-20261102-a03-storage-r1'
    schema='fc_f03_minapp_'+uuid.uuid4().hex;assert re.fullmatch('fc_f03_minapp_[a-f0-9]{32}',schema)
    def psql(sql):return run(['docker','exec',pg,'psql','-U','season_stage','-d','season_stage','-XqAt','-v','ON_ERROR_STOP=1','-c',sql]).decode().strip()
    assert psql('SELECT current_user,current_database()')=='season_stage|season_stage'
    assert psql("SELECT count(*) FROM pg_namespace WHERE nspname='"+schema+"'")=='0'
    psql('CREATE SCHEMA '+schema)
    (public/'owned-schema.original.json').write_text(json.dumps(dict(schema=schema,created_for_this_task=True,production_database_used=False))+'\n')
    password=json.loads(Path('/home/ubuntu/season-balance-20261102-a03-storage-r1/test-connection.private.json').read_text())['password']
    assert '\n' not in password and '\r' not in password
    admin=secrets.token_hex(32);port=19073
    dsn='Host=127.0.0.1;Port=5432;Database=season_stage;Username=season_stage;Password="'+password.replace('"','""')+'";Search Path='+schema+';Maximum Pool Size=8;Timeout=10;CommandTimeout=30;Application Name=fc-f03-minapp-r1'
    private_env=root/'runtime.private.env'
    private_env.write_text('ASPNETCORE_ENVIRONMENT=Production\nASPNETCORE_URLS=http://127.0.0.1:'+str(port)+'\nDOTNET_EnableDiagnostics=0\nIdentity__EnableLocalAuth=false\nIdentity__AllowManagedLocalAuth=false\nAdmin__ApiKey='+admin+'\nConnectionStrings__Postgres='+dsn+'\n')
    private_env.chmod(0o600)
    control=root/'http-control.private.json';control.write_text(json.dumps(dict(admin_key=admin,port=port)));control.chmod(0o600)
    app=run(['docker','run','-d','--name','fc-f03-app4-server-r1','--label','com.fantasycard.task='+label,'--network','container:'+pg,
        '--user','1654:1654','--read-only','--tmpfs','/tmp:rw,noexec,nosuid,size=64m','--cap-drop','ALL','--security-opt','no-new-privileges:true',
        '--cpus','1','--memory','512m','--memory-swap','512m','--pids-limit','192','--log-opt','max-size=5m','--log-opt','max-file=1',
        '--env-file',str(private_env),new_image]).decode().strip();created.append(app)
    probe=root/'http-probe.py';probe.write_text("from pathlib import Path\nimport hashlib,json,sys,time,urllib.error,urllib.request\n\nroot=Path(sys.argv[1]);control=json.loads((root/'http-control.private.json').read_text());base='http://127.0.0.1:'+str(control['port']);checks=[]\ndef request(method,path,data=None,headers=None):\n    call=urllib.request.Request(base+path,data=data,method=method,headers=headers or {})\n    try:\n        with urllib.request.urlopen(call,timeout=3) as response:status=response.status;body=response.read();received=dict(response.headers)\n    except urllib.error.HTTPError as error:status=error.code;body=error.read();received=dict(error.headers)\n    return dict(status=status,headers=received,body=body)\ndef check(name,response,status,extra=True):\n    checks.append(dict(name=name,status=response['status'],expected=status,passed=response['status']==status and extra,content_type=response['headers'].get('Content-Type'),body_bytes=len(response['body']),body_sha256=hashlib.sha256(response['body']).hexdigest()))\nready=None\nfor _ in range(60):\n    try:\n        ready=request('GET','/health/ready')\n        if ready['status']==200:break\n    except (OSError,urllib.error.URLError):pass\n    time.sleep(.5)\nassert ready is not None\ncheck('readiness',ready,200,ready['body'].strip()==b'Healthy')\ncheck('liveness',request('GET','/health/live'),200)\nbootstrap=request('GET','/api/v1/bootstrap');check('unauthenticated typed bootstrap',bootstrap,401,'protobuf' in bootstrap['headers'].get('Content-Type',''))\ndef field(number,value):\n    data=value.encode();assert len(data)<128;return bytes([number*8+2,len(data)])+data\nlocal=field(1,'f03-minapp-production-guard')+field(2,'Isolated production guard')\ncheck('old media type rejected',request('POST','/api/v1/auth/local',local,{'Content-Type':'application/x-protobuf'}),415)\ncheck('production local auth closed with required false flag',request('POST','/api/v1/auth/local',local,{'Content-Type':'application/protobuf'}),404)\ncheck('admin requires secure transport',request('GET','/api/admin/client-settings'),403)\ncheck('secure admin requires key',request('GET','/api/admin/client-settings',headers={'X-Forwarded-Proto':'https'}),401)\nauthenticated=request('GET','/api/admin/client-settings',headers={'X-Forwarded-Proto':'https','X-Admin-Key':control['admin_key']})\ncheck('isolated authenticated read-only admin',authenticated,200,'private' in authenticated['headers'].get('Cache-Control','') and 'no-store' in authenticated['headers'].get('Cache-Control',''))\ncheck('public client info',request('GET','/api/v1/client-info'),200)\nfor path in ['/release-encryption.key','/appsettings.Development.json','/mapping.xml']:\n    check('private package path denied '+path,request('GET',path),404)\nresult=dict(ok=all(c['passed'] for c in checks),checks=checks,new_gameplay_starts=0,no_login_account_created=True,no_purchase_queue_ready_or_settlement=True)\n(root/'public/http-probe.original.json').write_text(json.dumps(result,indent=2)+'\\n');print(json.dumps(dict(ok=True,checks=len(checks),new_gameplay_starts=0)))\n\nassert result['ok'], 'HTTP boundary outcomes contain failures; all checks recorded'\n")
    command=['nsenter','--target',str(pginfo['State']['Pid']),'--net','--','python3','-B',str(probe),str(root)]
    diagnostic=subprocess.run(command,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=60)
    (public/'http-driver.stdout.original.log').write_bytes(diagnostic.stdout)
    clean_error=diagnostic.stderr.decode(errors='replace').replace(password,'[REDACTED]').replace(admin,'[REDACTED]')
    (public/'http-driver.stderr.original.log').write_text(clean_error)
    state=inspect(app);(public/'application-state.original.json').write_text(json.dumps({k:state['State'].get(k) for k in ['Status','Running','Pid','ExitCode','Error','OOMKilled','StartedAt','FinishedAt']},indent=2)+'\n')
    captured=subprocess.run(['docker','logs',app],stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=20)
    logs=(captured.stdout+captured.stderr).decode(errors='replace');(root/'application.private.log').write_text(logs);(root/'application.private.log').chmod(0o600)
    safe_logs=logs.replace(password,'[REDACTED]').replace(admin,'[REDACTED]')
    assert password not in safe_logs and admin not in safe_logs
    (public/'application-redacted.original.log').write_text(safe_logs)
    (public/'application-log-capture.original.json').write_text(json.dumps(dict(stdout_bytes=len(captured.stdout),stderr_bytes=len(captured.stderr),both_streams_collected=True,raw_log_private=True))+'\n')
    assert diagnostic.returncode==0,'Isolated HTTP probe failed; inspect redacted public driver result'
    assert inspect(app)['State']['Running']
    facts=json.loads(psql('SET search_path TO '+schema+"; SELECT json_build_object('migration_count',(SELECT count(*) FROM schema_migrations),'migration_max',(SELECT max(version) FROM schema_migrations),'players',(SELECT count(*) FROM players),'matches',(SELECT count(*) FROM matches));"))
    assert facts['migration_count']==52 and facts['migration_max']==55 and facts['players']==facts['matches']==0
    (public/'runtime-db-facts.original.json').write_text(json.dumps(facts,indent=2)+'\n')
    actual_hashes=run(['docker','exec',app,'sha256sum',*['/app/'+name for name in sorted(files)]]).decode()
    assert {line.split('  ',1)[1].removeprefix('/app/'):line.split('  ',1)[0] for line in actual_hashes.splitlines()}==files
    (public/'running-app-file-hashes.original.log').write_text(actual_hashes)
    after=production_state();assert before==after and not breach.is_set();guard()
    result=dict(ok=True,exact18_files_and_SHA=True,UID1654_can_read_all_files=True,read_only_rootfs=True,no_network=True,no_SDK_present=True,no_SDK_started=True,
        game_program_started_in_owned_isolation=True,only_owned_test_schema_accessed=True,http_boundaries_verified=True,new_gameplay_starts=0,production_containers_unchanged=True,production_deployment=False,
        candidate_marker_retained=True,not_a_full_release_verification=True,candidate_image=new_image,payload_sha256=manifest['payload_sha256'])
except Exception as error:
    result=dict(ok=False,type=type(error).__name__,error=str(error),new_gameplay_starts=0,production_deployment=False)
finally:
    cleanup=[]
    for cid in reversed(created):
        try:
            item=inspect(cid);assert item['Config']['Labels'].get('com.fantasycard.task')==label
            subprocess.run(['docker','rm','-f',cid],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,check=True,timeout=20);cleanup.append(cid)
        except Exception as error:cleanup.append(dict(id=cid,error_type=type(error).__name__))
    schema_removed=False
    if schema is not None:
        assert re.fullmatch('fc_f03_minapp_[a-f0-9]{32}',schema)
        psql('DROP SCHEMA '+schema+' CASCADE')
        assert psql("SELECT count(*) FROM pg_namespace WHERE nspname='"+schema+"'")=='0';schema_removed=True
    if private_env is not None and private_env.exists():private_env.unlink()
    if (root/'http-control.private.json').exists():(root/'http-control.private.json').unlink()
    image_removed=False
    if new_image is not None:
        item=json.loads(run(['docker','image','inspect',new_image]))[0];assert item['Config']['Labels'].get('com.fantasycard.task')==label
        assert not run(['docker','ps','-a','-q','--filter','ancestor='+new_image]).strip()
        subprocess.run(['docker','image','rm',new_tag],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,check=True,timeout=20);image_removed=True
    after=production_state();assert before==after
    stop.set();thread.join(timeout=5)
    (public/'cleanup.original.json').write_text(json.dumps(dict(owned_containers_removed=cleanup,owned_candidate_image_removed=image_removed,owned_schema_removed=schema_removed,private_env_removed=private_env is None or not private_env.exists(),production_state_unchanged=before==after,resources=resources()),indent=2)+'\n')
    (public/'result.json').write_text(json.dumps(result,indent=2)+'\n')
with tarfile.open(root/'public-evidence.tar.gz','w:gz') as tar:
    for p in sorted(public.iterdir()):
        if p.is_file():tar.add(p,arcname=p.name,recursive=False)
print(json.dumps(result),flush=True)
