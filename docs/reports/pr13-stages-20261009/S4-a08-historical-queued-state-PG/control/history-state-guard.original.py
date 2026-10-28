import json
import sys
from pathlib import Path
from pr13_review_policy import execution_state,history_claim

C = Path('/control')
mode = sys.argv[1]
if mode=='historical-counts':
    actual = history_claim(191,62,raw_reconciled=False)
    assert actual['historical_passed']==191 and actual['historical_skipped']==62
    assert actual['current_passed']==0 and actual['runtime_revalidated'] is False
    assert actual['comparison_state']=='Blocked'
    inputs = {'historical_passed':191,'historical_skipped':62,'raw_reconciled':False,
              'input_authority':'Explicit controlled historical-count predicate from PR13-A08.2-T01'}
elif mode=='queued-fortyeight':
    queue = json.loads((C/'legacy-B-queue.original.json').read_bytes())
    tasks = [t for package in queue['tasks'] for t in package['subtasks']]
    assert len(tasks)==queue['subtask_count']==48
    assert all(t['state']=='Queued' and t['specification_state']=='ReviewReady' for t in tasks)
    observations = []
    for task in tasks:
        records = [{'executed':False,'status':'NotExecuted','case_id':task['id']+'-T'+str(i).zfill(2)} for i in range(1,4)]
        state = execution_state(records,['OFFLINE','POSTGRES'])
        assert state=='Queued'
        observations.append({'task_id':task['id'],'legacy_specification_state':task['specification_state'],
            'legacy_queue_state':task['state'],'controlled_execution_records':records,
            'actual_classification':state})
    actual = {'historical_queue_tasks':48,'actual_classifier_observations':observations,
              'controlled_current_passed':0,'current_real_B_register_was_not_reclassified':True}
    inputs = {'queue':'Exact current tracked legacy queue; not the current execution register',
              'execution':'Three explicitly absent controlled case records for each of all 48 tasks'}
elif mode=='unresolved-thirty':
    actual = history_claim(130,0,raw_reconciled=False)
    assert actual['historical_passed']==130 and actual['current_passed']==0
    assert actual['comparison_state']=='Blocked' and actual['runtime_revalidated'] is False
    actual = {**actual,'reported_other_cutoff_count':139,'raw_reconciliation_performed':False}
    inputs = {'reported_count':130,'reported_other_cutoff_count':139,'raw_reconciled':False,
              'input_authority':'Explicit controlled unresolved-count predicate from PR13-A08.2-T03'}
else:
    raise ValueError('Unknown frozen state classification mode')
print(json.dumps({'ok':True,'mode':mode,'actual_policy_output':actual,'declared_inputs':inputs,
    'scope':'Exact current review policy with declared historical/absent metadata faults; no actual 191/62 historical raw validation, current B48 acceptance, or 130/139 raw reconciliation'}))
