from pathlib import Path
import json,hashlib,subprocess,sys,importlib.util,os

sys.stdout.reconfigure(encoding='utf-8');repo=Path.cwd();base=Path(__file__).parent;out=base/'b05-final-local-build-r2';assert not out.exists();out.mkdir()
budget=json.loads((repo/'docs/season-balance-20261102/evidence/B05/test-budget.json').read_bytes());assert budget['used']==291 and budget['remaining']==9 and not budget['full_matrix_rerun_authorized']
plan=dict(item='B05',prior_used=291,maximum=300,additional_limit=9,mode='three heroes x water/draw-engine/core; D2 effective card/weapon2 and 1Orange4Purple armor+3',
          path=[[0,0],[0,1],[0,2],[0,3],[0,4],[1,4],[2,4],[2,3]],map_condition='first natural seed>=73150 with original spawn0,0 and boss2,3; all original cells/stats preserved',
          formal_config='season-v1-config-14',old_matrix_not_enabled=True,old_42_timeouts_retained=True,not_class_balance_or_population_evidence=True,
          no_monster_or_player_resets=True,no_100_player_capacity=True,local_reserve_GiB=2,local_startup_GiB=1)
(out/'plan.json').write_text(json.dumps(plan,indent=2)+'\n',encoding='utf-8')
names=subprocess.check_output(['git','ls-files','--cached','--others','--exclude-standard','-z','--','server','protocol','config/FantasyCard_Config.xlsx']).decode().split('\0');pin={n:hashlib.sha256((repo/n).read_bytes()).hexdigest() for n in names if n and (repo/n).is_file()};(out/'source-pin.json').write_text(json.dumps(pin,indent=2)+'\n',encoding='utf-8')
spec=importlib.util.spec_from_file_location('guard',repo/'client/tests/fixture_runtime.py');guard=importlib.util.module_from_spec(spec);spec.loader.exec_module(guard)
cmd=['dotnet','build',str(repo/'server/tests/FantasyCard.Domain.Tests/FantasyCard.Domain.Tests.csproj'),'--artifacts-path',str(out/'build'),'--verbosity','minimal','-m:1','-p:UseSharedCompilation=false']
try:r=guard.guarded_run(cmd,env=dict(os.environ,DOTNET_CLI_UI_LANGUAGE='en',DOTNET_CLI_TELEMETRY_OPTOUT='1',DOTNET_NOLOGO='1',FANTASYCARD_RUN_B05_MATRIX='',FANTASYCARD_RUN_B05_FINAL_NINE=''),timeout=240,wait_seconds=180)
except Exception as e:
 (out/'interrupted.original.json').write_text(json.dumps({'type':type(e).__name__,'error':str(e),'output':str(getattr(e,'output',''))},indent=2)+'\n',encoding='utf-8');raise
(out/'build.original.log').write_text(r.stdout+r.stderr,encoding='utf-8');proof=dict(exit=r.returncode,source_unchanged=all(hashlib.sha256((repo/n).read_bytes()).hexdigest()==h for n,h in pin.items()),new_routes=0,build_only=True,command=cmd)
(out/'result.json').write_text(json.dumps(proof,indent=2)+'\n',encoding='utf-8');print((r.stdout+r.stderr)[-3500:]);print(json.dumps(proof));assert r.returncode==0 and proof['source_unchanged']
