"""Owned JSONL file fixture; distributions are fixture inputs, not measured service latency."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

root=Path(os.environ.get('PR13_SOURCE_ROOT','/workspace/godot_FanstaryCard')).resolve()
sys.path.insert(0,str(root/'tools'))
from gameplay_load_test import read_owned_statuses,read_audit_events
from gameplay_load_validation import aggregate_window,new_events
parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
out=args.output.resolve();out.mkdir(parents=True,exist_ok=False);report=out/'client.json'
code=r'''import json,os,pathlib,sys
report=pathlib.Path(sys.argv[1]);rows=[]
for seq in range(1,23):
 rows.append(dict(run_id='distribution-run',client_id='distribution-owned',process_epoch='epoch-A',event_seq=seq,
  at_unix_ms=10000+seq,type='http',path='/fixture/a' if seq%2 else '/fixture/b',route='/fixture/a' if seq%2 else '/fixture/b',
  phase='playing' if seq<16 else 'settlement',duration_ms=100 if seq==1 else 5,status=500 if seq==1 else 200,ok=seq!=1,result='error' if seq==1 else 'success'))
status=dict(run_id='distribution-run',client_id='distribution-owned',process_epoch='epoch-A',pid=os.getpid(),status_seq=1,
 now_unix_ms=10022,event_seq_max=22,telemetry=rows,operations=rows,online=False,room=False,last_progress_age_ms=0)
pathlib.Path(str(report)+'.status.json').write_text(json.dumps(status))
pathlib.Path(str(report)+'.telemetry.jsonl').write_text(''.join(json.dumps(r)+'\n' for r in rows))
print(json.dumps(dict(pid=os.getpid(),events_written=len(rows),fixture_clock=True,fixture_durations=True)),flush=True)
'''
argv=[sys.executable,'-c',code,str(report)]
with (out/'child.log').open('w') as log:
 child=subprocess.Popen(argv,stdout=log,stderr=subprocess.STDOUT)
 try:
  exit_code=child.wait(timeout=5)
 finally:
  if child.poll() is None:child.kill();child.wait(timeout=5)
entry=dict(client_id='distribution-owned',process=child,report=report,run_id='distribution-run',process_epoch='epoch-A')
owned,invalid=read_owned_statuses([entry],{},require_files=True)
fresh,lost=new_events(owned,{})
audit,audit_errors=read_audit_events([entry],owned)
assert invalid==lost==0 and not audit_errors and exit_code==0
assert fresh[0]['operations']==audit
def aggregate(rows):return aggregate_window([dict(operations=rows,telemetry=rows)])
stop_ms=10001;final_ms=10022
buckets=dict(running=[r for r in audit if r['at_unix_ms']<=stop_ms],drain=[r for r in audit if stop_ms<r['at_unix_ms']<=final_ms],final=[r for r in audit if r['at_unix_ms']<=final_ms])
stats={name:aggregate(rows) for name,rows in buckets.items()}
derived={route:aggregate([r for r in audit if r['route']==route]) for route in sorted(set(r['route'] for r in audit))}
last_window=aggregate(audit[-2:])
output=dict(integration_sha='ee8adcf40be9aebb1330156a3524910c08225ebc',fixture_clock=True,fixture_duration_values=True,
 service_capacity_claim=False,owned_child=dict(pid=child.pid,exit_code=exit_code,reaped=True,argv=argv),
 reader=dict(ownership_invalid=invalid,event_loss=lost,audit_errors=audit_errors,raw_equals_consumed=True),
 fixed_cutoffs=dict(start_ms=10000,stop_ms=stop_ms,final_ms=final_ms),cutoff_distributions=stats,
 diagnostic_derived_route_distributions=derived,last_window=last_window,
 full_run_error_count=stats['final']['error_count'],last_window_error_count=last_window['error_count'],
 unequal_window_p95_average=(stats['running']['http']['p95_ms']+stats['drain']['http']['p95_ms'])/2,
 full_raw_p95_ms=stats['final']['http']['p95_ms'],
 production_route_distribution_present=any('route' in k for k in stats['final']),
 production_throughput_present=any('throughput' in k for k in stats['final']),
 source_file_sha256={p:hashlib.sha256((root/p).read_bytes()).hexdigest() for p in ['tools/gameplay_load_validation.py','tools/gameplay_load_test.py']},
 stage='SupportForFullCriterionReview',
 limitation='Diagnostic fixture recomputation exists here; production aggregate/coordinator do not output route distributions/throughput/full-run HTTP three-cutoff fields. Do not label this harness as implementation of those missing production fields.',Accepted=False)
(out/'REPORT.json').write_text(json.dumps(output,indent=2)+'\n')
print(json.dumps({k:output[k] for k in ['full_run_error_count','last_window_error_count','unequal_window_p95_average','full_raw_p95_ms','production_route_distribution_present','production_throughput_present']}))
