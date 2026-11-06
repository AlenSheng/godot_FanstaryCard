from pathlib import Path
import hashlib,json,shutil,importlib.util,os
repo=Path.cwd();b=Path(r'G:\PR13Evidence\season-balance-20261102-r1');out=b/'local-config-r13';assert not out.exists();out.mkdir()
source=b/'workbook/outputs/01a1737c-c1cf-7342-92cd-7cea01eded79/refresh-prices-r1';proof=json.loads((source/'preservation-proof.json').read_text(encoding='utf-8'))
p=repo/'config/FantasyCard_Config.xlsx';assert hashlib.sha256(p.read_bytes()).hexdigest()==proof['before_sha256'];assert hashlib.sha256((source/p.name).read_bytes()).hexdigest()==proof['after_sha256']
archive=repo/'server/config/archive/season-v1-config-12';assert not archive.exists();archive.mkdir()
for n in ['fantasycard.config.bytes','fantasycard.config.sha256','fantasycard.config.version.txt']:shutil.copy2(repo/'server/config/generated'/n,archive/n)
assert (archive/'fantasycard.config.version.txt').read_text(encoding='utf-8').strip()=='season-v1-config-12'
shutil.copy2(source/p.name,p)
spec=importlib.util.spec_from_file_location('fixture_runtime',repo/'client/tests/fixture_runtime.py');r=importlib.util.module_from_spec(spec);spec.loader.exec_module(r)
cmd=['dotnet',str(b/'local-archive-pg-r2/build/bin/FantasyCard.ConfigExporter/debug/FantasyCard.ConfigExporter.dll'),'--input',str(p),'--version','season-v1-config-13','--server-output',str(repo/'server/config/generated'),'--client-output',str(repo/'client/data/generated')]
v=r.guarded_run(cmd,env=dict(os.environ,DOTNET_CLI_UI_LANGUAGE='en',DOTNET_NOLOGO='1'),timeout=120);(out/'export.original.log').write_text(v.stdout+v.stderr,encoding='utf-8');print(v.stdout+v.stderr);assert v.returncode==0
for n in ['fantasycard.config.bytes','fantasycard.config.sha256','fantasycard.config.version.txt']:assert (repo/'server/config/generated'/n).read_bytes()==(repo/'client/data/generated'/n).read_bytes()
(out/'install.original.json').write_text(json.dumps(dict(workbook_sha256=proof['after_sha256'],previous_12_archived=True,production_activated=False,exporter_reused_from_verified_local_build=True),indent=2)+'\n',encoding='utf-8')
