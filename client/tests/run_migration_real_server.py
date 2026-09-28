"""Godot -> actual .NET -> isolated PostgreSQL schema integration; loopback only.
Connection file is consumed privately. No credentials are written to test output.
"""
import argparse, json, os, re, shutil, socket, subprocess, time, uuid
from pathlib import Path
from urllib.request import urlopen

p=argparse.ArgumentParser()
for flag in ['godot','dotnet','psql','connection-file']: p.add_argument('--'+flag,required=True)
p.add_argument('--work-dir',default='work/client-real-server')
a=p.parse_args()
repo=Path(__file__).resolve().parents[2]
work=(repo/a.work_dir).resolve(); work.mkdir(parents=True,exist_ok=True)
connection=Path(a.connection_file).read_text(encoding='utf-8-sig').strip()
settings={k.strip().lower():v.strip() for k,v in (pair.split('=',1) for pair in connection.split(';') if '=' in pair)}
if settings.get('host') not in ['127.0.0.1','localhost','::1']: raise SystemExit('Refusing non-loopback PostgreSQL')
if settings.get('database') != 'fc_migration_tests': raise SystemExit('Use the dedicated fc_migration_tests database')
schema='fc_client_real_'+uuid.uuid4().hex
if not re.fullmatch(r'fc_client_real_[0-9a-f]{32}',schema): raise SystemExit('Invalid isolated schema')
pg_env=dict(os.environ,PGHOST=settings['host'],PGPORT=settings.get('port','5432'),PGDATABASE=settings['database'],PGUSER=settings.get('username',settings.get('user id','')),PGPASSWORD=settings.get('password',''))
pg_env.pop('PGOPTIONS',None)
flags=getattr(subprocess,'CREATE_NO_WINDOW',0)
records=[]; server=None; server_log=None; owned=False; ok=False

def sql(command):
    result=subprocess.run([a.psql,'-X','-v','ON_ERROR_STOP=1','-c',command],env=pg_env,capture_output=True,timeout=30,creationflags=flags)
    if result.returncode: raise RuntimeError('Isolated schema operation failed (database output withheld)')

def run(command,label,cwd,env,timeout=120):
    r=subprocess.run(command,cwd=cwd,env=env,capture_output=True,timeout=timeout,creationflags=flags)
    output=(r.stdout+r.stderr).decode('utf-8',errors='replace')
    # Build/Godot assertions do not print response bodies; redact defensively.
    output=output.replace(connection,'[connection redacted]')
    (work/(label+'.log')).write_text(output,encoding='utf-8')
    passed=r.returncode==0 and 'ERROR:' not in output
    records.append({'step':label,'exit_code':r.returncode,'passed':passed,'log':label+'.log'})
    print(label+': '+('PASS' if passed else 'FAIL'),flush=True)
    return passed

try:
    sql('CREATE SCHEMA '+schema); owned=True
    build_env=dict(os.environ,DOTNET_ROOT=str(Path(a.dotnet).resolve().parent))
    build_env['PATH']=str(Path(a.dotnet).resolve().parent)+os.pathsep+build_env.get('PATH','')
    artifacts=work/'build'
    if not run([a.dotnet,'build','src/FantasyCard.Server/FantasyCard.Server.csproj','--artifacts-path',str(artifacts),'-v','minimal'],'server-build',repo/'server',build_env): raise RuntimeError('Server build failed')
    dll=artifacts/'bin/FantasyCard.Server/debug/FantasyCard.Server.dll'
    if not dll.exists(): raise RuntimeError('Expected isolated server assembly missing')
    with socket.socket() as probe:
        probe.bind(('127.0.0.1',0)); port=probe.getsockname()[1]
    address='http://127.0.0.1:'+str(port)
    env=dict(build_env,ASPNETCORE_ENVIRONMENT='Development',ASPNETCORE_URLS=address,
        ConnectionStrings__Postgres=connection.rstrip(';')+';Search Path='+schema,
        Identity__EnableLocalAuth='true',ProtobufHttp__AllowLegacyJson='false',Realtime__AllowLegacyAccessTokenQuery='false',
        Logging__LogLevel__Default='Warning',Logging__LogLevel__FantasyCard='Warning',
        FANTASYCARD_SERVER_URL=address)
    for key in list(env):
        if key.startswith('OTEL_EXPORTER_'): env.pop(key)
    server_log=open(work/'server.log','wb')
    server=subprocess.Popen([a.dotnet,str(dll)],cwd=repo/'server/src/FantasyCard.Server',env=env,stdout=server_log,stderr=subprocess.STDOUT,creationflags=flags)
    ready=False
    for attempt in range(150):
        if server.poll() is not None: break
        try:
            with urlopen(address+'/health/ready',timeout=.5) as response: ready=response.status==200
        except Exception: pass
        if ready: break
        time.sleep(.2)
    records.append({'step':'server-ready','passed':ready})
    if not ready: raise RuntimeError('Local server did not become ready')
    project=work/'godot'
    for folder in ['network','data','tests']: (project/folder).mkdir(parents=True,exist_ok=True)
    for name in ['gateway.gd','protobuf.gd','http_protocol.gd']: shutil.copyfile(repo/'client/network'/name,project/'network'/name)
    for name in ['http_schema.json','http_endpoints.json','realtime_schema.json']: shutil.copyfile(repo/'client/data'/name,project/'data'/name)
    shutil.copyfile(repo/'client/tests/test_migration_real_server.gd',project/'tests/test_migration_real_server.gd')
    shutil.copyfile(repo/'client/tests/test_http_decode_scheduling.gd',project/'tests/test_http_decode_scheduling.gd')
    (project/'project.godot').write_text('[application]\nconfig/name="Real protobuf isolated integration"\n[rendering]\nrenderer/rendering_method="gl_compatibility"\n',encoding='utf-8')
    if not run([a.godot,'--headless','--language','en','--path',str(project),'--editor','--import','--quit'],'godot-import',repo,env): raise RuntimeError('Godot import failed')
    ok=run([a.godot,'--headless','--language','en','--path',str(project),'--script','res://tests/test_migration_real_server.gd'],'godot-real-server',repo,env)
    if ok:
        ok=run([a.godot,'--headless','--language','en','--max-fps','60','--path',str(project),'--script','res://tests/test_http_decode_scheduling.gd'],'godot-decode-scheduling',repo,env)
except Exception as exc:
    # Do not include connection strings or HTTP bodies in error text.
    print(type(exc).__name__+': integration failed; inspect redacted task logs',flush=True)
    records.append({'step':'runner','passed':False,'error_type':type(exc).__name__})
finally:
    if server is not None:
        server.terminate()
        try: server.wait(timeout=10)
        except subprocess.TimeoutExpired: server.kill(); server.wait(timeout=5)
    if server_log is not None: server_log.close()
    if owned:
        sql('DROP SCHEMA '+schema+' CASCADE')
        records.append({'step':'owned-schema-cleanup','passed':True})
    if (work/'server.log').exists():
        log=(work/'server.log').read_text(encoding='utf-8',errors='replace')
        secret_free='access_token=' not in log and 'ticket=' not in log and settings.get('password','\0') not in log
        records.append({'step':'server-log-no-credentials','passed':secret_free})
        ok=ok and secret_free
    (work/'results.json').write_text(json.dumps({'ok':ok,'schema':schema,'runs':records},indent=2),encoding='utf-8')
raise SystemExit(0 if ok else 1)
