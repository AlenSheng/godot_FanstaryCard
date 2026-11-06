from pathlib import Path
import json,hashlib,os,importlib.util
base=Path(__file__).parent;repo=Path.cwd();out=base/'d03-card10-holdout-preflight-r1';assert not out.exists();out.mkdir()
build=base/'d03-card10-preflight-r1';pin=json.loads((build/'source-pin.json').read_bytes());assert all(hashlib.sha256((repo/n).read_bytes()).hexdigest()==h for n,h in pin.items())
cmd=['dotnet',str(build/'build/bin/FantasyCard.Server.Tests/debug/FantasyCard.Server.Tests.dll'),'-noLogo','-noColor','-noAutoReporters','-failSkips','-parallel','none','-reporter','verbose','-method','FantasyCard.Server.Tests.Config.SeasonClassEfficiencyPilotTests.CandidateInputsAreLegalAndBothSpeedLayersAreValued','-trx',str(out/'cases.trx'),'-xml',str(out/'cases.xml')]
spec=importlib.util.spec_from_file_location('guard',repo/'client/tests/fixture_runtime.py');guard=importlib.util.module_from_spec(spec);spec.loader.exec_module(guard)
r=guard.guarded_run(cmd,env=dict(os.environ,FANTASYCARD_RUN_D03_EFFICIENCY='1',FANTASYCARD_D03_PLAN=str(base/'d03-card10-holdout-roster-r1.original.json'),FANTASYCARD_D03_PREFLIGHT_OUTPUT=str(out/'legality.original.json'),FANTASYCARD_D03_CARD_VARIANT_OUTPUT=str(out/'variant'),FANTASYCARD_TEST_POSTGRES=''),timeout=90)
(out/'test.original.log').write_text(r.stdout+r.stderr,encoding='utf-8');(out/'result.json').write_text(json.dumps(dict(exit=r.returncode,new_encounters=0,same_binary_reused=True))+'\n');print(r.stdout+r.stderr);assert r.returncode==0
