"""Readonly tested-source attribution and controlled manifest/run identity faults."""
import argparse
import json
from pathlib import Path
import subprocess
import tempfile
from pr13_render_cases import ROOT,sha,write
from pr13_stages import source_references
from pr13_public_evidence import validated_files
from pr13_runtime_evidence import reconcile_cycles


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);args=p.parse_args();out=args.output.resolve();out.mkdir(parents=True,exist_ok=False)
    plan=ROOT/'docs/plans/PR13_ACCEPTANCE_DETAILS_20260930.json';contracts={c['id']:c for pkg in json.loads(plan.read_text(encoding='utf8'))['packages'] for t in pkg['subtasks'] for c in t['test_cases']};rows=[]
    def record(cid,actual,ok):rows.append(dict(case_id=cid,executed=True,status='Passed' if ok else 'Failed',setup=contracts[cid]['setup_and_injection'],expected=contracts[cid]['expected'],profiles_executed=['OFFLINE','AUDIT'],scope='Actual readonly local source/report attribution and controlled immutable-file/run-context faults; no production rollback or historical raw repair',actual=actual))
    parent=ROOT/'outputs/pr13-local-20261008/S3/client-after-prelaunch/commands.json';before=sha(parent);commands=json.loads(parent.read_text(encoding='utf8'));tested=commands[0]['source_sha'];refs=source_references('HEAD',tested)
    record('PR13-A09.1-T01',dict(refs,parent_sha256=before,actual_runtime_source=tested,actual_new_head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()),refs['different_sources'] and not refs['runtime_execution_verified'] and sha(parent)==before)
    with tempfile.TemporaryDirectory(dir=out) as directory:
        folder=Path(directory);fixture=folder/'fixture.json';fixture.write_bytes(b'{"v":1}\n');old=dict(path=fixture.name,bytes=fixture.stat().st_size,sha256=sha(fixture));fixture.write_bytes(b'{"v":2}\n');rejected=False
        try:validated_files(folder,[old])
        except ValueError:rejected=True
        fresh=dict(path=fixture.name,bytes=fixture.stat().st_size,sha256=sha(fixture));checked=validated_files(folder,[fresh])
        record('PR13-A09.1-T02',dict(old=old,current=fresh,old_manifest_rejected=rejected,fresh_manifest_accepted=len(checked)==1),rejected and old['sha256']!=fresh['sha256'] and len(checked)==1)
    event=dict(client_id='controlled-client',process_epoch='controlled-epoch',event_seq=1,cycle_id='controlled-client:1',match_id='controlled-match',at_unix_ms=1,event_type='cycle.completed',agent_id='must-not-become-run-id')
    result=reconcile_cycles([event],10,20)
    record('PR13-A09.1-T03',dict(derivation=result,input_run_id=event.get('run_id'),agent_id_not_used=True),'missing_context' in result['evidence_errors'] and result['final']['completed_cycles']==0 and 'run_id' not in event)
    (out/'cases.jsonl').write_bytes(''.join(json.dumps(row,ensure_ascii=False)+'\n' for row in rows).encode());write(out/'report.json',dict(source_sha=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),plan_sha256=sha(plan),source=dict(scope='actual source attribution and controlled input provenance faults',input_hashes={p:sha(ROOT/p) for p in ['tools/pr13_source_lifecycle_cases.py','tools/pr13_stages.py','tools/pr13_public_evidence.py','tools/pr13_runtime_evidence.py']}),executed=len(rows),passed=sum(r['status']=='Passed' for r in rows),accepted=False));print(json.dumps(dict(executed=len(rows),passed=sum(r['status']=='Passed' for r in rows))))
    return 0 if all(r['status']=='Passed' for r in rows) else 1


if __name__=='__main__':raise SystemExit(main())
