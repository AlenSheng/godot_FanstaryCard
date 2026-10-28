import json
from pathlib import Path
import subprocess
import sys
import time
B=Path(__file__).resolve().parents[1];E=B/'evidence/sequence';E.mkdir(exist_ok=True)
sys.path.insert(0,str(B/'source/tools'))
from gameplay_load_test import read_owned_statuses,read_audit_events
from gameplay_load_validation import new_events,aggregate_window
commands=[];children=[]
def child():
 cmd=[sys.executable,str(B/'harness/writer_child.py')];p=subprocess.Popen(cmd,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True);children.append(p);commands.append({'command':cmd,'pid':p.pid,'started_monotonic_ns':time.monotonic_ns()});return p
def rows(cid,epoch,seqs):
 at=int(time.time()*1000)
 return [dict(run_id='owned-sequence-run',client_id=cid,process_epoch=epoch,event_seq=n,at_unix_ms=at,type='http',event_type='http',phase='playing',path='/fixture/file',route='/fixture/file',cycle_id='cycle:'+epoch,match_id='',logical_request_id=epoch+':'+str(n),ok=True,status=200,result='success',duration_ms=1) for n in seqs]
def write(p,path,cid,epoch,events,status_seq=1,audit=None):
 status=dict(run_id='owned-sequence-run',client_id=cid,process_epoch=epoch,status_seq=status_seq,now_unix_ms=int(time.time()*1000),online=False,room=False,last_progress_age_ms=0,cycles_completed=0,event_seq_max=max([e['event_seq'] for e in events],default=0),telemetry=events,operations=events,audit_lost_count=0,errors=[],cleanup={'state':'Passed'})
 p.stdin.write(json.dumps({'path':str(path),'status':status,'audit':events if audit is None else audit})+'\n');p.stdin.flush();ack=json.loads(p.stdout.readline());return dict(process=p,client_id=cid,run_id='owned-sequence-run',process_epoch=epoch,report=path,started_at_ms=int(time.time()*1000),started_at_monotonic_ms=time.monotonic()*1000),ack
def consume(entry,seen,cache=None):
 owned,invalid=read_owned_statuses([entry],cache=cache,require_files=True);fresh,lost=new_events(owned,seen);audit,errors=read_audit_events([entry],owned);return {'owned':owned,'invalid_files':invalid,'fresh':fresh,'lost_count':lost,'aggregate':aggregate_window(fresh),'audit':audit,'audit_errors':errors,'watermarks':[(list(k),v) for k,v in seen.items()]}
receipts=[]
try:
 d=E/'same-ms';d.mkdir(exist_ok=True);p=child();events=rows('same','e1',[1,2]);entry,ack=write(p,d/'status.json','same','e1',events);seen={};first=consume(entry,seen);second=consume(entry,seen)
 ok=first['lost_count']==0 and len(first['fresh'][0]['telemetry'])==2 and first['fresh'][0]['telemetry']==first['audit'] and second['fresh'][0]['telemetry']==[] and first['aggregate']['logical_request_count']==2 and second['aggregate']['logical_request_count']==0
 receipts.append({'case_id':'LOAD-03.1-T01','passed':ok,'actual_write_ack':ack,'first':first,'second':second})
 d=E/'gap';d.mkdir(exist_ok=True);p=child();events=rows('gap','e1',[1,3]);entry,ack=write(p,d/'status.json','gap','e1',events);seen={};first=consume(entry,seen);repaired=rows('gap','e1',[1,2,3,4]);entry,ack2=write(p,d/'status.json','gap','e1',repaired,2,audit=events+[repaired[3]]);second=consume(entry,seen)
 ok=first['lost_count']==1 and second['lost_count']==0 and len(second['fresh'][0]['telemetry'])==1 and any(e['error']=='event_sequence_gap_or_reorder' for e in second['audit_errors'])
 receipts.append({'case_id':'LOAD-03.1-T02','passed':ok,'first':first,'next_snapshot':second,'meaning':'Incremental lost_count is per-window; archived first loss plus audit gap persist. Coordinator sticky verdict executed separately.'})
 d=E/'epoch';d.mkdir(exist_ok=True);p1=child();e1,ack1=write(p1,d/'epoch1.json','restart','old-epoch',rows('restart','old-epoch',[1,2]));seen={};old=consume(e1,seen);p1.stdin.write('{"quit":true}\n');p1.stdin.flush();p1.wait(timeout=5)
 p2=child();e2,ack2=write(p2,d/'epoch2.json','restart','new-epoch',rows('restart','new-epoch',[1,2]));new=consume(e2,seen)
 ok=p1.pid!=p2.pid and old['lost_count']==new['lost_count']==0 and len(old['fresh'][0]['telemetry'])==len(new['fresh'][0]['telemetry'])==2 and len(seen)==2
 receipts.append({'case_id':'LOAD-03.1-T03','passed':ok,'old_pid':p1.pid,'new_pid':p2.pid,'old':old,'new':new,'launch_cache_policy':'New launch starts a new status receipt cache; shared event-watermark map retains both epochs.'})
 extras=[]
 for mode,seqs,archive_seqs in [('duplicate',[1,2],[1,1,2]),('out-of-order',[1,2],[2,1]),('truncation',[1,2],[1]),('tail-unflushed',[1,2],[1])]:
  d=E/mode;d.mkdir(exist_ok=True);p=child();events=rows(mode,'epoch',[1,2]);arch=[next(e for e in events if e['event_seq']==s) for s in archive_seqs];entry,_=write(p,d/'status.json',mode,'epoch',events,audit=arch);c=consume(entry,{});extras.append({'mode':mode,'passed':bool(c['audit_errors']),'actual':c})
 assert all(r['passed'] for r in receipts) and all(r['passed'] for r in extras)
finally:
 for p in children:
  if p.poll() is None:p.stdin.write('{"quit":true}\n');p.stdin.flush();p.wait(timeout=5)
 for command,p in zip(commands,children):command['exit_code']=p.returncode
(E/'receipts.json').write_text(json.dumps(receipts,indent=2));(E/'additional-criteria.json').write_text(json.dumps(extras,indent=2));(E/'commands.json').write_text(json.dumps(commands,indent=2));print(json.dumps({'canonical_passed':len(receipts),'extra_criteria_passed':len(extras),'owned_pids':[p.pid for p in children],'all_reaped':all(p.poll() is not None for p in children)}))
