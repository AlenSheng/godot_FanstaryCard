from pathlib import Path
import datetime,hashlib,json,copy

b=Path(__file__).parent;repo=Path.cwd();out=b/'f01-skill-preparation-r1';assert not out.exists();out.mkdir()
private=Path(r'G:\PR13Evidence\private\season-balance-20261102-f03-google-r1');parent=private/'f01-calendar-r1/control.private.json';raw=parent.read_bytes();original=json.loads(raw)
assert original['Status']=='Completed' and original['NextIndex']==252 and len(original['Finished'])==252 and original['CurrentCase'] is None
actors=[a for a in original['Actors'] if a['Id'].startswith('F01-skilled-')];assert len(actors)==3 and all(not a['Censored'] for a in actors)
child_dir=private/'f01-skill-correction';assert not child_dir.exists();child_dir.mkdir()
(child_dir/'parent-control.private.original.json').write_bytes(raw)
state=copy.deepcopy(original);state.update(Task='season-balance-20261102-f01-skill-correction',NextIndex=0,CurrentCase=None,Status='Ready',Finished=[],Skipped=[],ManualLobbyResumeCase=None)
(child_dir/'control.private.json').write_text(json.dumps(state,indent=2)+'\n')
plan=dict(scope='F01 original skilled-account day15 correction only, no account/capital reset',attempts=[dict(id=a['Id']+'-D15-adaptive-gear-001',actor=a['Id'],day=15,shanghai_start_hour=9) for a in actors],
    maximum_new=3,F01_before=297,F01_after=300,F01_maximum=300,original252_and_support42_and_diagnostics3_retained=True,D03_new=0,B05_new=0)
plan_path=out/'plan.original.json';plan_path.write_text(json.dumps(plan,indent=2)+'\n')
policy=dict(scope=plan['scope'],legacy_rarity_only_policy_retained=True,new_policy='Skilled still takes Purple+; additionally take a strictly better Green/Blue starter piece. Existing60% heal safety and all mechanics unchanged.',
    new_policy_flag='acceptUsefulStarterGear',flag_default=False,corrected_cases=3,old_28_games_each_not_replayed=True,
    parent_control_sha256=hashlib.sha256(raw).hexdigest(),parent_schema=original['Schema'],same_actor_ids_and_balances=True,no_provisioning_or_grants=True,
    date='Original simulated day15 09:00',authority='Existing explicitly approved independent F01 maximum300, remaining3; no extra ceiling.',class15_not_evaluated_by_these_cases=True,
    at_utc=datetime.datetime.now(datetime.timezone.utc).isoformat())
policy_path=out/'policy.original.json';policy_path.write_text(json.dumps(policy,indent=2)+'\n')
path=repo/'docs/season-balance-20261102/F01-BUDGET.json';prior=path.read_bytes();budget=json.loads(prior);assert budget['used']==297 and budget['maximum']==300 and budget['current_handle'] is None
(out/'prior-budget.original.json').write_bytes(prior)
budget['skill_correction_plan']=dict(source=str(plan_path),sha256=hashlib.sha256(plan_path.read_bytes()).hexdigest(),planned_actual_starts=3,executed=False)
budget['skill_correction_policy']=dict(source=str(policy_path),sha256=hashlib.sha256(policy_path.read_bytes()).hexdigest(),executed=False)
path.write_text(json.dumps(budget,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps(dict(original_accounts=len(actors),same_schema=original['Schema'],planned_new=3,actual_new=0,F01_used=297,maximum=300,no_grants=True)))
