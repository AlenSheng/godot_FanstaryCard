"""Unchanged seven-file canonical and nine-file causal assemblies; red retained."""
import os,pathlib,subprocess,sys,json
B=pathlib.Path(__file__).resolve().parent;P=B/'a05'
pg=P/'owned-pg';sock=P/'owned-socket';sock.mkdir()
with (P/'evidence/initdb.log').open('w') as f:
    subprocess.run(['initdb','-D',str(pg),'-A','trust','--no-locale','--encoding=UTF8'],stdout=f,stderr=subprocess.STDOUT,check=True)
subprocess.run(['pg_ctl','-D',str(pg),'-l',str(P/'evidence/postgres.log'),'-o',f"-k {sock} -p 55517 -h ''",'-w','start'],check=True)
os.environ['FANTASYCARD_TEST_POSTGRES']=f'Host={sock};Port=55517;Database=postgres;Username=agent;Pooling=true;Maximum Pool Size=8'
def run(name,source,argv,allowed=(0,),timeout=1500):
    os.environ['FANTASYCARD_PROCESS_SERVER_DLL']=str(source/'server/src/FantasyCard.Server/bin/Release/net10.0/FantasyCard.Server.dll')
    os.environ['FANTASYCARD_PROCESS_EVIDENCE']=str(P/'evidence'/name)
    r=subprocess.run([sys.executable,str(B/'run_command.py'),'--id',name,'--cwd',str(source/'server'),'--sha','f812879e4518fd09bf22656451cb563d62940298','--timeout',str(timeout),'--',*argv])
    assert r.returncode in allowed,(name,r.returncode)
    return r.returncode
project='tests/FantasyCard.Server.Tests/FantasyCard.Server.Tests.csproj'
codes={}
try:
    src=P/'source'
    run('A05-BUILD',src,['dotnet','build','FantasyCard.Server.slnx','-c','Release'],timeout=300)
    codes['focused']=run('A05-FOCUSED',src,['dotnet','test',project,'-c','Release','--no-build','--filter','FullyQualifiedName~ProcessLifecycleRecoveryTests.A05_','--logger','trx;LogFileName=a05.trx','--results-directory',str(P/'evidence/A05-FOCUSED')],allowed=(0,1))
    causal=P/'source-causal'
    run('A05-CAUSAL-BUILD',causal,['dotnet','build','FantasyCard.Server.slnx','-c','Release'],timeout=300)
    codes['causal']=run('A05-CAUSAL',causal,['dotnet','test',project,'-c','Release','--no-build','--filter','FullyQualifiedName~Frozen_f812_actual_poll_return_during_ACK_must_not_restore_completed_receipt','--logger','trx;LogFileName=causal.trx','--results-directory',str(P/'evidence/A05-CAUSAL')],allowed=(1,))
    codes['full']=run('A05-SERVER295',src,['dotnet','test',project,'-c','Release','--no-build','--logger','trx;LogFileName=server295.trx','--results-directory',str(P/'evidence/A05-SERVER295')],allowed=(0,1))
    subprocess.run(['psql','-h',str(sock),'-p','55517','-d','postgres','-c',"SELECT count(*) AS owned_test_schemas FROM pg_namespace WHERE nspname LIKE 'fc_runtime_test_%'; SELECT count(*) AS other_connections FROM pg_stat_activity WHERE pid<>pg_backend_pid() AND backend_type='client backend';"],check=True)
finally:
    subprocess.run(['pg_ctl','-D',str(pg),'-m','fast','-w','stop'],check=True)
(B/'A05-EXIT-SUMMARY.json').write_text(json.dumps(codes,indent=2)+'\n')
