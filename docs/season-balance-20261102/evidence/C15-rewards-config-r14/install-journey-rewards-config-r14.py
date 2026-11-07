from pathlib import Path
import hashlib,json,shutil,os,sys
sys.stdout.reconfigure(encoding='utf-8')
repo=Path.cwd();b=Path(r'G:\PR13Evidence\season-balance-20261102-r1');out=b/'local-config-r14';draft=b/'workbook/outputs/01a1737c-c1cf-7342-92cd-7cea01eded79/season-journey-rewards-r1'
proof=json.loads((out/'result.json').read_text('utf-8'));preserved=json.loads((draft/'preservation-proof.json').read_text('utf-8'))
assert proof['original_35_table_messages_byte_identical'] and proof['original_30_public_tables_equal']
assert (repo/'server/config/generated/fantasycard.config.version.txt').read_text('utf-8').strip()=='season-v1-config-13'
assert hashlib.sha256((repo/'config/FantasyCard_Config.xlsx').read_bytes()).hexdigest()==preserved['before_sha256']
mapping={'config/FantasyCard_Config.xlsx':draft/'FantasyCard_Config.xlsx','client/data/catalog.json':out/'client/data/catalog.json'}
for folder in ['server/config/generated','client/data/generated']:
    for n in ['fantasycard.config.bytes','fantasycard.config.sha256','fantasycard.config.version.txt']:mapping[folder+'/'+n]=out/folder/n
assert hashlib.sha256(mapping['config/FantasyCard_Config.xlsx'].read_bytes()).hexdigest()==proof['workbook_sha256']
assert hashlib.sha256(mapping['server/config/generated/fantasycard.config.bytes'].read_bytes()).hexdigest()==proof['binary_sha256']
originals=out/'original-repo';assert not originals.exists();originals.mkdir();before={}
for name in mapping:
    p=originals/name;p.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(repo/name,p);before[name]=hashlib.sha256(p.read_bytes()).hexdigest()
archive=repo/'server/config/archive/season-v1-config-13';assert not archive.exists();archive.mkdir()
for n in ['fantasycard.config.bytes','fantasycard.config.sha256','fantasycard.config.version.txt']:shutil.copyfile(originals/'server/config/generated'/n,archive/n)
assert (archive/'fantasycard.config.version.txt').read_text('utf-8').strip()=='season-v1-config-13'
try:
    for name,source in mapping.items():
        temporary=(repo/name).with_name((repo/name).name+'.season14.staging');assert not temporary.exists();shutil.copyfile(source,temporary);os.replace(temporary,repo/name)
    for name,source in mapping.items():assert (repo/name).read_bytes()==source.read_bytes(),name
except BaseException:
    for name in mapping:shutil.copyfile(originals/name,repo/name)
    raise
result=dict(version='season-v1-config-14',formal_collection_worktree_installed=True,production_activated=False,production_restarted=False,original_repo_sha256=before,installed_sha256={name:hashlib.sha256((repo/name).read_bytes()).hexdigest() for name in mapping},archive13_sha256={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in archive.iterdir()})
assert not (out/'install.original.json').exists();(out/'install.original.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8');print(json.dumps(result))
