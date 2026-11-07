from pathlib import Path
import importlib.util,os,json,hashlib,shutil
repo=Path.cwd();base=Path(r'G:\PR13Evidence\season-balance-20261102-r1');out=base/'local-theme-pilot-r3';assert not out.exists();out.mkdir()
files=['config/FantasyCard_Config.xlsx','client/data/catalog.json']
for folder in ['server/config/generated','client/data/generated','server/config/archive/season-v1-config-4','server/config/archive/season-v1-config-5','server/config/archive/season-v1-config-6','server/config/archive/season-v1-config-7','server/config/archive/season-v1-config-8','server/config/archive/season-v1-config-9','server/config/archive/season-v1-config-10','server/config/archive/season-v1-config-11']:
 for n in ['fantasycard.config.bytes','fantasycard.config.sha256','fantasycard.config.version.txt']:files.append(folder+'/'+n)
for n in files:
 p=out/n;p.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(repo/n,p);assert p.read_bytes()==(repo/n).read_bytes()
pins={p.relative_to(repo).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in (repo/'server').rglob('*') if p.is_file() and p.suffix in ['.cs','.sql','.csproj','.props','.targets','.bytes','.proto'] and not any(x in p.parts for x in ['bin','obj','.artifacts'])}
pins.update({n:hashlib.sha256((repo/n).read_bytes()).hexdigest() for n in files});(out/'source-pin.json').write_text(json.dumps(pins,indent=2)+'\n')
spec=importlib.util.spec_from_file_location('fixture_runtime',repo/'client/tests/fixture_runtime.py');r=importlib.util.module_from_spec(spec);spec.loader.exec_module(r)
cmd=['dotnet','test',str(repo/'server/tests/FantasyCard.Server.Tests/FantasyCard.Server.Tests.csproj'),'--artifacts-path',str(out/'build'),'--filter','FullyQualifiedName~SeasonThemeComparisonTests','--logger','trx;LogFileName=bot-domain.trx','--results-directory',str(out/'results'),'--verbosity','minimal','-m:1','-p:UseSharedCompilation=false']
print('Running C16 compiler and actual room recovery controls; no database or game route queue',flush=True)
try:result=r.guarded_run(cmd,env=dict(os.environ,DOTNET_CLI_UI_LANGUAGE='en',FANTASYCARD_RUN_THEME_COMPARISON='1',FANTASYCARD_THEME_COMPARISON_SEEDS='73',FANTASYCARD_THEME_COMPARISON_DIR=str(out/'observations'),DOTNET_CLI_TELEMETRY_OPTOUT='1',DOTNET_NOLOGO='1'),timeout=240)
except Exception as e:
 data=getattr(e,'output','') or '';data=data.decode('utf-8',errors='replace') if isinstance(data,bytes) else data;(out/'interrupted.original.log').write_text(data,encoding='utf-8');raise
text=result.stdout+result.stderr;(out/'test.original.log').write_text(text,encoding='utf-8');proof={'exit':result.returncode,'B05_not_run':True,'production_database_used':False,'actual_gameplay_routes':0,'command':cmd,'source_unchanged':all(hashlib.sha256((repo/n).read_bytes()).hexdigest()==h for n,h in pins.items())};(out/'result.json').write_text(json.dumps(proof,indent=2)+'\n');print(text[-10000:]);print(json.dumps(proof));assert result.returncode==0 and proof['source_unchanged']
