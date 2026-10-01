import os, pathlib, subprocess, sys
b = pathlib.Path(__file__).resolve().parent
p = b/'b02'
rec = b/'run_command.py'
sha = 'f812879e4518fd09bf22656451cb563d62940298'
def run(name,cwd,args,timeout=900):
    return subprocess.run([sys.executable,str(rec),'--id',name,'--cwd',str(cwd),'--sha',sha,'--timeout',str(timeout),'--',*args],check=True)
subprocess.run(['pg_ctl','-D',str(p/'owned-pg'),'-l',str(p/'evidence/postgres-suites.log'),'-o',f"-k {p}/pgsocket -p 55482 -h '' -c max_connections=160",'-w','start'],check=True)
os.environ['FANTASYCARD_TEST_POSTGRES']=f'Host={p}/pgsocket;Port=55482;Database=postgres;Username=agent;Pooling=true;Maximum Pool Size=8'
os.environ['FANTASYCARD_PROCESS_SERVER_DLL']=str(p/'source/server/src/FantasyCard.Server/bin/Release/net10.0/FantasyCard.Server.dll')
os.environ['FANTASYCARD_PROCESS_EVIDENCE']=str(p/'evidence/process')
try:
    run('B02-BUILD',p/'source/server',['dotnet','build','FantasyCard.Server.slnx','-c','Release'],300)
    run('B02-DOMAIN',p/'source/server',['dotnet','test','tests/FantasyCard.Domain.Tests/FantasyCard.Domain.Tests.csproj','-c','Release','--no-build','--logger','trx;LogFileName=domain.trx','--results-directory',str(p/'evidence/trx')])
    run('B02-SERVER',p/'source/server',['dotnet','test','tests/FantasyCard.Server.Tests/FantasyCard.Server.Tests.csproj','-c','Release','--no-build','--logger','trx;LogFileName=server.trx','--results-directory',str(p/'evidence/trx')],1500)
    run('B02-PROTO',p/'source',['python','tools/generate_network_protocol.py','--check'])
finally:
    subprocess.run(['pg_ctl','-D',str(p/'owned-pg'),'-m','fast','-w','stop'],check=True)
