"""Actual wait, receipt recovery and shield display in an isolated GPU renderer."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import time

from pr13_render_cases import ROOT, sha, write, isolated_environment


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--godot',required=True)
    p.add_argument('--output',type=Path,required=True)
    args=p.parse_args();out=args.output.resolve();out.mkdir(parents=True,exist_ok=False)
    plan=ROOT/'docs/plans/PR13_ACCEPTANCE_DETAILS_20260930.json'
    contracts={c['id']:c for pkg in json.loads(plan.read_text(encoding='utf8'))['packages'] for task in pkg['subtasks'] for c in task['test_cases']}
    source=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    paths=['tools/pr13_wait_render_cases.py','tools/pr13_render_cases.py','client/tests/pr13_wait_frames.gd','client/tests/pr13_wait_frames.tscn','client/tests/art_preview.gd','client/tests/test_settlement_polling.gd','client/tests/test_settlement_return.gd','client/main.tscn']
    paths+=subprocess.check_output(['git','ls-files','client/ui','client/state','client/network','client/data'],cwd=ROOT,text=True).splitlines()
    inputs={path:sha(ROOT/path) for path in sorted(set(paths)) if (ROOT/path).is_file()}
    env=isolated_environment(out,FANTASYCARD_SERVER_URL='http://127.0.0.1:1',FANTASYCARD_ART_EVIDENCE=str(out),FANTASYCARD_LOAD_RUN_ID='render-wait-contract')
    command=[args.godot,'--path',str(ROOT/'client'),'--rendering-method','gl_compatibility','--max-fps','30','res://tests/pr13_wait_frames.tscn']
    options={}
    if sys.platform=='win32':
        startup=subprocess.STARTUPINFO();startup.dwFlags|=subprocess.STARTF_USESHOWWINDOW;startup.wShowWindow=0;options['startupinfo']=startup
    start=time.monotonic();code=None
    with (out/'engine.private.log').open('wb') as log:
        child=subprocess.Popen(command,cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT,**options)
        try:code=child.wait(timeout=90)
        except subprocess.TimeoutExpired:pass
        finally:
            if child.poll() is None:child.kill();child.wait(timeout=5)
    clean=code is not None and not any(marker in (out/'engine.private.log').read_text(encoding='utf8',errors='replace') for marker in ('SCRIPT ERROR','Parse Error','Failed to load script'))
    native=json.loads((out/'native-result.json').read_text(encoding='utf8')) if (out/'native-result.json').exists() else {}
    rows=native.get('cases',[])
    for row in rows:
        row.update(setup=contracts[row['case_id']]['setup_and_injection'],expected=contracts[row['case_id']]['expected'])
        if not clean or native.get('display_driver')=='headless' or len(native.get('observations',[]))!=72:row['status']='Failed'
    if any(sha(ROOT/path)!=value for path,value in inputs.items()):raise ValueError('Renderer input changed during native execution')
    write(out/'observations.json',{k:native.get(k) for k in ('observations','display_driver','adapter')})
    (out/'cases.jsonl').write_bytes(''.join(json.dumps(row,ensure_ascii=False)+'\n' for row in rows).encode())
    write(out/'report.json',dict(source_sha=source,plan_sha256=sha(plan),source=dict(scope='actual controlled wait/recovery/render components',input_hashes=inputs),executed=len(rows),passed=sum(r['status']=='Passed' for r in rows),exit_code=code,native_clean=clean,display_driver=native.get('display_driver'),adapter=native.get('adapter'),observations=len(native.get('observations',[])),elapsed_seconds=time.monotonic()-start,accepted=False))
    write(out/'commands.json',dict(command=command,exit_code=code,timeout_seconds=90,user_data_isolated=True))
    print(json.dumps(dict(executed=len(rows),passed=sum(r['status']=='Passed' for r in rows),native_clean=clean,observations=len(native.get('observations',[])))))
    return 0 if code==0 and clean and len(rows)==12 and all(row['status']=='Passed' for row in rows) else 1


if __name__=='__main__':raise SystemExit(main())
