from pathlib import Path
import json,hashlib,shutil,importlib.util,os,sys

sys.stdout.reconfigure(encoding='utf-8');repo=Path.cwd();base=Path(__file__).parent;out=base/'local-config-r16';assert not out.exists();out.mkdir()
source=base/'d03-d0-workbook-r1/outputs/01a1737c-c1cf-7342-92cd-7cea01eded79';proof=json.loads((base/'d03-d0-workbook-r1/preservation-proof.derived.json').read_bytes())
assert hashlib.sha256((repo/'config/FantasyCard_Config.xlsx').read_bytes()).hexdigest()==proof['before_sha256'];assert hashlib.sha256((source/'FantasyCard_Config.xlsx').read_bytes()).hexdigest()==proof['after_sha256']
spec=importlib.util.spec_from_file_location('guard',repo/'client/tests/fixture_runtime.py');guard=importlib.util.module_from_spec(spec);spec.loader.exec_module(guard)
exporter=base/'d03-d0-preflight-r1/build/bin/FantasyCard.ConfigExporter/debug/FantasyCard.ConfigExporter.dll';server=out/'server/config/generated';client=out/'client/data/generated'
r=guard.guarded_run(['dotnet',str(exporter),'--input',str(source/'FantasyCard_Config.xlsx'),'--version','season-v1-config-16','--server-output',str(server),'--client-output',str(client)],env=dict(os.environ,DOTNET_CLI_UI_LANGUAGE='en',DOTNET_NOLOGO='1'),timeout=120,wait_seconds=180)
(out/'export.original.log').write_text(r.stdout+r.stderr,encoding='utf-8');print(r.stdout+r.stderr);assert r.returncode==0
for n in ['fantasycard.config.bytes','fantasycard.config.sha256','fantasycard.config.version.txt']:assert (server/n).read_bytes()==(client/n).read_bytes()
for code in ['en','zh-CN']:
 target=out/'client/data/locales'/f'{code}.json';target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(repo/'client/data/locales'/f'{code}.json',target)
spec=importlib.util.spec_from_file_location('client_exporter',repo/'tools/export_client_catalog.py');catalog=importlib.util.module_from_spec(spec);spec.loader.exec_module(catalog);catalog.ROOT=out;catalog.main()
old=catalog.fields((repo/'server/config/generated/fantasycard.config.bytes').read_bytes());new=catalog.fields((server/'fantasycard.config.bytes').read_bytes())
def bodies(bundle):return{catalog.fields(t)[1][0].decode():t for t in bundle[3]}
before=bodies(old);after=bodies(new);assert len(before)==len(after)==38 and set(after)==set(before)
assert all(after[n]==data for n,data in before.items() if n!='SeasonDifficulty');assert sum(len(catalog.fields(t).get(3,[])) for t in after.values())==1829
oldrows=catalog.fields(before['SeasonDifficulty'])[3];newrows=catalog.fields(after['SeasonDifficulty'])[3];assert oldrows[1:]==newrows[1:]
oldvalues=catalog.fields(oldrows[0])[1];newvalues=catalog.fields(newrows[0])[1];assert [i for i,(a,b) in enumerate(zip(oldvalues,newvalues)) if a!=b]==[2,3]
a=json.loads((repo/'client/data/catalog.json').read_bytes());z=json.loads((out/'client/data/catalog.json').read_bytes());assert len(z['tables'])==32 and all(a['tables'][n]==z['tables'][n] for n in a['tables'] if n!='SeasonDifficulty') and 'SeasonMonsterTuning' not in z['tables'];assert a['tables']['SeasonDifficulty'][1:]==z['tables']['SeasonDifficulty'][1:]
assert (out/'client/data/card_descriptions.json').read_bytes()==(repo/'client/data/card_descriptions.json').read_bytes();assert new[1][0].decode()=='season-v1-config-16' and (server/'fantasycard.config.sha256').read_text().strip()==new[2][0].hex()
result=dict(status='candidate16_export_verified_not_installed',version='season-v1-config-16',content_hash=new[2][0].hex(),binary_sha256=hashlib.sha256((server/'fantasycard.config.bytes').read_bytes()).hexdigest(),workbook_sha256=proof['after_sha256'],tables=38,rows=1829,client_public_tables=32,other_37_table_messages_byte_identical=True,other_public_tables_equal=True,D0_only_hp_and_shield_changed=True,card_descriptions_unchanged=True,formal_installed=False,production_activated=False)
(out/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))
