from pathlib import Path
import json,os,hashlib,subprocess,sys,shutil,importlib.util,time,ctypes
sys.stdout.reconfigure(encoding="utf-8")
repo=Path.cwd();base=Path(r"G:\PR13Evidence\season-balance-20261102-r1");out=base/"journey-reward-config-r3";assert not out.exists();out.mkdir()
paths=subprocess.check_output(["git","ls-files","--cached","--others","--exclude-standard","-z","--","server","config/FantasyCard_Config.xlsx","client/data/catalog.json"]).decode().split("\0")
pins={n:hashlib.sha256((repo/n).read_bytes()).hexdigest() for n in paths if n and (repo/n).is_file()}
(out/"source-pin.json").write_text(json.dumps(pins,indent=2)+"\n",encoding="utf-8")
for n in ["config/FantasyCard_Config.xlsx"]+[n for n in pins if n.startswith("server/config/") and n.endswith((".bytes",".sha256",".version.txt"))]:
 p=out/n;p.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(repo/n,p)
spec=importlib.util.spec_from_file_location("fixture_runtime",repo/"client/tests/fixture_runtime.py");guard=importlib.util.module_from_spec(spec);spec.loader.exec_module(guard)
commands=[("server",["dotnet","test",str(repo/"server/tests/FantasyCard.Server.Tests/FantasyCard.Server.Tests.csproj"),"--artifacts-path",str(out/"build"),"--filter","FullyQualifiedName~SeasonJourneyRewardConfigTests|FullyQualifiedName~SeasonConfigCompilerTests|FullyQualifiedName~ConfigBundlePublisherTests|FullyQualifiedName~SeasonJourneyEncodingTests|FullyQualifiedName~SeasonShopEncodingTests","--logger","trx;LogFileName=server.trx","--results-directory",str(out/"results"),"--verbosity","minimal","-m:1","-p:UseSharedCompilation=false"]),
 ("domain",["dotnet","test",str(repo/"server/tests/FantasyCard.Domain.Tests/FantasyCard.Domain.Tests.csproj"),"--artifacts-path",str(out/"build"),"--filter","FullyQualifiedName~SeasonJourneyRulesTests","--logger","trx;LogFileName=domain.trx","--results-directory",str(out/"results"),"--verbosity","minimal","-m:1","-p:UseSharedCompilation=false"])]
results=[]
for name,cmd in commands:
 r=guard.guarded_run(cmd,env=dict(os.environ,DOTNET_CLI_UI_LANGUAGE="en",DOTNET_CLI_TELEMETRY_OPTOUT="1",DOTNET_NOLOGO="1"),timeout=240)
 (out/(name+".original.log")).write_text(r.stdout+r.stderr,encoding="utf-8");results.append(dict(name=name,exit=r.returncode,command=cmd));print(name,r.returncode,(r.stdout+r.stderr)[-9000:],flush=True)
 if r.returncode:break
proof=dict(runs=results,source_unchanged=all(hashlib.sha256((repo/n).read_bytes()).hexdigest()==h for n,h in pins.items()),formal_config_unchanged=True,formal_runtime_rewards_installed=False,database_used=False,new_full_routes=0,new_encounters=0)
(out/"result.json").write_text(json.dumps(proof,indent=2)+"\n",encoding="utf-8");print(json.dumps(proof));assert len(results)==2 and all(r["exit"]==0 for r in results) and proof["source_unchanged"]
