"""Original B02 Pooling=false profile on separately owned Unix-only PG."""
import os,pathlib,subprocess,sys
B=pathlib.Path(__file__).resolve().parent
P=B/'b02';pg=P/'original-profile-pg';sock=P/'original-profile-socket'
sock.mkdir()
with (P/'evidence/original-initdb.log').open('w') as f:
    subprocess.run(['initdb','-D',str(pg),'-A','trust','--no-locale','--encoding=UTF8'],stdout=f,stderr=subprocess.STDOUT,check=True)
subprocess.run(['pg_ctl','-D',str(pg),'-l',str(P/'evidence/original-postgres.log'),'-o',f"-k {sock} -p 55483 -h '' -c max_connections=160",'-w','start'],check=True)
try:
    subprocess.run(['createdb','-h',str(sock),'-p','55483','b02_acceptance'],check=True)
    os.environ['FANTASYCARD_TEST_POSTGRES']=f'Host={sock};Port=55483;Database=b02_acceptance;Username=agent;Pooling=false'
    os.environ['FANTASYCARD_PROCESS_SERVER_DLL']=str(P/'source/server/src/FantasyCard.Server/bin/Release/net10.0/FantasyCard.Server.dll')
    os.environ['FANTASYCARD_PROCESS_EVIDENCE']=str(P/'evidence/process-original')
    result=subprocess.run([sys.executable,str(B/'run_command.py'),'--id','B02-SERVER-ORIGINAL','--cwd',str(P/'source/server'),'--sha','f812879e4518fd09bf22656451cb563d62940298','--timeout','1500','--','dotnet','test','tests/FantasyCard.Server.Tests/FantasyCard.Server.Tests.csproj','-c','Release','--no-build','--logger','trx;LogFileName=server-original.trx','--results-directory',str(P/'evidence/trx-original')])
finally:
    subprocess.run(['pg_ctl','-D',str(pg),'-m','fast','-w','stop'],check=True)
raise SystemExit(result.returncode)
