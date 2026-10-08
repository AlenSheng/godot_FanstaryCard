"""Explicit controlled statistical and comparison rejection cases, OFFLINE only."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
from pr13_candidate_review import paired_clusters,holm_adjust,gameplay_review,performance_review,tail_evidence,retain_default_decision,resource_gap_review

ROOT=Path(__file__).resolve().parents[1]
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def write(path,value):path.write_bytes((json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)+'\n').encode())

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',required=True,type=Path);args=p.parse_args();out=args.output.resolve();out.mkdir(parents=True,exist_ok=False)
    plan_path=ROOT/'docs/plans/PR13_ACCEPTANCE_DETAILS_20260930.json';contracts={c['id']:c for pkg in json.loads(plan_path.read_text(encoding='utf8'))['packages'] for task in pkg['subtasks'] for c in task['test_cases']};records=[]
    def record(cid,actual,passed):records.append({'case_id':cid,'executed':True,'status':'Passed' if passed else 'Failed','setup':contracts[cid]['setup_and_injection'],'expected':contracts[cid]['expected'],'actual':actual,'profiles_executed':['OFFLINE'],'scope':'Actual decision/statistical code with declared controlled inputs; native scenes, sampled experiments, capacity and human layers remain separate; no MAIN acceptance'})
    a=[{'seed':s,'battle':b,'value':10.0} for s in range(3) for b in range(4)]
    b=[dict(row,value=12.0+row['seed']) for row in a]
    paired=paired_clusters(a,b);repeat=paired_clusters(a,b)
    record('PR13-B03.3-T01',paired,paired['paired_battles']==12 and paired['independent_seed_clusters']==3)
    record('PR13-A06.4-T03',{'first':paired,'repeat':repeat,'controlled_three_paired_seed_clusters':True},paired==repeat and paired['mean_delta']==3)
    base={'source_config_hash':'frozen','request_mix_hash':'fixed','gameplay_profile':'original','effective_limit_hash':'default','window_seconds':600,'n':100,'request_rate':10,'error_rate':.01,'p95_ms':1000,'load_passed':True}
    higher=performance_review(base,dict(base,p95_ms=700,error_rate=.02))
    record('PR13-A06.4-T01',higher,higher['state']=='Inconclusive')
    for cid,key,value in [('PR13-A06.4-T02','source_config_hash','changed'),('PR13-A10.1-T01','request_mix_hash','changed'),('PR13-A10.1-T02','gameplay_profile','shorter-candidate'),('PR13-A10.1-T03','effective_limit_hash','temporary-override')]:
        result=performance_review(base,dict(base,**{key:value}))
        record(cid,result,result['state']=='DiagnosticOnly' and key in result['mismatched_inputs'])
    lower=performance_review(base,dict(base,p95_ms=700,request_rate=5))
    record('PR13-A10.4-T01',lower,lower['state']=='Inconclusive')
    record('LOAD-10.4-T02',lower,lower['state']=='Inconclusive')
    small=performance_review(base,dict(base,n=1,p95_ms=100))
    record('PR13-A10.4-T02',small,small['state']=='Unknown')
    tail=tail_evidence([10],quantile=.99,minimum_samples=3000)
    record('PR13-B01.4-T03',tail,tail['state']=='Unknown' and tail['value'] is None)
    args=dict(improvement=.15,interval=[-.05,.35],p_values={'tail':.04,'gap':.02,'secondary':.4},primary='tail',drifts={'victory_rate':.0,'resources_per_minute':.0})
    uncertain=gameplay_review(**args)
    record('PR13-B05.4-T01',uncertain,uncertain['state']=='Inconclusive' and not uncertain['production_activation'])
    drift=gameplay_review(**dict(args,drifts={'victory_rate':.0,'resources_per_minute':.051}))
    record('PR13-B05.4-T02',drift,drift['state']=='Blocked' and 'resources_per_minute' in drift['risk_drift'])
    record('PR13-B05.3-T01',drift,drift['drifts']['resources_per_minute']==.051 and drift['production_defaults_retained'])
    missing=gameplay_review(**dict(args,scenarios_complete=False))
    record('PR13-B05.3-T03',missing,missing['state']=='Blocked')
    mortality=gameplay_review(**dict(args,improvement=.5,interval=[.4,.6],drifts={'death_rate':.1}))
    record('PR13-B04.4-T01',mortality,mortality['state']=='Blocked')
    broken=gameplay_review(**dict(args,correctness=False))
    record('PR13-B04.4-T02',broken,broken['state']=='Failed')
    record('PR13-B05.1-T01',dict(broken,source_values_changed=False),broken['state']=='Failed' and broken['production_defaults_retained'])
    record('PR13-B03.4-T01',{'gameplay':gameplay_review(**dict(args,improvement=.2)),'capacity':performance_review(base,dict(base,gameplay_profile='shorter-candidate'))},performance_review(base,dict(base,gameplay_profile='shorter-candidate'))['state']=='DiagnosticOnly')
    no_benefit=gameplay_review(**dict(args,improvement=0,interval=[-.03,.02]))
    unchanged=retain_default_decision(no_benefit,evidence_complete=True)
    for cid in ['PR13-B04.4-T03','PR13-B09.4-T03']:
        record(cid,unchanged,unchanged['state']=='NoChangeWithEvidence' and unchanged['equivalence_claim'] is False and not unchanged['production_activation'])
    no_problem=retain_default_decision(no_benefit,observed_problem=False,evidence_complete=True)
    for cid in ['PR13-B04.2-T03','PR13-B05.4-T03','PR13-B08.4-T03','PR13-B11.3-T02']:
        record(cid,no_problem,no_problem['state']=='NoChangeWithEvidence' and no_problem['production_defaults_retained'])
    insufficient=retain_default_decision(gameplay_review(**dict(args,budget_met=False)),evidence_complete=False)
    record('PR13-B05.1-T03',insufficient,insufficient['state']=='Blocked' and not insufficient['production_activation'])
    pvp_fault=retain_default_decision(gameplay_review(**dict(args,correctness=False)))
    record('PR13-B05.3-T02',dict(pvp_fault,injected_fault='indirect_PVP_value_change'),pvp_fault['state']=='Failed')
    controlled_rounds=[performance_review(base,dict(base,p95_ms=1000+delta)) for delta in (2,1,3)]
    no_change_rounds=[retain_default_decision(review,evidence_complete=True) for review in controlled_rounds]
    for cid in ['LOAD-09.4-T03','PR13-A10.4-T03']:
        record(cid,{'controlled_rounds':controlled_rounds,'decisions':no_change_rounds,
            'measured_service_benefit_claim':False},all(r['state']=='NoChangeWithEvidence' and not r['production_activation'] for r in no_change_rounds))
    gap=resource_gap_review(dict(resource_per_card=1,no_cards_seconds=2),dict(resource_per_card=.5,no_cards_seconds=20))
    record('PR13-B06.4-T02',dict(gap,controlled_inputs=True,measured_gameplay_improvement_claim=False),gap['single_card_resource_decreased'] and 'empty_hand_wait_increased' in gap['side_effects'] and gap['production_activation'] is False)
    # The adjusted family is monotone in sorted p-values. A raw .04 primary
    # does not become significant when the other registered tests are retained.
    adjusted=holm_adjust({'tail':.04,'gap':.02,'secondary':.4})
    if adjusted!={'gap':.06,'tail':.08,'secondary':.4}:raise AssertionError('Holm family correction changed')
    (out/'cases.jsonl').write_bytes(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in records).encode())
    write(out/'report.json',{'source_sha':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),'plan_sha256':sha(plan_path),'source':{'scope':'controlled paired clusters/frozen comparison/benefit risk review','input_hashes':{p:sha(ROOT/p) for p in ('tools/pr13_candidate_review.py','tools/pr13_candidate_cases.py')}},'executed':len(records),'passed':sum(r['status']=='Passed' for r in records),'accepted':False})
    write(out/'manifest.json',{'files':[{'path':f.name,'bytes':f.stat().st_size,'sha256':sha(f)} for f in sorted(out.glob('*')) if f.is_file()]})
    print(json.dumps({'executed':len(records),'passed':sum(r['status']=='Passed' for r in records)}));return 0 if all(r['status']=='Passed' for r in records) else 1
if __name__=='__main__':raise SystemExit(main())
