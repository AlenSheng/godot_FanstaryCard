from pathlib import Path
import datetime,hashlib,json

b=Path(__file__).parent;repo=Path.cwd();out=b/'d03-extra-budget-reply-r1';assert not out.exists();out.mkdir()
path=repo/'docs/season-balance-20261102/D03-BUDGET.json';prior=path.read_bytes();budget=json.loads(prior)
assert budget['used']==299 and budget['maximum']==300 and budget['current_handle'] is None
(out/'prior-budget.original.json').write_bytes(prior)
decision=dict(question_id='call_64057967dce54bb1a0e64a06f64c68d0',reply='上限调至308，按方案补9场（推荐）',
    received_at_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),prior_used=299,prior_maximum=300,new_maximum=308,approved_new_attempts=9,
    scenario='Water3/Fire2 twoPiercing/threeVitality +3, flow-loop, Mage/Priest/Guardian x seeds1553/1601/1699',
    class_ratio_limit=1.15,B05_new=0,old_evidence_retained=True,other_D03_growth_yield_sustainability_gaps_not_waived=True)
(out/'decision.original.json').write_text(json.dumps(decision,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
budget.update(maximum=308,remaining=9,original_maximum=300,additional_user_reply_received=True,
    additional_authorization_reference='explicit-user-reply-call_64057967dce54bb1a0e64a06f64c68d0-max308-nine-matched-cases',
    additional_authorization_source=str(out/'decision.original.json'),additional_authorized_new_attempts=9,
    prior_budget_before_extension=str(out/'prior-budget.original.json'),prior_budget_sha256=hashlib.sha256(prior).hexdigest())
path.write_text(json.dumps(budget,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
checkpoint=b/'current-journey-client-continuation-20261105.json';c=json.loads(checkpoint.read_bytes())
c['D03_additional_budget_request'].update(pending=False,approved=True,question_id=decision['question_id'],maximum=308,approved_new_attempts=9)
c['D03_matched_armor_preflight'].update(budget_approval_received=True,maximum=308)
c['current_blocker_audit'].update(request_blocked_status_after_final_live_audit=False,condition_resolved=True,reason='Explicit user extra-budget reply received; proceed with the frozen9 after source/resource checks.')
checkpoint.write_text(json.dumps(c,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');print(json.dumps(decision,ensure_ascii=False))
