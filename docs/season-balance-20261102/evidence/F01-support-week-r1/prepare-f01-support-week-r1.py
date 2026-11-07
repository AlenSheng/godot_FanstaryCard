from pathlib import Path
import datetime,hashlib,json,shutil

b=Path(__file__).parent;repo=Path.cwd();out=b/'f01-support-week-preparation-r1';assert not out.exists();out.mkdir()
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
members={x['path']:x for x in json.loads((repo/'docs/season-balance-20261102/evidence/F01-calendar-final-r1/original-archive-members.json').read_bytes())}
baseline=[]
for hero in ['Mage','Priest','Guardian']:
    paths=list((b/f'f01-calendar-r1/observations/F01-novice-{hero}-D01-A1').rglob('before.original.json'));assert len(paths)==1
    path=paths[0];relative=path.relative_to(b).as_posix();assert sha(path)==members[relative]['sha256']
    value=json.loads(path.read_bytes());cards=value['Checkpoint']['cards'];owned=[c for c in cards if c['Unlocked'] and c['CopyCount']>=1];assert len(owned)==51
    support=[{k:card[k] for k in ['CardId','Unlocked','CopyCount','Level']} for card in owned if card['CardId'] in ['C15','C16','C17','C18']]
    assert len(support)==4 and all(c['Level']==0 for c in support)
    baseline.append(dict(hero=hero,source=str(path),sha256=sha(path),owned_unlocked_cards=51,support_cards_already_owned=support,baseline_fixed_deck_size=20))
(out/'baseline-ownership-audit.original.json').write_text(json.dumps(dict(profiles=baseline,raw_SHA_matches_immutable_main_archive=True,source_initialization='PlayerProvisioningService.InsertStarterCardsAsync',new_accounts_have_51_initial_copies_not_only_default20=True,no_statement_that_all51_are_legal_for_one_hero=True,actual_new_encounters=0),indent=2)+'\n')
actors=[f'F01-support-novice-{hero}' for hero in ['Mage','Priest','Guardian']]
attempts=[dict(id=f'{actor}-D{day:02}-A{1 if hour==9 else 2}',actor=actor,day=day,shanghai_start_hour=hour) for day in range(1,8) for hour in [9,18] for actor in actors]
plan=dict(scope='F01 independent first-week owned-deck alternative, not a D03 Boss retry or replacement of the original252',config='season-v1-config-17',attempts=attempts,maximum_new=42,prior_total=255,projected_total=297,maximum=300,
    cards='Exact existing support-guard20; each card must actually be owned/unlocked at level0, saved through ProgressionRepository without SQL grants',cohort='novice',fresh_accounts=True,zero_season_capital=True,
    daily_attempts_per_profile=2,normal_original_match_seeds=True,reaction_seconds=1,old_failures_preserved=True,no_original_income_import_or_pooling=True,no_B05_or_D03_attempts=True)
plan_path=out/'plan.original.json';plan_path.write_text(json.dumps(plan,indent=2)+'\n')
policy=dict(scope=plan['scope'],profile_count=3,days=7,maximum_attempts=42,current_config=plan['config'],old_default20_baseline_preserved=True,
    ownership_proof='Three original day1 account snapshots + actual fresh provisioning/save-deck checks before the new calendar',
    deck_source='SeasonStarterSupportTests.Deck support-guard (all common initially unlocked cards)',
    source_values_unchanged=True,borrowed_template_unchanged=True,original_51_copies_not_granted_by_this_scenario=True,
    account_and_schema_separate=True,old_9_accounts_unchanged=True,old_D03_banks_unchanged=True,normal_Bot_PVE_PVP_and_actual_settlement=True,
    execution_model='Original persistent calendar controller, same novice risk/reaction/lobby; explicit first-week extension with its own case IDs and durable starts in the SAME F01 journal',
    budgets=dict(F01_maximum=300,F01_before=255,F01_planned_after=297,D03_unchanged=299,B05_unchanged=330),
    authority='Explicit user F01 independent budget maximum300; no additional F01 ceiling requested or inferred',created_utc=datetime.datetime.now(datetime.timezone.utc).isoformat())
policy_path=out/'policy.original.json';policy_path.write_text(json.dumps(policy,indent=2)+'\n')
budget_path=repo/'docs/season-balance-20261102/F01-BUDGET.json';prior=budget_path.read_bytes();budget=json.loads(prior);assert budget['used']==255 and budget['maximum']==300 and budget['current_handle'] is None and budget['approved'] and budget['additional_user_reply_received']
(out/'prior-budget.original.json').write_bytes(prior)
budget['support_week_plan']=dict(source=str(plan_path),sha256=sha(plan_path),planned_actual_starts=42,execution_started=False)
budget['support_week_policy']=dict(source=str(policy_path),sha256=sha(policy_path),executed=False)
budget_path.write_text(json.dumps(budget,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
checkpoint=b/'current-journey-client-continuation-20261105.json';shutil.copyfile(checkpoint,out/'checkpoint-before-new-independent-action.original.json');c=json.loads(checkpoint.read_bytes())
c['current_blocker_audit'].update(request_blocked_status_after_final_live_audit=False,remaining_authorized_preparation_complete=False,reason='New authoritative ownership finding exposes an independent F01 first-week alternative within the already approved remaining45; meaningful safe work remains. Do not mark goal blocked.')
c['F01_support_week']=dict(plan=str(plan_path),policy=str(policy_path),preparation=str(out),scope='Fresh novices choose existing support cards using real save-deck,7days42starts within originalF01 max300',executed=False)
c.update(worktree_clean=False,all_own_test_handles_terminal=True,pending_test_handles=[])
checkpoint.write_text(json.dumps(c,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps(dict(owned_cards_confirmed=51,baseline_profiles=3,planned_F01_new=42,projected_F01_total=297,D03_new=0,B05_new=0,actual_new_starts=0)))
