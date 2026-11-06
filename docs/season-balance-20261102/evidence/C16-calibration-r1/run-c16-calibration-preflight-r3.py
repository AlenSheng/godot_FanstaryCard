from pathlib import Path
import json,hashlib,subprocess,sys,importlib.util,os,shutil,tarfile,io

sys.stdout.reconfigure(encoding='utf-8');repo=Path.cwd();base=Path(__file__).parent;out=base/'c16-calibration-preflight-r3';assert not out.exists();out.mkdir()
old=json.loads((repo/'docs/season-balance-20261102/evidence/C16-themes/comparison/budget-checkpoint.json').read_bytes());assert old['attempts_committed']==121 and old['remaining']==179
files=subprocess.check_output(['git','ls-files','--cached','--others','--exclude-standard','-z','--','server','protocol','config/FantasyCard_Config.xlsx','client/data/catalog.json']).decode().split('\0');pin={n:hashlib.sha256((repo/n).read_bytes()).hexdigest() for n in files if n and (repo/n).is_file()};(out/'source-pin.json').write_text(json.dumps(pin,indent=2)+'\n',encoding='utf-8')
target=out/'config/FantasyCard_Config.xlsx';target.parent.mkdir();shutil.copyfile(repo/'config/FantasyCard_Config.xlsx',target)
with tarfile.open(out/'source-snapshot.original.tar.gz','w:gz') as tf:
 for n in sorted(pin):
  if Path(n).suffix in ['.cs','.sql','.csproj','.props','.targets','.proto']:
   data=(repo/n).read_bytes();info=tarfile.TarInfo(n);info.size=len(data);tf.addfile(info,io.BytesIO(data))
plan=dict(prior_encounters=121,limit=300,pilot_limit=18,remaining_after_complete_pilot=161,
          scope='Same actual formal selected-theme boss (current14=Fire); six difficulties x three heroes; direct-engine pilot only. Distinct counter-combo and fortress-control decks are static-preflight only.',
          entry_armor='D0 Blue+3 without effect affix; D1 Purple+3; D2..5 oneOrange4Purple+3; two Piercing including highest quality plus three Vitality.',
          permanent_level_assumed=5,effective_card_weapon_level='min(5,D)',seed=73,
          action_policy='Only current hand and public target/telegraph; top3 real read-only previews. Assert whole original snapshot unchanged by selection.',
          resource_observer='All net monster HP/shield changes after every actual cast and100ms tick, plus actual damage; exact conservation check.',
          production_numeric_changes=False,minimum_observation_seconds_limit=600,B05_budget=300,B05_retest=False,C15_UI_retest=False,capacity100_retest=False,
          local_reserve_GiB=2,startup_GiB=1)
(out/'plan.json').write_text(json.dumps(plan,indent=2)+'\n',encoding='utf-8')
spec=importlib.util.spec_from_file_location('guard',repo/'client/tests/fixture_runtime.py');guard=importlib.util.module_from_spec(spec);spec.loader.exec_module(guard)
cmd=['dotnet','test',str(repo/'server/tests/FantasyCard.Server.Tests/FantasyCard.Server.Tests.csproj'),'--artifacts-path',str(out/'build'),'--filter','FullyQualifiedName~SeasonThemeCalibrationTests.PreflightBuildsAreDistinctLegalAndRespectAllSixArmorEntryCapsWithoutRunningEncounters','--logger','trx;LogFileName=preflight.trx','--results-directory',str(out/'results'),'--verbosity','minimal','-m:1','-p:UseSharedCompilation=false']
try:r=guard.guarded_run(cmd,env=dict(os.environ,DOTNET_CLI_UI_LANGUAGE='en',DOTNET_CLI_TELEMETRY_OPTOUT='1',DOTNET_NOLOGO='1',FANTASYCARD_RUN_C16_CALIBRATION='',FANTASYCARD_RUN_THEME_COMPARISON='',FANTASYCARD_RUN_B05_MATRIX='',FANTASYCARD_RUN_B05_FINAL_NINE='',FANTASYCARD_TEST_POSTGRES=''),timeout=240,wait_seconds=180)
except Exception as e:
 (out/'interrupted.original.json').write_text(json.dumps({'type':type(e).__name__,'error':str(e),'output':str(getattr(e,'output',''))},indent=2)+'\n');raise
(out/'build-and-preflight.original.log').write_text(r.stdout+r.stderr,encoding='utf-8');proof=dict(exit=r.returncode,new_encounters=0,source_unchanged=all(hashlib.sha256((repo/n).read_bytes()).hexdigest()==h for n,h in pin.items()),command=cmd)
(out/'result.json').write_text(json.dumps(proof,indent=2)+'\n',encoding='utf-8');print((r.stdout+r.stderr)[-4500:]);print(json.dumps(proof));assert r.returncode==0 and proof['source_unchanged']
