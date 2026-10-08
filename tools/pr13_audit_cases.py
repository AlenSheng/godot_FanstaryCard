"""Execute the nine explicit PR13-A01 file/replay/denominator cases."""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import time

from pr13_audit_replay import replay, validate_derived, REDLINES
from gameplay_load_validation import provenance

ROOT=Path(__file__).resolve().parents[1]


def write(path,value):path.write_bytes((json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)+'\n').encode())


def fixture(root):
    rows=[dict(run_id='fixture',client_id='client',process_epoch='epoch',event_seq=i,
               cycle_id='client:1',match_id='match',event_type=kind,at_unix_ms=at)
          for i,kind,at in [(1,'settlement.acknowledged',99),(2,'cycle.completed',110)]]
    for i,status in enumerate([404,503],3):
        rows.append(dict(rows[0],event_seq=i,type='http',event_type='http',at_unix_ms=120,
                         path='/api/v1/settlements/context',duration_ms=10,status=status,ok=False))
    path=root/'events.jsonl';path.write_bytes(''.join(json.dumps(r)+'\n' for r in rows).encode())
    return {'files':[{'path':path.name,'bytes':path.stat().st_size,'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}]}


def action(number):
    with tempfile.TemporaryDirectory() as directory:
        root=Path(directory);manifest=fixture(root);before=(root/'events.jsonl').read_bytes()
        if number==2:manifest['files'][0]['sha256']='0'*64
        if number==3:(root/'events.jsonl').unlink()
        arguments={}
        if number==4:arguments['claimed_totals']={'running':{'completed_cycles':1}}
        if number==6:
            arguments['checks']=[{'client_id':str(i),'passed':False} for i in range(52)]
            arguments['checks'] += [{'client_id':str(i),'passed':False} for i in range(25)]
        if number==9:arguments['algorithm']='legacy-accounting'
        result=replay(root,manifest,stop_ms=100,final_ms=200,**arguments)
        if number==1:passed=result['status']=='Derived' and result['raw_read']
        elif number==2:passed=result['status']=='Blocked' and result['files'][0]['state']=='HashMismatchQuarantined' and (root/'events.jsonl').read_bytes()==before
        elif number==3:passed=result['status']=='Blocked' and not result['raw_read'] and result['derived'] is None
        elif number==4:passed=result['status']=='InvalidEvidence' and result['derived']['running']['completed_cycles']==0
        elif number==5:
            passed=(result['derived']['running']['completed_cycles']==0 and result['derived']['drain']['completed_cycles']==1
                    and [r['event_seq'] for r in result['event_differences'] if r['cutoff']=='drain' and r['event_type']=='cycle.completed']==[2])
        elif number==6:passed=result['check_denominators']=={'failed_clients':52,'failed_checks':77}
        elif number==7:
            edited=copy.deepcopy(result);edited['derived']['final']['completed_cycles']+=1
            try:validate_derived(edited,result);passed=False
            except ValueError:passed=True
            result={'original':result,'manually_edited':edited,'edit_rejected':passed}
        elif number==8:
            second=replay(root,manifest,stop_ms=100,final_ms=200)
            first_bytes=json.dumps(result,sort_keys=True,ensure_ascii=False).encode();second_bytes=json.dumps(second,sort_keys=True,ensure_ascii=False).encode()
            passed=first_bytes==second_bytes;result={'first_sha256':hashlib.sha256(first_bytes).hexdigest(),'second_sha256':hashlib.sha256(second_bytes).hexdigest(),'byte_stable':passed}
        else:
            current=replay(root,manifest,stop_ms=100,final_ms=200)
            passed=result['legacy_redlines']==REDLINES and result['legacy_request_statistics']['sample_count']==1 and result['algorithm']!=current['algorithm'] and current['legacy_redlines'] is None
            result={'current':current,'legacy':result,'source_raw_unchanged':(root/'events.jsonl').read_bytes()==before}
            passed=passed and result['source_raw_unchanged']
        return result,passed


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();output=args.output.resolve();output.mkdir(parents=True,exist_ok=False)
    plan_path=ROOT/'docs/plans/PR13_ACCEPTANCE_DETAILS_20260930.json';plan=json.loads(plan_path.read_text(encoding='utf8'))
    cases={c['id']:c for p in plan['packages'] for t in p['subtasks'] for c in t['test_cases']}
    ids=['PR13-A01.'+str(task)+'-T0'+str(case) for task in [1,3,4] for case in [1,2,3]]
    records=[]
    for number,case_id in enumerate(ids,1):
        row={'case_id':case_id,'executed':True,'setup':cases[case_id]['setup_and_injection'],'expected':cases[case_id]['expected'],
             'profiles_executed':['OFFLINE'],'scope':'Owned synthetic source files; does not recover deleted historical raw.','started_at':time.time()}
        try:
            actual,passed=action(number);row.update(actual=actual,status='Passed' if passed else 'Failed')
        except Exception as error:row.update(status='Failed',error=repr(error))
        records.append(row)
    source=provenance(ROOT,('tools/pr13_audit_replay.py','tools/pr13_audit_cases.py','tools/pr13_runtime_evidence.py','tools/cloud_load_test.py'))
    report={'source_sha':source['git_commit'],'source':source,'plan_sha256':hashlib.sha256(plan_path.read_bytes()).hexdigest(),
            'executed':len(records),'passed':sum(r['status']=='Passed' for r in records),'historical_recovery':False,'all_cases_accepted':False}
    (output/'cases.jsonl').write_bytes(''.join(json.dumps(r,ensure_ascii=False,allow_nan=False)+'\n' for r in records).encode())
    write(output/'report.json',report);print(json.dumps({k:report[k] for k in ['executed','passed','source_sha']}))
    return 0 if report['passed']==report['executed'] else 1


if __name__=='__main__':raise SystemExit(main())
