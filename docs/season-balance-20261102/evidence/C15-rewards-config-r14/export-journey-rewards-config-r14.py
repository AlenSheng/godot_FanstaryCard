from pathlib import Path
import json,hashlib,shutil,importlib.util,os,sys
sys.stdout.reconfigure(encoding='utf-8')
repo=Path.cwd();b=Path(r'G:\PR13Evidence\season-balance-20261102-r1');out=b/'local-config-r14';assert not out.exists();out.mkdir()
source=b/'workbook/outputs/01a1737c-c1cf-7342-92cd-7cea01eded79/season-journey-rewards-r1';proof=json.loads((source/'preservation-proof.json').read_text('utf-8'))
assert hashlib.sha256((repo/'config/FantasyCard_Config.xlsx').read_bytes()).hexdigest()==proof['before_sha256']
assert hashlib.sha256((source/'FantasyCard_Config.xlsx').read_bytes()).hexdigest()==proof['after_sha256']
spec=importlib.util.spec_from_file_location('fixture_runtime',repo/'client/tests/fixture_runtime.py');guard=importlib.util.module_from_spec(spec);spec.loader.exec_module(guard)
exporter=b/'journey-reward-config-r3/build/bin/FantasyCard.ConfigExporter/debug/FantasyCard.ConfigExporter.dll'
server=out/'server/config/generated';client=out/'client/data/generated'
cmd=['dotnet',str(exporter),'--input',str(source/'FantasyCard_Config.xlsx'),'--version','season-v1-config-14','--server-output',str(server),'--client-output',str(client)]
r=guard.guarded_run(cmd,env=dict(os.environ,DOTNET_CLI_UI_LANGUAGE='en',DOTNET_NOLOGO='1'),timeout=120)
(out/'export.original.log').write_text(r.stdout+r.stderr,encoding='utf-8');print(r.stdout+r.stderr,flush=True);assert r.returncode==0
for n in ['fantasycard.config.bytes','fantasycard.config.sha256','fantasycard.config.version.txt']:assert (server/n).read_bytes()==(client/n).read_bytes()
for code in ['en','zh-CN']:
    target=out/'client/data/locales'/f'{code}.json';target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(repo/'client/data/locales'/f'{code}.json',target)
spec=importlib.util.spec_from_file_location('original_client_exporter',repo/'tools/export_client_catalog.py');catalog=importlib.util.module_from_spec(spec);spec.loader.exec_module(catalog);catalog.ROOT=out;catalog.main()
old=catalog.fields((repo/'server/config/generated/fantasycard.config.bytes').read_bytes());new=catalog.fields((server/'fantasycard.config.bytes').read_bytes())
def bodies(bundle):return {catalog.fields(t)[1][0].decode():t for t in bundle[3]}
oldtables=bodies(old);newtables=bodies(new);assert len(oldtables)==35 and len(newtables)==37
assert all(newtables[n]==data for n,data in oldtables.items());assert set(newtables)-set(oldtables)=={'SeasonJourneyRewards','SeasonCosmetics'}
assert sum(len(catalog.fields(t).get(3,[])) for t in newtables.values())==1825
a=json.loads((repo/'client/data/catalog.json').read_text('utf-8'));z=json.loads((out/'client/data/catalog.json').read_text('utf-8'));assert len(a['tables'])==30 and len(z['tables'])==32
assert all(z['tables'][n]==rows for n,rows in a['tables'].items());assert set(z['tables'])-set(a['tables'])=={'SeasonJourneyRewards','SeasonCosmetics'}
assert len(z['tables']['SeasonJourneyRewards'])==30 and len(z['tables']['SeasonCosmetics'])==10
assert (out/'client/data/card_descriptions.json').read_bytes()==(repo/'client/data/card_descriptions.json').read_bytes()
assert new[1][0].decode()=='season-v1-config-14' and (server/'fantasycard.config.sha256').read_text('utf-8').strip()==new[2][0].hex()
result=dict(status='candidate14_export_verified_not_installed',version=new[1][0].decode(),content_hash=new[2][0].hex(),binary_sha256=hashlib.sha256((server/'fantasycard.config.bytes').read_bytes()).hexdigest(),workbook_sha256=proof['after_sha256'],tables=37,rows=1825,client_public_tables=32,original_35_table_messages_byte_identical=True,original_30_public_tables_equal=True,legacy_card_descriptions_byte_identical=True,new_reward_levels=30,new_cosmetics=10,exporter_path=str(exporter),exporter_sha256=hashlib.sha256(exporter.read_bytes()).hexdigest(),client_exporter_sha256=hashlib.sha256((repo/'tools/export_client_catalog.py').read_bytes()).hexdigest(),formal_installed=False,production_activated=False)
(out/'result.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8');print(json.dumps(result))
