from pathlib import Path
import json,hashlib,subprocess,sys,importlib.util,os,shutil,tarfile,io

sys.stdout.reconfigure(encoding='utf-8');repo=Path.cwd();base=Path(__file__).parent;out=base/'monster-tuning-contract-r2';assert not out.exists();out.mkdir()
files=subprocess.check_output(['git','ls-files','--cached','--others','--exclude-standard','-z','--','server','protocol','config/FantasyCard_Config.xlsx','client/data/catalog.json','client/tests/fixture_runtime.py']).decode().split('\0');pin={n:hashlib.sha256((repo/n).read_bytes()).hexdigest() for n in files if n and (repo/n).is_file()};(out/'source-pin.json').write_text(json.dumps(pin,indent=2)+'\n',encoding='utf-8')
target=out/'config/FantasyCard_Config.xlsx';target.parent.mkdir();shutil.copyfile(repo/'config/FantasyCard_Config.xlsx',target)
with tarfile.open(out/'source-snapshot.original.tar.gz','w:gz') as tf:
 for n in sorted(pin):
  if Path(n).suffix in ['.cs','.sql','.csproj','.props','.targets','.proto'] or '/Fixtures/' in n:
   data=(repo/n).read_bytes();info=tarfile.TarInfo(n);info.size=len(data);tf.addfile(info,io.BytesIO(data))
spec=importlib.util.spec_from_file_location('guard',repo/'client/tests/fixture_runtime.py');guard=importlib.util.module_from_spec(spec);spec.loader.exec_module(guard)
cmd=['dotnet','test',str(repo/'server/tests/FantasyCard.Server.Tests/FantasyCard.Server.Tests.csproj'),'--artifacts-path',str(out/'build'),'--filter','FullyQualifiedName~SeasonMonsterTuningContractTests','--logger','trx;LogFileName=contracts.trx','--results-directory',str(out/'results'),'--verbosity','minimal','-m:1','-p:UseSharedCompilation=false']
try:r=guard.guarded_run(cmd,env=dict(os.environ,DOTNET_CLI_UI_LANGUAGE='en',DOTNET_CLI_TELEMETRY_OPTOUT='1',DOTNET_NOLOGO='1',FANTASYCARD_RUN_C16_CALIBRATION='',FANTASYCARD_RUN_THEME_COMPARISON='',FANTASYCARD_RUN_B05_MATRIX='',FANTASYCARD_RUN_B05_FINAL_NINE='',FANTASYCARD_TEST_POSTGRES=''),timeout=240,wait_seconds=180)
except Exception as e:
 (out/'interrupted.original.json').write_text(json.dumps({'type':type(e).__name__,'error':str(e),'output':str(getattr(e,'output',''))},indent=2)+'\n');raise
(out/'build-and-tests.original.log').write_text(r.stdout+r.stderr,encoding='utf-8');proof=dict(exit=r.returncode,new_C16_encounters=0,new_B05_encounters=0,source_unchanged=all(hashlib.sha256((repo/n).read_bytes()).hexdigest()==h for n,h in pin.items()),command=cmd)
(out/'result.json').write_text(json.dumps(proof,indent=2)+'\n');print((r.stdout+r.stderr)[-4500:]);print(json.dumps(proof));assert r.returncode==0 and proof['source_unchanged']
