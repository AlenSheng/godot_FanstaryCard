"""Execute the production READY loop's controlled dispatch/deadline boundaries."""
import argparse
import json
from pathlib import Path
import subprocess
import time
from pr13_render_cases import ROOT,sha,write,isolated_environment


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--godot',required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--script',choices=['ready','prelaunch','idle'],default='ready');args=p.parse_args();out=args.output.resolve();out.mkdir(parents=True,exist_ok=False)
    plan=ROOT/'docs/plans/PR13_ACCEPTANCE_DETAILS_20260930.json';contracts={c['id']:c for pkg in json.loads(plan.read_text(encoding='utf8'))['packages'] for t in pkg['subtasks'] for c in t['test_cases']}
    script={'ready':'pr13_ready_edges.gd','prelaunch':'pr13_prelaunch_boundaries.gd','idle':'pr13_idle_recovery.gd'}[args.script]
    source=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip();paths=['client/tests/'+script,'client/tests/gameplay_load_client.gd','client/network/gateway.gd','client/state/game_store.gd','tools/pr13_ready_edge_cases.py'];inputs={path:sha(ROOT/path) for path in paths}
    env=isolated_environment(out,FANTASYCARD_SERVER_URL='http://127.0.0.1:1',FANTASYCARD_LOAD_RUN_ID='ready-component',PR13_READY_EDGES=str(out/'native-result.json'))
    cmd=[args.godot,'--headless','--path',str(ROOT/'client'),'--script','res://tests/'+script];start=time.monotonic();code=None
    with (out/'native.private.log').open('wb') as log:
        child=subprocess.Popen(cmd,cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        try:code=child.wait(timeout=90)
        except subprocess.TimeoutExpired:pass
        finally:
            if child.poll() is None:child.kill();child.wait(timeout=5)
    clean=code is not None and not any(x in (out/'native.private.log').read_text(encoding='utf8',errors='replace') for x in ['SCRIPT ERROR','Parse Error','Failed to load script'])
    rows=json.loads((out/'native-result.json').read_text(encoding='utf8'))['cases'] if (out/'native-result.json').exists() else []
    for r in rows:
        r.update(setup=contracts[r['case_id']]['setup_and_injection'],expected=contracts[r['case_id']]['expected'])
        if not clean:r['status']='Failed'
    if any(sha(ROOT/p)!=h for p,h in inputs.items()):raise ValueError('READY source changed during execution')
    (out/'cases.jsonl').write_bytes(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in rows).encode());write(out/'report.json',dict(source_sha=source,plan_sha256=sha(plan),source=dict(scope='actual native production READY loop with declared controlled interfaces',input_hashes=inputs),executed=len(rows),passed=sum(r['status']=='Passed' for r in rows),native_clean=clean,exit_code=code,elapsed_seconds=time.monotonic()-start,accepted=False));print(json.dumps(dict(executed=len(rows),passed=sum(r['status']=='Passed' for r in rows),native_clean=clean)))
    return 0 if code==0 and clean and len(rows)=={'ready':4,'prelaunch':3,'idle':1}[args.script] and all(r['status']=='Passed' for r in rows) else 1


if __name__=='__main__':raise SystemExit(main())
