"""Bounded actual Godot store/codec UI contracts with explicit canonical IDs."""
import argparse,hashlib,json,subprocess,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'client/tests'))
from fixture_runtime import isolated_environment

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def write(p,v):p.write_bytes((json.dumps(v,ensure_ascii=False,indent=2,allow_nan=False)+'\n').encode())
def main():
 parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--godot',required=True);parser.add_argument('--output',type=Path,required=True);args=parser.parse_args();out=args.output.resolve();out.mkdir(parents=True,exist_ok=False)
 plan_path=ROOT/'docs/plans/PR13_ACCEPTANCE_DETAILS_20260930.json';plan=json.loads(plan_path.read_text(encoding='utf8'));contracts={c['id']:c for p in plan['packages'] for s in p['subtasks'] for c in s['test_cases']}
 head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip();paths=('tools/pr13_ui_cases.py','client/tests/pr13_ui_contract_cases.gd','client/state/game_store.gd','client/network/gateway.gd','client/network/protobuf.gd','client/data/catalog.json','client/ui/palette.gd','client/tests/test_play_retry.gd','client/tests/test_combat_feedback_scope.gd')
 inputs={p:sha(ROOT/p) for p in paths};env=isolated_environment(out,FANTASYCARD_SERVER_URL='http://127.0.0.1:1',FANTASYCARD_LOAD_RUN_ID='ui-offline-case',PR13_UI_CASE_REPORT=str(out/'native-result.json'))
 command=[args.godot,'--headless','--path',str(ROOT/'client'),'--script','res://tests/pr13_ui_contract_cases.gd'];started=time.monotonic()
 with (out/'engine.log').open('wb') as log:
  process=subprocess.Popen(command,cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
  try:code=process.wait(timeout=90)
  finally:
   if process.poll() is None:process.kill();process.wait(timeout=5)
 log=(out/'engine.log').read_text(encoding='utf8',errors='replace')
 native_clean=code==0 and not any(marker in log for marker in ('SCRIPT ERROR','Parse Error','Failed to load script'))
 records=json.loads((out/'native-result.json').read_text(encoding='utf8'))['cases'] if (out/'native-result.json').exists() else []
 if not native_clean:
  for record in records:record.update(status='Failed',native_execution_invalid=True)
 for r in records:r.update(setup=contracts[r['case_id']]['setup_and_injection'],expected=contracts[r['case_id']]['expected'])
 (out/'cases.jsonl').write_bytes(''.join(json.dumps(r,ensure_ascii=False,allow_nan=False)+'\n' for r in records).encode())
 write(out/'report.json',{'source_sha':head,'source':{'scope':'actual native Godot store/codec; controlled room/gateway fixtures','input_hashes':inputs},'plan_sha256':sha(plan_path),'executed':len(records),'passed':sum(r['status']=='Passed' for r in records),'exit_code':code,'native_execution_clean':native_clean,'command':command,'pid':process.pid,'elapsed_seconds':time.monotonic()-started,'profiles_executed':['OFFLINE'],'remaining_profiles':['RENDER'],'accepted':False})
 write(out/'manifest.json',{'files':[{'path':p.relative_to(out).as_posix(),'bytes':p.stat().st_size,'sha256':sha(p)} for p in sorted(out.rglob('*')) if p.is_file() and 'runtime' not in p.relative_to(out).parts]})
 print(json.dumps({'exit_code':code,'executed':len(records),'passed':sum(r['status']=='Passed' for r in records)}));return 0 if code==0 and len(records)==11 and all(r['status']=='Passed' for r in records) else 1
if __name__=='__main__':raise SystemExit(main())
