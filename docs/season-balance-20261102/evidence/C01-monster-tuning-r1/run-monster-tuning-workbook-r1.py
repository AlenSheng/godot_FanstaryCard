from pathlib import Path
import importlib.util,os,sys,json

sys.stdout.reconfigure(encoding='utf-8');repo=Path.cwd();base=Path(__file__).parent/'monster-tuning-workbook-r1';phase=sys.argv[1];assert phase in ['before','edit']
node=Path(r'C:\Users\SHENGJIAHAO\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin\node.exe')
spec=importlib.util.spec_from_file_location('guard',repo/'client/tests/fixture_runtime.py');guard=importlib.util.module_from_spec(spec);spec.loader.exec_module(guard)
if phase=='edit':
 marker=Path(r'C:\Users\SHENGJIAHAO\.cache\codex-runtimes\codex-primary-runtime\plugins\openai-primary-runtime\plugins\spreadsheets\skills\spreadsheets\container_tools\mark_artifact_operation_started.mjs');log=base/'edit-marker.original.json'
 if not log.exists():
  r=guard.guarded_run([str(node),str(marker),'--operation-kind','edit','--expected-output-count','1','--output-format','xlsx'],env=dict(os.environ),timeout=60,wait_seconds=180);log.write_text(json.dumps({'exit':r.returncode,'stdout':r.stdout,'stderr':r.stderr},indent=2)+'\n');print(r.stdout+r.stderr);assert r.returncode==0
 else:assert json.loads(log.read_bytes())['exit']==0
log=base/(phase+'.original.log');assert not log.exists()
r=guard.guarded_run([str(node),str(base/'build.mjs'),'--'+phase],env=dict(os.environ),timeout=240,wait_seconds=180)
log.write_text(r.stdout+r.stderr,encoding='utf-8');print((r.stdout+r.stderr)[-4500:]);assert r.returncode==0
