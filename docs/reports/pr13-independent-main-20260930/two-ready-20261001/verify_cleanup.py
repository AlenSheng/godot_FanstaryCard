"""Only remove owned stopped throwaway PostgreSQL directories after replay completes."""
import collections,hashlib,json,pathlib,re,shutil
B=pathlib.Path(__file__).resolve().parent;E=B/'evidence';out=[];pids=set()
assert (E/'load02-PG-STOP.json').exists(),'Replay must finish first.'
for run in ['A05-RED','A05-SERVER299','LOAD02-FOCUSED','LOAD02-SERVER302']:
    rows=[json.loads(x) for x in (E/run/'receipts.jsonl').read_text().splitlines()]
    starts=[x['evidence']['Id'] for x in rows if x['caseId']=='process-start'];stops=[x['evidence'] for x in rows if x['caseId']=='process-stop']
    assert len(starts)==len(stops) and set(starts)=={x['ProcessId'] for x in stops},(run,'host PID sets differ')
    assert all(x['ExitCode']==137 for x in stops)
    children=[x['evidence'] for x in rows if x['caseId'] in ['A05-client-stop','LOAD02-process-exit','ack-client-process-stop','ack-runner-process-stop']]
    for x in stops+children:
        pid=x.get('ProcessId',x.get('Id'));assert pid is not None,(run,x);pids.add(pid)
    out.append({'run':run,'raw_receipts':len(rows),'host_start_stop':[len(starts),len(stops)],'exact_host_PID_sets_match':True,'all_host_stop_137':True,'Godot_exit_receipts':len(children),'Godot_exit_counts':dict(collections.Counter(x['ExitCode'] for x in children)),'not_readjudicating_other_tasks':True})
states=[]
for pid in sorted(pids):
    p=pathlib.Path('/proc')/str(pid)/'stat'
    if p.exists():
        s=p.read_text().rsplit(')',1)[1].split()[0];assert s=='Z',(pid,'recorded child still active',s);state='ExitedZombie; not listening/running; do not touch PID1'
    else:state='Absent/exited'
    states.append({'pid':pid,'state':state})
pg=[]
for name in ['a05','load02']:
    receipt=json.loads((E/(name+'-PG-STOP.json')).read_text());assert receipt['final_readonly_exit']==receipt['stop_exit']==0 and receipt['status_after_stop_exit']==3
    log=(E/(name+'-final-readonly.log')).read_text();assert len(re.findall(r'\n\s+0\n',log))==2
    data=B/(name+'-pg');sock=B/(name+'-socket');assert not (data/'postmaster.pid').exists()
    assert data.parent==sock.parent==B and data.name==name+'-pg' and sock.name==name+'-socket'
    shutil.rmtree(data);shutil.rmtree(sock)
    pg.append({'name':name,'final_readonly_exit':0,'owned_schemas':0,'other_connections':0,'stop_exit':0,'status_after_stop_exit':3,'owned_data_socket_removed':not data.exists() and not sock.exists(),'final_readonly_log_sha256':hashlib.sha256((E/(name+'-final-readonly.log')).read_bytes()).hexdigest(),'raw_stop_receipt_data_retention_flag':'Historical at stop; superseded by this later owned directory removal receipt.'})
r={'status':'Passed','runs':out,'recorded_child_states':states,'owned_PG':pg,'unrelated_process_or_PID1_changes':False,'raw_and_review_preserved':True}
(B/'CLEANUP_CHECKS.json').write_text(json.dumps(r,indent=2)+'\n')
print(json.dumps({'cleanup':'Passed','runs':out,'recorded_children':len(states),'all_children_inactive':True,'owned_PG_data_socket_removed':2}))
