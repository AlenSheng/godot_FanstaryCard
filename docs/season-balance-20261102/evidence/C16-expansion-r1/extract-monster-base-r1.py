from pathlib import Path
import os,json,hashlib,importlib.util,sys

sys.stdout.reconfigure(encoding='utf-8');repo=Path.cwd();base=Path(__file__).parent;root=base/'monster-base-extractor-r1';assert not (root/'result.json').exists()
domain=base/'c16-remaining-build-r1/build/bin/FantasyCard.Server.Tests/debug/FantasyCard.Domain.dll';pin=json.loads((base/'c16-remaining-build-r1/source-pin.json').read_bytes());factory='server/src/FantasyCard.Domain/Combat/PveBattleFactory.cs';assert hashlib.sha256((repo/factory).read_bytes()).hexdigest()==pin[factory]
domain_hash=hashlib.sha256(domain.read_bytes()).hexdigest();sources={n:hashlib.sha256((root/n).read_bytes()).hexdigest() for n in ['MonsterBaseExtractor.csproj','Program.cs']}
spec=importlib.util.spec_from_file_location('guard',repo/'client/tests/fixture_runtime.py');guard=importlib.util.module_from_spec(spec);spec.loader.exec_module(guard)
environment=dict(os.environ,DOTNET_CLI_UI_LANGUAGE='en',DOTNET_CLI_TELEMETRY_OPTOUT='1',DOTNET_NOLOGO='1')
os.chdir(repo/'server')
build=guard.guarded_run(['dotnet','build',str(root/'MonsterBaseExtractor.csproj'),'--artifacts-path',str(root/'build'),'-m:1','-p:UseSharedCompilation=false','--verbosity','minimal'],env=environment,timeout=120,wait_seconds=180)
(root/'build.original.log').write_text(build.stdout+build.stderr,encoding='utf-8');print((build.stdout+build.stderr)[-1800:]);assert build.returncode==0
target=root/'legacy-base.original.json';assert not target.exists()
result=guard.guarded_run(['dotnet',str(root/'build/bin/MonsterBaseExtractor/debug/MonsterBaseExtractor.dll'),str(target)],env=environment,timeout=60,wait_seconds=180)
(root/'run.original.log').write_text(result.stdout+result.stderr,encoding='utf-8');print(result.stdout+result.stderr);assert result.returncode==0
data=json.loads(target.read_bytes());assert data['profiles']==35 and data['intent_rows']==58 and data['new_combat_encounters']==0
proof=dict(exit=0,source_factory_sha256=pin[factory],compiled_domain_sha256=domain_hash,compiled_domain_unchanged=hashlib.sha256(domain.read_bytes()).hexdigest()==domain_hash,extractor_sources=sources,base_data_sha256=hashlib.sha256(target.read_bytes()).hexdigest(),profiles=35,intents=58,new_encounters=0,workbook_edited=False)
(root/'result.json').write_text(json.dumps(proof,indent=2)+'\n');assert proof['compiled_domain_unchanged'];print(json.dumps(proof))
