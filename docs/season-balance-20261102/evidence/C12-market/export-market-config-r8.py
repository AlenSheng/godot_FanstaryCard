from pathlib import Path
import importlib.util,os,json,shutil,hashlib
repo=Path.cwd();base=Path(r'G:\PR13Evidence\season-balance-20261102-r1');out=base/'local-config-r8';assert not out.exists();out.mkdir()
archive=repo/'server/config/archive/season-v1-config-7';assert not archive.exists();archive.mkdir()
for name in ['fantasycard.config.bytes','fantasycard.config.sha256','fantasycard.config.version.txt']:shutil.copyfile(repo/'server/config/generated'/name,archive/name)
spec=importlib.util.spec_from_file_location('fixture_runtime',repo/'client/tests/fixture_runtime.py');rt=importlib.util.module_from_spec(spec);spec.loader.exec_module(rt)
cmd=['dotnet',str(base/'local-market-server-r1/build/bin/FantasyCard.ConfigExporter/debug/FantasyCard.ConfigExporter.dll'),'--input',str(repo/'config/FantasyCard_Config.xlsx'),'--version','season-v1-config-8','--server-output',str(repo/'server/config/generated'),'--client-output',str(repo/'client/data/generated')]
r=rt.guarded_run(cmd,env=dict(os.environ,DOTNET_CLI_UI_LANGUAGE='en',DOTNET_NOLOGO='1'),timeout=120);(out/'export.original.log').write_text(r.stdout+r.stderr,encoding='utf-8');print(r.stdout+r.stderr);assert r.returncode==0
for n in ['fantasycard.config.bytes','fantasycard.config.sha256','fantasycard.config.version.txt']:assert (repo/'server/config/generated'/n).read_bytes()==(repo/'client/data/generated'/n).read_bytes()
print('binary_sha256',hashlib.sha256((repo/'server/config/generated/fantasycard.config.bytes').read_bytes()).hexdigest())
