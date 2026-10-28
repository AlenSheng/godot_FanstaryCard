import hashlib, json, os, pathlib, shutil, subprocess, time, datetime
ROOT=pathlib.Path(__file__).resolve().parents[1]
SRC=ROOT/'source'; E=ROOT/'evidence'; E.mkdir(exist_ok=True)
COMMANDS=[]
def run(name, argv, cwd=SRC, env=None, expected=0, timeout=600):
    start=time.monotonic(); utc=datetime.datetime.now(datetime.timezone.utc).isoformat()
    raw=E/(name+'.log')
    with raw.open('w') as f:
        f.write(json.dumps({'argv':argv,'cwd':str(cwd),'started_utc':utc})+'\n'); f.flush()
        try:
            p=subprocess.run(argv,cwd=cwd,env=env,stdout=f,stderr=subprocess.STDOUT,timeout=timeout)
            code=p.returncode
        except subprocess.TimeoutExpired: code=124
    item={'name':name,'argv':argv,'cwd':str(cwd),'started_utc':utc,'elapsed_seconds':time.monotonic()-start,'exit_code':code,'expected_exit_code':expected,'raw':raw.relative_to(ROOT).as_posix(),'input_manifest_sha256':hashlib.sha256((E/'input_manifest.json').read_bytes()).hexdigest() if (E/'input_manifest.json').exists() else None}
    COMMANDS.append(item); (E/'commands-baseline.json').write_text(json.dumps(COMMANDS,indent=2))
    print(json.dumps(item),flush=True)
    if code!=expected: raise RuntimeError(f'{name} exit {code}, expected {expected}')
    return code

tracked=subprocess.check_output(['git','-C','/workspace/godot_FanstaryCard','ls-tree','-r','--name-only','f812879e4518fd09bf22656451cb563d62940298'],text=True).splitlines()
items=[]; removed=[]
for name in tracked:
    p=SRC/name
    if any(c in {'bin','obj','validation-bin','validation-obj','.godot'} for c in p.parts): continue
    if name.startswith(('server/src/','server/tests/','client/','protocol/','config/','tools/','docs/plans/')) or name in ['GDD.md','GDD_BASE_v0.69.md','server/AGENTS.md','docs/SERVER_SPEC.md','docs/SERVER_0_TO_1_GUIDE.md']:
        items.append({'path':name,'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()})
(E/'input_manifest.json').write_text(json.dumps({'source_sha':'f812879e4518fd09bf22656451cb563d62940298','archive_source':'git archive','main_repo_status':subprocess.check_output(['git','-C','/workspace/godot_FanstaryCard','status','--porcelain=v1'],text=True),'files':items},indent=2))
for p in sorted(SRC.rglob('*'),key=lambda p:len(p.parts),reverse=True):
    if p.is_dir() and p.name in {'bin','obj','validation-bin','validation-obj','.godot'}:
        removed.append(str(p.relative_to(SRC))); shutil.rmtree(p)
(E/'removed-stale-build-directories.json').write_text(json.dumps(removed,indent=2))
run('tool-dotnet',['dotnet','--info'])
run('tool-postgres',['postgres','--version'])
run('tool-godot',[os.environ['A3GAME_GODOT_EXECUTABLE'],'--version'])
PG=ROOT/'owned-pg'; PG.mkdir(exist_ok=True)
SOCK=ROOT/'pgsocket'; SOCK.mkdir(exist_ok=True)
run('pg-init',['initdb','-D',str(PG),'-A','trust','--no-locale','--encoding=UTF8'])
run('pg-start',['pg_ctl','-D',str(PG),'-l',str(E/'postgres.log'),'-o',f"-k {SOCK} -p 55482 -c listen_addresses='' -c max_connections=160",'-w','start'])
try:
    run('pg-createdb',['createdb','-h',str(SOCK),'-p','55482','b02_acceptance'])
    env=os.environ.copy(); env['FANTASYCARD_TEST_POSTGRES']=f'Host={SOCK};Port=55482;Database=b02_acceptance;Username=agent;Pooling=false'
    run('C-BUILD',['dotnet','build','FantasyCard.Server.slnx','-c','Release'],SRC/'server')
    run('C-DOMAIN',['dotnet','test','tests/FantasyCard.Domain.Tests/FantasyCard.Domain.Tests.csproj','-c','Release','--logger','trx;LogFileName=domain.trx','--results-directory',str(E/'trx')],SRC/'server')
    run('C-SERVER',['dotnet','test','tests/FantasyCard.Server.Tests/FantasyCard.Server.Tests.csproj','-c','Release','--logger','trx;LogFileName=server.trx','--results-directory',str(E/'trx')],SRC/'server',env)
    run('C-PROTO',['python3','tools/generate_network_protocol.py','--check'])
    godotenv=os.environ.copy();godotenv.update(FANTASYCARD_SERVER_URL='http://127.0.0.1:1',FANTASYCARD_LOAD_RUN_ID='b02-isolated')
    run('godot-import',[os.environ['A3GAME_GODOT_EXECUTABLE'],'--headless','--path',str(SRC/'client'),'--editor','--import','--quit'],env=godotenv,timeout=180)
    run('C-GODOT-NUM',[os.environ['A3GAME_GODOT_EXECUTABLE'],'--headless','--path',str(SRC/'client'),'res://tests/numerical_integration.tscn'],env=godotenv,timeout=180)
finally:
    run('pg-stop',['pg_ctl','-D',str(PG),'-m','fast','-w','stop'])
