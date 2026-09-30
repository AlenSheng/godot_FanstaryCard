import hashlib,json,os,pathlib,subprocess,shutil,tempfile,time,socket
repo=pathlib.Path('/workspace/godot_FanstaryCard')
root=pathlib.Path(__file__).resolve().parent
work=root/os.environ.get('PR13_TEST_ATTEMPT','development-01')
work.mkdir(exist_ok=False)
sock=pathlib.Path(tempfile.mkdtemp(prefix='pr13-ack-cycles-',dir='/tmp'))
pgdata=work/'pgdata'
commands=[]
started=False
cleaned=False
port=5432
bind_tcp=os.environ.get('PR13_PG_TEST_TRANSPORT')=='tcp'
if bind_tcp:
 with socket.socket() as probe:
  probe.bind(('127.0.0.1',0));port=probe.getsockname()[1]

def run(cmd,label,timeout=180,cwd=repo,env=None):
 t=time.monotonic()
 with (work/(label+'.log')).open('wb') as log:
  try:
   p=subprocess.run(cmd,cwd=cwd,env=env,stdout=log,stderr=subprocess.STDOUT,timeout=timeout)
   code=p.returncode
  except subprocess.TimeoutExpired: code=124
 commands.append(dict(command=cmd,label=label,cwd=str(cwd),exit_code=code,deadline_seconds=timeout,duration_seconds=round(time.monotonic()-t,3)))
 print(label,code,flush=True)
 return code
paths=['client/tests/pr13_ack_stop_cycles.gd','client/tests/gameplay_load_client.gd','client/state/game_store.gd','client/network/gateway.gd','server/tests/FantasyCard.Server.Tests/EndToEnd/ProcessLifecycleAckResponseLossTests.cs','server/tests/FantasyCard.Server.Tests/EndToEnd/ProcessLifecycleAckStopAndCycleTests.cs']
(work/'inputs.json').write_text(json.dumps(dict(frozen_runtime_sha='f93e32dac07608e8375e709cd357c4793bdcc41a',source_sha=subprocess.check_output(['git','rev-parse','HEAD'],cwd=repo).decode().strip(),dirty=subprocess.check_output(['git','status','--porcelain'],cwd=repo).decode().splitlines(),files={p:dict(sha256=hashlib.sha256((repo/p).read_bytes()).hexdigest(),size=(repo/p).stat().st_size) for p in paths},canonical_sha256=hashlib.sha256((repo/'docs/plans/PR13_ACCEPTANCE_DETAILS_20260930.json').read_bytes()).hexdigest()),indent=2))
try:
 for p in sorted((x for x in (repo/'server').rglob('*') if x.is_dir() and x.name in ['bin','obj']),key=lambda p:len(p.parts),reverse=True):
  if p.exists(): shutil.rmtree(p)
 assert run(['dotnet','build','FantasyCard.Server.slnx','-c','Release','-v','minimal'],'fresh-build',240,repo/'server')==0
 assert run(['initdb','-D',str(pgdata),'-U','ack_cycle_owner','--auth=trust','--no-locale','--encoding=UTF8'],'pg-init',30)==0
 assert run(['pg_ctl','-D',str(pgdata),'-l',str(work/'pg.log'),'-o',"-k "+str(sock)+" -h "+('127.0.0.1' if bind_tcp else "''")+" -p "+str(port),'-w','start'],'pg-start',30)==0
 started=True
 assert run(['createdb','-h',str(sock),'-p',str(port),'-U','ack_cycle_owner','pr13_ack_cycles'],'pg-createdb',30)==0
 env=dict(os.environ)
 env['FANTASYCARD_TEST_POSTGRES']='Host='+('127.0.0.1' if bind_tcp else str(sock))+';Port='+str(port)+';Database=pr13_ack_cycles;Username=ack_cycle_owner;Pooling=false'
 env['FANTASYCARD_PROCESS_SERVER_DLL']=str(repo/'server/src/FantasyCard.Server/bin/Release/net10.0/FantasyCard.Server.dll')
 env['FANTASYCARD_PROCESS_EVIDENCE']=str(work/'raw')
 filt=os.environ.get('PR13_TEST_FILTER','FullyQualifiedName~Real_load_runner_counts_three_games_once_and_STOP_during_ACK_never_completes')
 code=run(['dotnet','test','tests/FantasyCard.Server.Tests/FantasyCard.Server.Tests.csproj','-c','Release','--no-build','--filter',filt,'--logger','trx;LogFileName=targeted.trx','--results-directory',str(work/'results'),'-v','normal'],'targeted-tests',1500,repo/'server',env)
 print('RESULT',code,flush=True)
finally:
 if started:
  env=dict(os.environ)
  r=subprocess.run(['psql','-h',str(sock),'-p',str(port),'-U','ack_cycle_owner','-d','pr13_ack_cycles','-X','-A','-t','-c',"SELECT count(*) FROM information_schema.schemata WHERE schema_name LIKE 'fc_runtime_test_%'"],capture_output=True,env=env,timeout=15)
  (work/'schema-cleanup-check.json').write_text(json.dumps(dict(exit_code=r.returncode,remaining_owned_schemas=r.stdout.decode().strip())))
  run(['pg_ctl','-D',str(pgdata),'-m','fast','-w','stop'],'pg-stop',30)
  if pgdata.exists(): shutil.rmtree(pgdata)
 shutil.rmtree(sock)
 (work/'commands.json').write_text(json.dumps(commands,indent=2)+'\n')

raise SystemExit(code)
