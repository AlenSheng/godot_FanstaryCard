from pathlib import Path
import json,hashlib,subprocess,importlib.util,os
b=Path(r'G:\PR13Evidence\season-balance-20261102-r1');info=json.loads((b/'f03-steam-integration-r1/source.original.json').read_bytes());work=Path(info['worktree']);out=b/'f03-steam-integration-r1'
names=subprocess.check_output(['git','-C',str(work),'ls-files','-z','--','server','protocol','config','client/data']).decode().split('\0');pin={n:hashlib.sha256((work/n).read_bytes()).hexdigest() for n in names if n and (work/n).is_file()};(out/'source-pin.original.json').write_text(json.dumps(pin,indent=2)+'\n')
spec=importlib.util.spec_from_file_location('guard',Path.cwd()/'client/tests/fixture_runtime.py');guard=importlib.util.module_from_spec(spec);spec.loader.exec_module(guard)
cmd=['dotnet','build',str(work/'server/FantasyCard.Server.slnx'),'-c','Release','--artifacts-path',str(out/'build'),'-m:1','-p:UseSharedCompilation=false','--verbosity','minimal']
r=guard.guarded_run(cmd,env=dict(os.environ,DOTNET_CLI_TELEMETRY_OPTOUT='1',DOTNET_NOLOGO='1',DOTNET_CLI_UI_LANGUAGE='en',FANTASYCARD_TEST_POSTGRES=''),timeout=300,wait_seconds=30)
(out/'solution-build.original.log').write_text(r.stdout+r.stderr,encoding='utf-8');proof={'exit':r.returncode,'source_unchanged':all(hashlib.sha256((work/n).read_bytes()).hexdigest()==h for n,h in pin.items()),'new_gameplay_cases':0,'actual_remote_branch_updated':False}
(out/'build-result.json').write_text(json.dumps(proof,indent=2)+'\n');print((r.stdout+r.stderr)[-3300:]);print(json.dumps(proof));assert r.returncode==0 and proof['source_unchanged']
