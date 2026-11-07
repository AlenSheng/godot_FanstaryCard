from pathlib import Path
import importlib.util,subprocess,json,hashlib
repo=Path.cwd();root=Path(r'G:\PR13Evidence\season-balance-20261102-r1/local-domain-r1');assert not root.exists();root.mkdir()
spec=importlib.util.spec_from_file_location('fixture_runtime',repo/'client/tests/fixture_runtime.py');r=importlib.util.module_from_spec(spec);spec.loader.exec_module(r)
pins={p.relative_to(repo).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in (repo/'server').rglob('*') if p.is_file() and p.suffix in ['.cs','.sql','.csproj','.props','.targets','.bytes'] and not any(x in p.parts for x in ['bin','obj','.artifacts'])}
(root/'source-pin.json').write_text(json.dumps(pins,indent=2)+'\n')
cmd=['dotnet','test',str(repo/'server/tests/FantasyCard.Domain.Tests/FantasyCard.Domain.Tests.csproj'),'--artifacts-path',str(root/'build'),'--filter','FullyQualifiedName!~SeasonResourceLoopTests&FullyQualifiedName!~MonsterPoolBaselineContractTests','--logger','trx;LogFileName=base-drops-domain.trx','--results-directory',str(root/'results'),'--verbosity','minimal','-m:1','-p:UseSharedCompilation=false']
print('Starting isolated local .NET10 Domain checks; B05 and unchanged9000 diagnostic excluded',flush=True)
try:
 result=r.guarded_run(cmd,env=dict(__import__('os').environ,DOTNET_CLI_TELEMETRY_OPTOUT='1',DOTNET_NOLOGO='1'),timeout=240)
except Exception as error:
 output=getattr(error,'output','') or '';output=output.decode('utf-8',errors='replace') if isinstance(output,bytes) else output
 (root/'failed.original.log').write_text(output,encoding='utf-8');raise
text=result.stdout+result.stderr;(root/'test.original.log').write_text(text,encoding='utf-8')
proof={'exit':result.returncode,'SDK':'10.0.400','production_database_used':False,'B05_not_run':True,'actual_game_matches':0,'command':cmd,'source_unchanged':all(hashlib.sha256((repo/n).read_bytes()).hexdigest()==h for n,h in pins.items())}
(root/'result.json').write_text(json.dumps(proof,indent=2)+'\n');print(text[-7000:]);print(json.dumps(proof));assert result.returncode==0 and proof['source_unchanged']
