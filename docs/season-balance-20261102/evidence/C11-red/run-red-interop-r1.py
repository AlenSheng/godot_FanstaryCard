from pathlib import Path
import importlib.util,os,json,hashlib,sys
repo=Path.cwd();b=Path(r'G:\PR13Evidence\season-balance-20261102-r1');w=b/'red-interop-r1'
spec=importlib.util.spec_from_file_location('fixture_runtime',repo/'client/tests/fixture_runtime.py');rt=importlib.util.module_from_spec(spec);spec.loader.exec_module(rt)
commands=[['dotnet','build',str(w/'Interop.csproj'),'--artifacts-path',str(w/'build'),'--verbosity','minimal','-m:1','-p:UseSharedCompilation=false'],['dotnet',str(w/'build/bin/Interop/debug/Interop.dll'),str(w)]]
for index,cmd in enumerate(commands):
 result=rt.guarded_run(cmd,env=dict(os.environ,DOTNET_CLI_UI_LANGUAGE='en',DOTNET_NOLOGO='1'),timeout=120);text=result.stdout+result.stderr;(w/('server-'+str(index)+'.original.log')).write_text(text,encoding='utf-8');print(text);assert result.returncode==0
(w/'server-assembly-pin.json').write_text(json.dumps({'contracts_sha256':hashlib.sha256((b/'local-red-server-r1/build/bin/FantasyCard.Contracts/debug/FantasyCard.Contracts.dll').read_bytes()).hexdigest(),'production_used':False},indent=2)+'\n')
