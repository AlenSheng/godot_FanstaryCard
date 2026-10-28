"""Run explicit control-union, capped-healing and cross-clock metric faults."""
import argparse
import json
from pathlib import Path
import subprocess
from pr13_experience_metrics import control_union,recovery,elapsed
from pr13_render_cases import ROOT,sha,write


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);args=p.parse_args();out=args.output.resolve();out.mkdir(parents=True,exist_ok=False)
    plan=ROOT/'docs/plans/PR13_ACCEPTANCE_DETAILS_20260930.json';contracts={c['id']:c for pkg in json.loads(plan.read_text(encoding='utf8'))['packages'] for t in pkg['subtasks'] for c in t['test_cases']};rows=[]
    def record(cid,actual,ok):rows.append(dict(case_id=cid,executed=True,status='Passed' if ok else 'Failed',setup=contracts[cid]['setup_and_injection'],expected=contracts[cid]['expected'],profiles_executed=['OFFLINE'],scope='Actual report accounting helper with declared controlled intervals/recovery/clock origins; sampled experiment and native gameplay layers separate',actual=actual))
    origin=dict(host='controlled-host',process_epoch='process-1')
    union=control_union([dict(start_ms=0,end_ms=3000,clock_origin=origin),dict(start_ms=1000,end_ms=4000,clock_origin=origin)])
    record('PR13-B01.3-T01',union,union['union_ms']==4000 and union['interval_count']==2)
    heal=recovery(10,2);full=recovery(10,0)
    record('PR13-B01.3-T02',dict(partial=heal,full=full),heal['effective']==2 and heal['overflow']==8 and full['effective']==0 and full['overflow']==10)
    foreign=elapsed(dict(monotonic_ms=5000,clock_origin=origin),dict(monotonic_ms=6000,clock_origin=dict(host='other-host',process_epoch='process-2')))
    record('PR13-B01.3-T03',foreign,foreign['available'] is False and foreign['value_ms'] is None)
    (out/'cases.jsonl').write_bytes(''.join(json.dumps(row,ensure_ascii=False)+'\n' for row in rows).encode());write(out/'report.json',dict(source_sha=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),plan_sha256=sha(plan),source=dict(scope='controlled experience metric faults',input_hashes={p:sha(ROOT/p) for p in ['tools/pr13_experience_metrics.py','tools/pr13_experience_metric_cases.py','tools/pr13_simulation_report.py']}),executed=len(rows),passed=sum(row['status']=='Passed' for row in rows),accepted=False));print(json.dumps(dict(executed=len(rows),passed=sum(row['status']=='Passed' for row in rows))))
    return 0 if all(row['status']=='Passed' for row in rows) else 1


if __name__=='__main__':raise SystemExit(main())
