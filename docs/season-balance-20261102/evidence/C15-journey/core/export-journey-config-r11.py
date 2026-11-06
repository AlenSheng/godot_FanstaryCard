from pathlib import Path
import json,hashlib,shutil,importlib.util,os
repo=Path.cwd();b=Path(r'G:\PR13Evidence\season-balance-20261102-r1');out=b/'local-config-r11';assert not out.exists();out.mkdir()
folder=b/'workbook/outputs/01a1737c-c1cf-7342-92cd-7cea01eded79/season-journey-r2';proof=json.loads((folder/'preservation-proof.json').read_text(encoding='utf-8'))
target=repo/'config/FantasyCard_Config.xlsx';assert hashlib.sha256(target.read_bytes()).hexdigest()==proof['before_sha256'];assert hashlib.sha256((folder/'FantasyCard_Config.xlsx').read_bytes()).hexdigest()==proof['after_sha256']
archive=repo/'server/config/archive/season-v1-config-10';assert not archive.exists();archive.mkdir()
for n in ['fantasycard.config.bytes','fantasycard.config.sha256','fantasycard.config.version.txt']:shutil.copy2(repo/'server/config/generated'/n,archive/n)
assert (archive/'fantasycard.config.version.txt').read_text(encoding='utf-8').strip()=='season-v1-config-10';shutil.copy2(folder/'FantasyCard_Config.xlsx',target)
(out/'install.original.json').write_text(json.dumps({'previous_sha256':proof['before_sha256'],'new_workbook_sha256':proof['after_sha256'],'original_sheets_preserved':31,'previous_config10_archived':True,'production_activated':False},indent=2)+'\n')
spec=importlib.util.spec_from_file_location('fixture_runtime',repo/'client/tests/fixture_runtime.py');rt=importlib.util.module_from_spec(spec);spec.loader.exec_module(rt)
cmd=['dotnet',str(b/'local-journey-server-build-r1/build/bin/FantasyCard.ConfigExporter/debug/FantasyCard.ConfigExporter.dll'),'--input',str(target),'--version','season-v1-config-11','--server-output',str(repo/'server/config/generated'),'--client-output',str(repo/'client/data/generated')]
r=rt.guarded_run(cmd,env=dict(os.environ,DOTNET_CLI_UI_LANGUAGE='en',DOTNET_NOLOGO='1'),timeout=120);(out/'export.original.log').write_text(r.stdout+r.stderr,encoding='utf-8');print(r.stdout+r.stderr);assert r.returncode==0
for n in ['fantasycard.config.bytes','fantasycard.config.sha256','fantasycard.config.version.txt']:assert (repo/'server/config/generated'/n).read_bytes()==(repo/'client/data/generated'/n).read_bytes()
