import pathlib, subprocess, os, json, time, datetime, hashlib, sys, uuid, shutil
ROOT=pathlib.Path(__file__).resolve().parents[1];E=ROOT/'evidence';commands=[]
def run(name,argv,env=None,timeout=180):
    stamp=datetime.datetime.now(datetime.timezone.utc).isoformat();t=time.monotonic();raw=E/(name+'.log')
    with raw.open('w') as f:
        f.write(json.dumps({'argv':argv,'cwd':str(ROOT),'started_utc':stamp})+'\n');f.flush()
        try:r=subprocess.run(argv,cwd=ROOT,env=env,stdout=f,stderr=subprocess.STDOUT,timeout=timeout);code=r.returncode
        except subprocess.TimeoutExpired:code=124
    item={'name':name,'argv':argv,'cwd':str(ROOT),'started_utc':stamp,'elapsed_seconds':time.monotonic()-t,'exit_code':code,'expected_exit_code':0,'raw':str(raw.relative_to(ROOT)),'input_manifest_sha256':hashlib.sha256((E/'input_manifest.json').read_bytes()).hexdigest(),'harness_source_hashes':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in (ROOT/'harness').glob('*') if p.is_file()},'env_nonsecret':{k:env[k] for k in ['FANTASYCARD_SERVER_URL','FANTASYCARD_LOAD_RUN_ID','FANTASYCARD_TEST_POSTGRES','B02_EXACT_EVIDENCE','B02_GODOT_OUTPUT'] if env and k in env}}
    commands.append(item);(E/('commands-godot-final.json' if '--godot-only' in sys.argv else 'commands-exact-final.json')).write_text(json.dumps(commands,indent=2));print(json.dumps(item),flush=True)
    if code:raise RuntimeError(name+' exit '+str(code))
database=os.environ.get('B02_DATABASE','b02_exact_'+uuid.uuid4().hex[:12])
env=os.environ.copy();env['FANTASYCARD_TEST_POSTGRES']=f'Host={ROOT}/pgsocket;Port=55482;Database={database};Username=agent;Pooling=false'
env.update(FANTASYCARD_SERVER_URL='http://127.0.0.1:1',FANTASYCARD_LOAD_RUN_ID='b02-isolated',XDG_DATA_HOME=str(ROOT/'godot-userdata'),B02_EXACT_EVIDENCE=str(E/'exact'),B02_GODOT_OUTPUT=str(E/'exact-godot.json'))
if '--godot-only' not in sys.argv:
    run('pg-exact-start',['pg_ctl','-D',str(ROOT/'owned-pg'),'-l',str(E/'postgres-exact.log'),'-o',f"-k {ROOT}/pgsocket -p 55482 -c listen_addresses='' -c max_connections=160",'-w','start'])
    run('pg-exact-createdb',['createdb','-h',str(ROOT/'pgsocket'),'-p','55482',database])
    if (E/'exact').exists():
        archive=E/('exact-prior-'+uuid.uuid4().hex[:12]);shutil.move(str(E/'exact'),archive)
try:
    if '--godot-only' not in sys.argv:
        run('B02-exact-csharp-final',['dotnet','run','--project',str(ROOT/'harness/ExactCases.csproj'),'-c','Release'],env)
    run('B02-exact-godot',[env['A3GAME_GODOT_EXECUTABLE'],'--headless','--path',str(ROOT/'source/client'),'--script',str(ROOT/'harness/exact_godot.gd')],env)
    run('C-GODOT-NUM-isolated',[env['A3GAME_GODOT_EXECUTABLE'],'--headless','--path',str(ROOT/'source/client'),'res://tests/numerical_integration.tscn'],env)
    run('C-GODOT-support',[env['A3GAME_GODOT_EXECUTABLE'],'--headless','--path',str(ROOT/'source/client'),'--script','res://tests/run_play_retry.gd'],env)
finally:
    if '--godot-only' not in sys.argv:
        run('pg-exact-stop',['pg_ctl','-D',str(ROOT/'owned-pg'),'-m','fast','-w','stop'])
