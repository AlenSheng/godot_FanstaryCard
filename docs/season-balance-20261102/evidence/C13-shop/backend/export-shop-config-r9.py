from pathlib import Path
import shutil,hashlib,json,importlib.util,os
repo=Path.cwd();base=Path(r'G:\PR13Evidence\season-balance-20261102-r1');out=base/'local-config-r9';assert not out.exists();out.mkdir()
proof=json.loads((repo/'docs/season-balance-20261102/evidence/C13-shop/workbook-draft/preservation-proof.json').read_text(encoding='utf-8'))
source=repo/'docs/season-balance-20261102/evidence/C13-shop/workbook-draft/FantasyCard_Config.xlsx';target=repo/'config/FantasyCard_Config.xlsx'
assert hashlib.sha256(target.read_bytes()).hexdigest()==proof['before_sha256'];assert hashlib.sha256(source.read_bytes()).hexdigest()==proof['after_sha256'];archive=repo/'server/config/archive/season-v1-config-8';assert not archive.exists();archive.mkdir()
for name in ['fantasycard.config.bytes','fantasycard.config.sha256','fantasycard.config.version.txt']:shutil.copy2(repo/'server/config/generated'/name,archive/name)
assert (archive/'fantasycard.config.version.txt').read_text(encoding='utf-8').strip()=='season-v1-config-8'
shutil.copy2(source,target);(out/'install.original.json').write_text(json.dumps({'before_sha256':proof['before_sha256'],'after_sha256':proof['after_sha256'],'previous_binary_archived':True,'source':'verified C13 workbook draft','production_activated':False},indent=2)+'\n')
spec=importlib.util.spec_from_file_location('fixture_runtime',repo/'client/tests/fixture_runtime.py');rt=importlib.util.module_from_spec(spec);spec.loader.exec_module(rt)
cmd=['dotnet',str(base/'local-shop-copies-server-r1/build/bin/FantasyCard.ConfigExporter/debug/FantasyCard.ConfigExporter.dll'),'--input',str(target),'--version','season-v1-config-9','--server-output',str(repo/'server/config/generated'),'--client-output',str(repo/'client/data/generated')]
r=rt.guarded_run(cmd,env=dict(os.environ,DOTNET_CLI_UI_LANGUAGE='en',DOTNET_NOLOGO='1'),timeout=120);(out/'export.original.log').write_text(r.stdout+r.stderr,encoding='utf-8');print(r.stdout+r.stderr);assert r.returncode==0
for name in ['fantasycard.config.bytes','fantasycard.config.sha256','fantasycard.config.version.txt']:assert (repo/'server/config/generated'/name).read_bytes()==(repo/'client/data/generated'/name).read_bytes()
print('Published matching candidate9 binaries without production activation')
