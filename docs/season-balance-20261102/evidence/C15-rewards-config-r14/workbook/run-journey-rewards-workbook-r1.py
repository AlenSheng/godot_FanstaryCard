from pathlib import Path
import importlib.util,os,sys,json,subprocess
sys.stdout.reconfigure(encoding='utf-8')
repo=Path.cwd();base=Path(r'G:\PR13Evidence\season-balance-20261102-r1\workbook');phase=sys.argv[1];assert phase in ['before','edit']
spec=importlib.util.spec_from_file_location('fixture_runtime',repo/'client/tests/fixture_runtime.py');guard=importlib.util.module_from_spec(spec);spec.loader.exec_module(guard)
node=Path(r'C:\Users\SHENGJIAHAO\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin\node.exe')
if phase=='edit':
 marker=Path(r'C:\Users\SHENGJIAHAO\.codex\plugins\cache\openai-primary-runtime\spreadsheets\26.1026.10807\skills\spreadsheets\container_tools\mark_artifact_operation_started.mjs')
 log=base/'journey-rewards-marker.original.log';assert not log.exists()
 r=guard.guarded_run([str(node),str(marker),'--operation-kind','edit','--expected-output-count','1','--output-format','xlsx'],env=dict(os.environ),timeout=60)
 log.write_text(r.stdout+r.stderr,encoding='utf-8');print(r.stdout+r.stderr,flush=True);assert r.returncode==0
log=base/('journey-rewards-'+phase+'.original.log');assert not log.exists()
r=guard.guarded_run([str(node),str(base/'season-journey-rewards.mjs'),'--'+phase],env=dict(os.environ),timeout=240)
log.write_text(r.stdout+r.stderr,encoding='utf-8');print((r.stdout+r.stderr)[-6500:]);assert r.returncode==0
