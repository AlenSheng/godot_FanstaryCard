"""Independent owned Unix PG replays; no runtime/assertion/source adaptation."""
import os,pathlib,subprocess,sys,json
B=pathlib.Path(__file__).resolve().parent;E=B/'evidence';E.mkdir()
sha05='62772be2a1bc28affffc3d057f259c8c5ded8e37';sha02='dfb3f88a73efd85cc4ed12b8d49038bebbb1f953';redsha='2dda41b32ba89f06d5ea722ae8b9469004940c22'
rec=B/'run_command.py';project='tests/FantasyCard.Server.Tests/FantasyCard.Server.Tests.csproj'
def run(name,root,sha,argv,allowed=(0,),timeout=1800):
    proc=subprocess.run([sys.executable,str(rec),'--id',name,'--cwd',str(root),'--sha',sha,'--timeout',str(timeout),'--',*argv])
    assert proc.returncode in allowed,(name,proc.returncode)
    return proc.returncode
def bind_source(root,sha,evidence):
    os.environ['FANTASYCARD_PROCESS_SERVER_DLL']=str(root/'server/src/FantasyCard.Server/bin/Release/net10.0/FantasyCard.Server.dll')
    os.environ['FANTASYCARD_PROCESS_SOURCE_SHA']=sha
    os.environ['FANTASYCARD_PROCESS_EVIDENCE']=str(evidence)
def build(name,source,sha):
    run(name+'-RESTORE',source/'server',sha,['dotnet','restore','FantasyCard.Server.slnx','-p:NuGetAudit=false','--source','/workspace/relicround-env/nuget'],timeout=300)
    run(name+'-BUILD',source/'server',sha,['dotnet','build','FantasyCard.Server.slnx','-c','Release','--no-restore'],timeout=300)
def test(name,source,sha,filter=None,allowed=(0,)):
    dst=E/name;dst.mkdir();bind_source(source,sha,dst)
    args=['dotnet','test',project,'-c','Release','--no-build','--logger','trx;LogFileName=tests.trx','--results-directory',str(dst)]
    if filter:args+=['--filter',filter]
    return run(name,source/'server',sha,args,allowed=allowed)
def pg(name,port):
    data=B/(name+'-pg');sock=B/(name+'-socket');sock.mkdir(mode=0o700)
    with (E/(name+'-initdb.log')).open('w') as f:
        subprocess.run(['initdb','-D',str(data),'-U','agent','--auth-local=trust','--auth-host=reject','--no-locale','--encoding=UTF8'],stdout=f,stderr=subprocess.STDOUT,check=True)
    subprocess.run(['pg_ctl','-D',str(data),'-l',str(E/(name+'-postgres.log')),'-o',f"-k {sock} -p {port} -h '' -c max_connections=64 -c shared_buffers=32MB",'-w','start'],check=True)
    os.environ['FANTASYCARD_TEST_POSTGRES']=f'Host={sock};Port={port};Username=agent;Database=postgres;Pooling=true;Maximum Pool Size=8'
    return data,sock
def finish(name,data,sock,port):
    query="SELECT count(*) AS owned_schemas FROM pg_namespace WHERE nspname LIKE 'fc_runtime_test_%'; SELECT count(*) AS other_connections FROM pg_stat_activity WHERE pid<>pg_backend_pid() AND backend_type='client backend';"
    with (E/(name+'-final-readonly.log')).open('w') as f:
        r=subprocess.run(['psql','-h',str(sock),'-p',str(port),'-U','agent','-d','postgres','-c',query],stdout=f,stderr=subprocess.STDOUT)
    subprocess.run(['pg_ctl','-D',str(data),'-m','fast','-w','stop'],check=True)
    status=subprocess.run(['pg_ctl','-D',str(data),'status'],capture_output=True,text=True)
    assert r.returncode==0 and status.returncode==3,(name,r.returncode,status.returncode)
    (E/(name+'-PG-STOP.json')).write_text(json.dumps({'data':str(data),'socket':str(sock),'port':port,'final_readonly_exit':r.returncode,'stop_exit':0,'status_after_stop_exit':status.returncode,'status_output':status.stdout,'data_retained_for_local_audit':True},indent=2)+'\n')
red=B/'red-source';a05=B/'a05-source';load=B/'load02-source'
build('RED',red,redsha);build('A05',a05,sha05)
data,sock=pg('a05',55531)
try:
    test('A05-RED',red,redsha,'FullyQualifiedName~Frozen_f812_actual_poll_return_during_ACK_must_not_restore_completed_receipt',allowed=(1,))
    test('A05-SERVER299',a05,sha05,allowed=(0,1))
finally:finish('a05',data,sock,55531)
build('LOAD02',load,sha02)
data,sock=pg('load02',55532)
try:
    test('LOAD02-FOCUSED',load,sha02,'FullyQualifiedName~Real_LOAD02_timeout_STOP_preserves_original_business_truth',allowed=(0,1))
    test('LOAD02-SERVER302',load,sha02,allowed=(0,1))
    run('LOAD02-PY122',load,sha02,['python','-m','unittest','discover','-s','tools/tests','-v'],allowed=(0,1))
finally:finish('load02',data,sock,55532)
print('Independent bounded replay driver complete. Interpret target assertions and raw; counts do not auto-sign Accepted.')
