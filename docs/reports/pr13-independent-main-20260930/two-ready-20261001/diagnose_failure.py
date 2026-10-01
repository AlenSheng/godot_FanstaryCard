"""One bounded isolated rerun of the newly failing mandatory case; no source edits."""
import json,os,pathlib,subprocess,sys
B=pathlib.Path(__file__).resolve().parent;E=B/'evidence';data=B/'a05-pg';sock=B/'a05-socket'
sha='62772be2a1bc28affffc3d057f259c8c5ded8e37';root=B/'a05-source';dst=E/'A05-MARKRUNNING-DIAGNOSTIC';dst.mkdir()
assert (E/'a05-PG-STOP.json').exists()
assert subprocess.run(['pg_ctl','-D',str(data),'status'],capture_output=True).returncode==3
subprocess.run(['pg_ctl','-D',str(data),'-l',str(E/'a05-diagnostic-postgres.log'),'-o',f"-k {sock} -p 55531 -h '' -c max_connections=64 -c shared_buffers=32MB",'-w','start'],check=True)
os.environ.update(FANTASYCARD_TEST_POSTGRES=f'Host={sock};Port=55531;Username=agent;Database=postgres;Pooling=true;Maximum Pool Size=8',FANTASYCARD_PROCESS_SERVER_DLL=str(root/'server/src/FantasyCard.Server/bin/Release/net10.0/FantasyCard.Server.dll'),FANTASYCARD_PROCESS_SOURCE_SHA=sha,FANTASYCARD_PROCESS_EVIDENCE=str(dst))
try:
    result=subprocess.run([sys.executable,str(B/'run_command.py'),'--id','A05-MARKRUNNING-DIAGNOSTIC','--cwd',str(root/'server'),'--sha',sha,'--timeout','120','--','dotnet','test','tests/FantasyCard.Server.Tests/FantasyCard.Server.Tests.csproj','-c','Release','--no-build','--logger','trx;LogFileName=tests.trx','--results-directory',str(dst),'--filter','FullyQualifiedName~MarkRunning_commit_response_loss_retries_same_room_and_restart_restores_it'])
finally:
    query="SELECT count(*) AS owned_schemas FROM pg_namespace WHERE nspname LIKE 'fc_runtime_test_%'; SELECT count(*) AS other_connections FROM pg_stat_activity WHERE pid<>pg_backend_pid() AND backend_type='client backend';"
    with (E/'a05-diagnostic-final-readonly.log').open('w') as f:
        q=subprocess.run(['psql','-h',str(sock),'-p','55531','-U','agent','-d','postgres','-c',query],stdout=f,stderr=subprocess.STDOUT)
    stop=subprocess.run(['pg_ctl','-D',str(data),'-m','fast','-w','stop'])
    status=subprocess.run(['pg_ctl','-D',str(data),'status'],capture_output=True,text=True)
    (E/'a05-diagnostic-PG-STOP.json').write_text(json.dumps({'final_readonly_exit':q.returncode,'stop_exit':stop.returncode,'status_after_stop_exit':status.returncode,'query':query,'scope':'Only prior owned isolated a05 PG, no production/source/assertion mutation'},indent=2)+'\n')
    assert q.returncode==stop.returncode==0 and status.returncode==3
print(json.dumps({'diagnostic_test_exit':result.returncode,'not_a_replacement_for_unfiltered_suite':True}))
