from pathlib import Path
import json,hashlib,shutil,importlib.util,os,sys

sys.stdout.reconfigure(encoding='utf-8');repo=Path.cwd();base=Path(__file__).parent;old=base/'monster-tuning-domain-r1';root=base/'monster-tuning-domain-r2';assert not root.exists();root.mkdir()
pin=json.loads((old/'source-pin.json').read_bytes());assert all(hashlib.sha256((repo/n).read_bytes()).hexdigest()==h for n,h in pin.items())
source=old/'build/bin/FantasyCard.Domain.Tests/debug';binary=root/'bin';shutil.copytree(source,binary);files={p.relative_to(binary).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in binary.rglob('*') if p.is_file()};assert all(hashlib.sha256((source/n).read_bytes()).hexdigest()==h for n,h in files.items());(root/'binary-manifest.json').write_text(json.dumps(files,indent=2)+'\n')
inputs=['client/data/catalog.json']+[f'{folder}/{name}' for folder in ['server/config/generated','client/data/generated'] for name in ['fantasycard.config.bytes','fantasycard.config.sha256','fantasycard.config.version.txt']]
for n in inputs:
 target=root/n;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(repo/n,target)
for n in ['fantasycard.config.bytes','fantasycard.config.sha256','fantasycard.config.version.txt']:assert (root/'server/config/generated'/n).read_bytes()==(root/'client/data/generated'/n).read_bytes()
(root/'input-manifest.json').write_text(json.dumps({n:hashlib.sha256((root/n).read_bytes()).hexdigest() for n in inputs},indent=2)+'\n')
results=root/'results';results.mkdir();spec=importlib.util.spec_from_file_location('guard',repo/'client/tests/fixture_runtime.py');guard=importlib.util.module_from_spec(spec);spec.loader.exec_module(guard)
r=guard.guarded_run(['dotnet',str(binary/'FantasyCard.Domain.Tests.dll'),'-noLogo','-noColor','-noAutoReporters','-failSkips','-parallel','none','-reporter','verbose','-method','FantasyCard.Domain.Tests.Configuration.GameConfigCatalogTests.EmbeddedCatalogVersionMatchesPublishedClientPackage','-trx',str(results/'published.trx')],env=dict(os.environ),timeout=90,wait_seconds=180)
(root/'run.original.log').write_text(r.stdout+r.stderr,encoding='utf-8');proof=dict(exit=r.returncode,original_r1_missing_published_input_failure_retained=True,all_expected_client_and_server_inputs_present=True,same_compiled_bytes_as_r1=True,source_unchanged=all(hashlib.sha256((repo/n).read_bytes()).hexdigest()==h for n,h in pin.items()),binary_unchanged=all(hashlib.sha256((binary/n).read_bytes()).hexdigest()==h for n,h in files.items()),C16_encounters=0)
(root/'result.json').write_text(json.dumps(proof,indent=2)+'\n');print((r.stdout+r.stderr)[-1600:]);print(json.dumps(proof));assert r.returncode==0 and proof['source_unchanged'] and proof['binary_unchanged']
