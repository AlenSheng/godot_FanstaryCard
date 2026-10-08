"""Actual renderer frame/delivery matrix in isolated user data with retained pixels."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'client/tests'))
from fixture_runtime import isolated_environment

def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def write(path,value):path.write_bytes((json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)+'\n').encode())
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--godot',required=True);p.add_argument('--output',required=True,type=Path);args=p.parse_args();out=args.output.resolve();out.mkdir(parents=True,exist_ok=False)
    plan_path=ROOT/'docs/plans/PR13_ACCEPTANCE_DETAILS_20260930.json';contracts={c['id']:c for pkg in json.loads(plan_path.read_text(encoding='utf8'))['packages'] for task in pkg['subtasks'] for c in task['test_cases']}
    head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    paths=['client/tests/pr13_feedback_frames.gd','client/tests/pr13_feedback_frames.tscn','tools/pr13_render_cases.py','client/tests/art_preview.gd','client/main.tscn','client/data/catalog.json']
    paths+=subprocess.check_output(['git','ls-files','client/ui','client/state','client/network'],cwd=ROOT,text=True).splitlines()
    inputs={path:sha(ROOT/path) for path in sorted(set(paths)) if (ROOT/path).is_file()}
    env=isolated_environment(out,FANTASYCARD_SERVER_URL='http://127.0.0.1:1',FANTASYCARD_ART_EVIDENCE=str(out),FANTASYCARD_LOAD_RUN_ID='render-frame-contract')
    cmd=[args.godot,'--path',str(ROOT/'client'),'--rendering-method','gl_compatibility','--max-fps','30','res://tests/pr13_feedback_frames.tscn']
    options={}
    if sys.platform=='win32':
        startup=subprocess.STARTUPINFO();startup.dwFlags|=subprocess.STARTF_USESHOWWINDOW;startup.wShowWindow=0;options['startupinfo']=startup
    start=time.monotonic();code=None
    with (out/'engine.private.log').open('wb') as log:
        child=subprocess.Popen(cmd,cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT,**options)
        try:code=child.wait(timeout=270)
        except subprocess.TimeoutExpired:pass
        finally:
            if child.poll() is None:child.kill();child.wait(timeout=5)
    clean=code is not None and not any(marker in (out/'engine.private.log').read_text(encoding='utf8',errors='replace') for marker in ('SCRIPT ERROR','Parse Error','Failed to load script'))
    native=json.loads((out/'report.json').read_text(encoding='utf8')) if (out/'report.json').exists() else {}
    rows=native.get('cases',[])
    for row in rows:
        row.update(setup=contracts[row['case_id']]['setup_and_injection'],expected=contracts[row['case_id']]['expected'])
        if not clean or native.get('display_driver')=='headless' or len(native.get('observations',[]))!=162:row['status']='Failed'
    if any(sha(ROOT/path)!=value for path,value in inputs.items()):raise ValueError('Rendered runtime inputs changed during execution')
    write(out/'observations.json',{'display_driver':native.get('display_driver'),'renderer':native.get('renderer'),'observations':native.get('observations',[]),'errors':native.get('errors',[])})
    (out/'cases.jsonl').write_bytes(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in rows).encode())
    write(out/'report.json',{'source_sha':head,'plan_sha256':sha(plan_path),'source':{'scope':'actual renderer, controlled delivery fixtures and actual UI callbacks','input_hashes':inputs},'executed':len(rows),'passed':sum(r['status']=='Passed' for r in rows),'profiles_executed':['OFFLINE','RENDER'],'native_execution_clean':clean,'exit_code':code,'matrix_rows':len(native.get('observations',[])),'display_driver':native.get('display_driver'),'adapter':native.get('renderer'),'pid':child.pid,'elapsed_seconds':time.monotonic()-start,'accepted':False})
    write(out/'commands.json',{'command':cmd,'exit_code':code,'timeout_seconds':270,'user_data_isolated':True,'engine_version':subprocess.check_output([args.godot,'--version'],text=True).strip()})
    write(out/'manifest.json',{'files':[{'path':f.name,'bytes':f.stat().st_size,'sha256':sha(f)} for f in sorted(out.glob('*')) if f.is_file()]})
    print(json.dumps({'executed':len(rows),'passed':sum(r['status']=='Passed' for r in rows),'matrix_rows':len(native.get('observations',[])),'native_clean':clean}));return 0 if code==0 and clean and len(rows)==3 and all(r['status']=='Passed' for r in rows) else 1
if __name__=='__main__':raise SystemExit(main())
