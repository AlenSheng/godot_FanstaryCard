from pathlib import Path
import importlib.util,os,json,hashlib,shutil
repo=Path.cwd();base=Path(r'G:\PR13Evidence\season-balance-20261102-r1');out=base/'local-refresh-config-build-r1';assert not out.exists();out.mkdir()
files=['config/FantasyCard_Config.xlsx','client/data/catalog.json']
for folder in ['server/config/generated','client/data/generated','server/config/archive/season-v1-config-4','server/config/archive/season-v1-config-5','server/config/archive/season-v1-config-6','server/config/archive/season-v1-config-7','server/config/archive/season-v1-config-8','server/config/archive/season-v1-config-9','server/config/archive/season-v1-config-10','server/config/archive/season-v1-config-11','server/config/archive/season-v1-config-12']:
 for n in ['fantasycard.config.bytes','fantasycard.config.sha256','fantasycard.config.version.txt']:files.append(folder+'/'+n)
for n in files:
 p=out/n;p.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(repo/n,p);assert p.read_bytes()==(repo/n).read_bytes()
pins={p.relative_to(repo).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in (repo/'server').rglob('*') if p.is_file() and p.suffix in ['.cs','.sql','.csproj','.props','.targets','.bytes','.proto'] and not any(x in p.parts for x in ['bin','obj','.artifacts'])}
pins.update({n:hashlib.sha256((repo/n).read_bytes()).hexdigest() for n in files});(out/'source-pin.json').write_text(json.dumps(pins,indent=2)+'\n')
spec=importlib.util.spec_from_file_location('fixture_runtime',repo/'client/tests/fixture_runtime.py');r=importlib.util.module_from_spec(spec);spec.loader.exec_module(r)
cmd=['dotnet','build',str(repo/'server/tests/FantasyCard.Server.Tests/FantasyCard.Server.Tests.csproj'),'--artifacts-path',str(out/'build'),'--verbosity','minimal','-m:1','-p:UseSharedCompilation=false']
result=r.guarded_run(cmd,env=dict(os.environ,DOTNET_CLI_UI_LANGUAGE='en',DOTNET_CLI_TELEMETRY_OPTOUT='1',DOTNET_NOLOGO='1'),timeout=240)
text=result.stdout+result.stderr;(out/'build.original.log').write_text(text,encoding='utf-8')
proof=dict(exit=result.returncode,source_unchanged=all(hashlib.sha256((repo/n).read_bytes()).hexdigest()==h for n,h in pins.items()),command=cmd,database_used=False,tests_executed=0)
(out/'result.json').write_text(json.dumps(proof,indent=2)+'\n',encoding='utf-8');print(text[-8000:]);print(json.dumps(proof));assert result.returncode==0 and proof['source_unchanged']
