"""Execute conservative delivery/history/candidate and human classification faults."""
import argparse
import json
from pathlib import Path
import subprocess
from pr13_render_cases import ROOT,sha,write
from pr13_review_policy import execution_state,candidate_matrix,deployment_claim,history_claim,asset_gate


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);args=p.parse_args();out=args.output.resolve();out.mkdir(parents=True,exist_ok=False)
    plan=ROOT/'docs/plans/PR13_ACCEPTANCE_DETAILS_20260930.json';contracts={c['id']:c for pkg in json.loads(plan.read_text(encoding='utf8'))['packages'] for t in pkg['subtasks'] for c in t['test_cases']};rows=[]
    def record(cid,actual,ok,**extra):rows.append(dict(case_id=cid,executed=True,status='Passed' if ok else 'Failed',setup=contracts[cid]['setup_and_injection'],expected=contracts[cid]['expected'],profiles_executed=['OFFLINE'],scope='Actual register/review classification with explicitly controlled absent/fault inputs; historical raw recovery, production rollback/health and human participation remain unverified',actual=actual,**extra))
    deployment=deployment_claim(pr_closed=True)
    record('LOAD-11.4-T02',deployment,deployment['runtime_rollback_verified'] is False and deployment['current_runtime_health']=='Unknown')
    historical=deployment_claim(restored_environment_hash='controlled-historical-restoration-hash')
    record('PR13-A08.4-T01',historical,historical['historical_environment_restoration_recorded'] and historical['current_runtime_health']=='Unknown')
    record('PR13-A08.4-T02',deployment,deployment['current_runtime_health']=='Unknown')
    history=history_claim(191,62)
    record('PR13-A08.2-T01',history,history['historical_passed']==191 and history['historical_skipped']==62 and history['current_passed']==0 and not history['runtime_revalidated'])
    queued=execution_state([dict(executed=False,status='NotExecuted')]*3,['OFFLINE'])
    record('PR13-A08.2-T02',dict(specification='ReviewReady',historical_B_tasks_queued=48,current_execution_state=queued),queued=='Queued')
    unresolved=history_claim(130,0,raw_reconciled=False)
    record('PR13-A08.2-T03',dict(unresolved,reported_upper_bound=139,raw_deleted_by_user=True),unresolved['comparison_state']=='Blocked' and unresolved['historical_passed']==130)
    failed=candidate_matrix(False,{},['fractional_guardian'])
    record('PR13-B12.2-T01',failed,failed['state']=='Failed' and not failed['production_activation'])
    absent=candidate_matrix(True,{},['cards_spent_draw','fractional_guardian','optional_monster_pool'])
    record('PR13-B12.2-T02',absent,absent['state']=='Blocked' and len(absent['missing_candidates'])==3)
    records=[dict(executed=True,status='Passed',profiles_executed=['OFFLINE','POSTGRES','LIVE','RENDER','EXPERIMENT'])]*3
    bot=execution_state(records,['OFFLINE','POSTGRES','LIVE','RENDER','EXPERIMENT'],human_required=True,
        human_evidence=dict(authority='MAIN',verified_source_files=['controlled-bot-log'],participants=[dict(participant_id=str(i),participant_kind='bot',hero_class=['Mage','Priest','Guardian'][i%3],skill_band='bot',natural_cycle_ids=['1','2','3']) for i in range(6)]))
    record('PR13-B12.2-T03',dict(all_machine_layers_controlled_passed=True,human_evidence_kind='bot_only',execution_state=bot,human_accepted=False),bot=='Partial')
    alerts=asset_gate([dict(id='controlled-asset-accounting-warning',explained=False)])
    record('PR13-B12.4-T03',alerts,alerts['state']=='Blocked' and not alerts['asset_acceptance'])
    delivery=json.loads((ROOT/'docs/plans/PR13_DELIVERY_DECISION_20261008.json').read_text(encoding='utf8'))
    register=json.loads((ROOT/'docs/reports/pr13-stages-20261008/S6-current-288/register.json').read_text(encoding='utf8'))
    unfinished=[t['task_id'] for t in register['tasks'] if t['state']!='Accepted']
    record('PR13-A08.4-T03',dict(current_local_register_unaccepted_tasks=unfinished,user_delivery_decision=delivery,all_accepted=register['all_accepted']),bool(unfinished) and register['all_accepted'] is False,
        expected_override='User-authorized local stage summary and direct release upload; unfinished list retained, draft writing waived.',override_source=dict(path='docs/plans/PR13_DELIVERY_DECISION_20261008.json',sha256=sha(ROOT/'docs/plans/PR13_DELIVERY_DECISION_20261008.json')))
    (out/'cases.jsonl').write_bytes(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in rows).encode());write(out/'report.json',dict(source_sha=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),plan_sha256=sha(plan),source=dict(scope='Controlled classification faults, plus actual current delivery decision and unfinished register',input_hashes={p:sha(ROOT/p) for p in ['tools/pr13_review_policy.py','tools/pr13_review_cases.py','tools/pr13_acceptance_register.py','docs/plans/PR13_DELIVERY_DECISION_20261008.json','docs/reports/pr13-stages-20261008/S6-current-288/register.json']}),executed=len(rows),passed=sum(r['status']=='Passed' for r in rows),accepted=False));print(json.dumps(dict(executed=len(rows),passed=sum(r['status']=='Passed' for r in rows))))
    return 0 if all(r['status']=='Passed' for r in rows) else 1


if __name__=='__main__':raise SystemExit(main())
