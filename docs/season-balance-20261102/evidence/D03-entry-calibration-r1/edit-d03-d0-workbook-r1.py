from pathlib import Path
import hashlib,importlib.util,json,os,shutil,sys

sys.stdout.reconfigure(encoding='utf-8');repo=Path.cwd();base=Path(__file__).parent;root=base/'d03-d0-workbook-r1';before=root/'before';assert not before.exists();before.mkdir()
for n in ['config/FantasyCard_Config.xlsx','client/data/catalog.json','client/data/card_descriptions.json']+[side+'/data/generated/'+f for side in [] for f in []]:
    target=before/n;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(repo/n,target)
for folder in ['server/config/generated','client/data/generated']:
    for name in ['fantasycard.config.bytes','fantasycard.config.sha256','fantasycard.config.version.txt']:
        n=folder+'/'+name;target=before/n;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(repo/n,target)
pin={p.relative_to(before).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in before.rglob('*') if p.is_file()};(root/'before-manifest.original.json').write_text(json.dumps(pin,indent=2)+'\n')
assert pin['config/FantasyCard_Config.xlsx']=='83155471d16d294e4a46cab5621078e1e24cf9bfe6f90e9d73fdfb532af54010'
spec=importlib.util.spec_from_file_location('guard',repo/'client/tests/fixture_runtime.py');guard=importlib.util.module_from_spec(spec);spec.loader.exec_module(guard)
node=r'C:\Users\SHENGJIAHAO\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin\node.exe';marker=r'C:\Users\SHENGJIAHAO\.cache\codex-runtimes\codex-primary-runtime\plugins\openai-primary-runtime\plugins\spreadsheets\skills\spreadsheets\container_tools\mark_artifact_operation_started.mjs'
assert not (root/'edit-marker.original.json').exists()
r=guard.guarded_run([node,marker,'--operation-kind','edit','--expected-output-count','1','--output-format','xlsx'],env=dict(os.environ),timeout=60,wait_seconds=180);(root/'edit-marker.original.json').write_text(json.dumps(dict(exit=r.returncode,stdout=r.stdout,stderr=r.stderr,exactly_once_for_this_operation=True),indent=2)+'\n');assert r.returncode==0
r=guard.guarded_run([node,str(root/'build.mjs')],env=dict(os.environ),timeout=120,wait_seconds=180);(root/'edit.original.log').write_text(r.stdout+r.stderr,encoding='utf-8');print(r.stdout+r.stderr);assert r.returncode==0
assert hashlib.sha256((repo/'config/FantasyCard_Config.xlsx').read_bytes()).hexdigest()==pin['config/FantasyCard_Config.xlsx']
print('ArtifactTool output prepared; source formal15 workbook not yet replaced')
