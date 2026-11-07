from pathlib import Path
import hashlib,importlib.util,json,os,subprocess,sys,datetime

b=Path(__file__).parent;repo=Path.cwd();platform=sys.argv[1];assert platform in ('main',)
out=b/'f03-main-integration-r1';assert out.exists() and not (out/'build-started.original.json').exists()
info=json.loads((out/'source.original.json').read_bytes());work=b/f'work/f03-{platform}-integration-r1'
assert subprocess.check_output(['git','-C',str(work),'rev-parse','HEAD']).decode().strip()==info['head']
assert not subprocess.check_output(['git','-C',str(work),'status','--porcelain'])
private=Path(r'G:\PR13Evidence\private\season-balance-20261102-f03-google-r1')/f'f03-{platform}-current-r1'
assert not private.exists();private.mkdir()
names=subprocess.check_output(['git','-C',str(work),'ls-files','-z','--','server','protocol','config','client/data','tools/generate_network_protocol.py','tools/generate_client_schema.py']).decode().split('\0')
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
pin={name:sha(work/name) for name in names if name and (work/name).is_file()}
(out/'source-pin.original.json').write_text(json.dumps(pin,indent=2)+'\n')
command=['dotnet','build',str(work/'server/FantasyCard.Server.slnx'),'-c','Release','--artifacts-path',str(private),'-m:1','-p:UseSharedCompilation=false','--verbosity','minimal']
(out/'build-started.original.json').write_text(json.dumps(dict(parent_pid=os.getpid(),at_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),command=command,reserve_GiB=2,startup_GiB=1,new_gameplay_cases=0),indent=2)+'\n')
spec=importlib.util.spec_from_file_location('guard',repo/'client/tests/fixture_runtime.py');guard=importlib.util.module_from_spec(spec);spec.loader.exec_module(guard)
env=dict(os.environ)
for k in list(env):
    if k.startswith('FANTASYCARD_'):env[k]=''
env.update(DOTNET_CLI_TELEMETRY_OPTOUT='1',DOTNET_NOLOGO='1',DOTNET_CLI_UI_LANGUAGE='en')
r=guard.guarded_run(command,env=env,timeout=300,wait_seconds=30)
(out/'solution-build.original.log').write_text(r.stdout+r.stderr,encoding='utf-8')
proof=dict(exit=r.returncode,source_entries=len(pin),source_unchanged=all(sha(work/name)==h for name,h in pin.items()),head=info['head'],private_build=str(private),new_gameplay_cases=0,actual_remote_target_updated=False,production_updated=False)
(out/'build-result.json').write_text(json.dumps(proof,indent=2)+'\n');print((r.stdout+r.stderr)[-1700:]);print(json.dumps(proof))
assert r.returncode==0 and proof['source_unchanged']

