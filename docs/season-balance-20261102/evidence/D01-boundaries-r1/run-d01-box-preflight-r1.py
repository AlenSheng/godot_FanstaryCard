from pathlib import Path
import hashlib,importlib.util,json,os,time

base=Path(__file__).parent;repo=Path.cwd();build=base/'d01-preflight-r2';out=base/'d01-boxelements-preflight-r1';assert not out.exists();out.mkdir()
pin=json.loads((build/'source-pin.json').read_bytes());assert all(hashlib.sha256((repo/n).read_bytes()).hexdigest()==h for n,h in pin.items())
roster=base/'d01-boxelements-roster-r1.original.json';(out/'roster.original.json').write_bytes(roster.read_bytes())
binary=build/'build/bin/FantasyCard.Server.Tests/debug';manifest={p.relative_to(binary).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in binary.rglob('*') if p.is_file()};(out/'binary-manifest.original.json').write_text(json.dumps(manifest,indent=2)+'\n')
spec=importlib.util.spec_from_file_location('guard',repo/'client/tests/fixture_runtime.py');guard=importlib.util.module_from_spec(spec);spec.loader.exec_module(guard)
command=['dotnet',str(binary/'FantasyCard.Server.Tests.dll'),'-noLogo','-noColor','-noAutoReporters','-failSkips','-parallel','none','-reporter','verbose','-method','FantasyCard.Server.Tests.Config.SeasonCombatBoundaryMatrixTests.FrozenInputsUseLegalEntryCapsAndActualPublishedProfiles','-trx',str(out/'contracts.trx')]
r=guard.guarded_run(command,env=dict(os.environ,FANTASYCARD_RUN_D01_BOUNDARIES='1',FANTASYCARD_D01_PLAN=str(out/'roster.original.json'),FANTASYCARD_D01_PREFLIGHT_OUTPUT=str(out/'legality.original.json'),FANTASYCARD_RUN_C16_CALIBRATION='',FANTASYCARD_C16_REUSE_PREFLIGHT='',FANTASYCARD_RUN_THEME_COMPARISON='',FANTASYCARD_RUN_B05_MATRIX='',FANTASYCARD_RUN_B05_FINAL_NINE='',FANTASYCARD_TEST_POSTGRES=''),timeout=60,wait_seconds=180)
(out/'run.original.log').write_text(r.stdout+r.stderr,encoding='utf-8');result=dict(exit=r.returncode,new_D01_encounters=0,binary_unchanged=all(hashlib.sha256((binary/n).read_bytes()).hexdigest()==h for n,h in manifest.items()),source_unchanged=all(hashlib.sha256((repo/n).read_bytes()).hexdigest()==h for n,h in pin.items()))
(out/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result));assert result['exit']==0 and result['binary_unchanged'] and result['source_unchanged']
