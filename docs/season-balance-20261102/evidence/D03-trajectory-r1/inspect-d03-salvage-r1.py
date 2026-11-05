from pathlib import Path
import collections,hashlib,json

base=Path(__file__).parent;root=base/'d03-trajectory-salvage-r1';out=base/'d03-salvage-inspection-r1.derived.json';assert not out.exists();run=json.loads((root/'result.json').read_bytes());assert run['exit']==0 and run['actual_started']==18 and all(run[k] for k in ['source_unchanged','binary_unchanged','roster_identity_match','workbook_unchanged'])
p=root/'observations';rows=[json.loads(x) for x in (p/'routes.original.jsonl').read_text('utf-8').splitlines()];events=[json.loads(x) for x in (p/'events.original.jsonl').read_text('utf-8').splitlines()];assert len(rows)==18
prices={x['quality_id']:x for x in json.loads(Path('client/data/catalog.json').read_bytes())['tables']['SeasonEquipment']};profiles=[];source={};equips=0;crafts=0;total_spent=0
for directory in sorted(x for x in p.iterdir() if x.is_dir()):
    initial=json.loads((directory/'bank-import.original.json').read_bytes());final=json.loads((directory/'bank-final.original.json').read_bytes());rr=[r for r in rows if r['scenario']['Id'].startswith(initial['Id']+'-A')];assert len(rr)==2 and final['Attempts']==initial['Attempts']+2
    assert final['Gold']==final['GoldEarned'] and final['Fragments']==final['FragmentsEarned']-final['FragmentsSpent'] and min(final['Gold'],final['Fragments'],final['Blueprints'],final['OrangeBlueprints'])>=0
    assert not ({x['Item']['ItemId'] for x in final['Items']}&set(final['LostIds'])) and len(final['Items'])==len({x['Item']['ItemId'] for x in final['Items']})
    actions=[e for e in events if e['kind']=='bank' and e['Id']==initial['Id']];paid=blue_paid=orange_paid=0
    for action in actions:
        payload=action['payload']
        if action['action']=='enhance':
            a=payload['after'];b=payload['before'];eq=a['Item']['Equipment'];assert a['Item']['ItemId']==b['Item']['ItemId'] and a['Version']==b['Version']+1 and eq['Level']==b['Item']['Equipment']['Level']+1;assert payload['cost']==prices[eq['Quality'].lower()]['cost_'+str(eq['Level'])];paid+=payload['cost']
        if action['action']=='reforge':
            a=payload['after'];b=payload['before'];assert a['Item']['ItemId']==b['Item']['ItemId'] and a['Item']['Equipment']['Level']==0 and payload['cost'] in [1,2];paid+=payload['cost']
        if action['action']=='craft':
            blue_paid+=payload['payment']['Blueprints'];orange_paid+=payload['payment']['OrangeBlueprints'];assert payload['payment']['Blueprints']+payload['payment']['OrangeBlueprints']==(14 if payload['item']['Equipment']['Quality']=='Orange' else 4);crafts+=1
    assert final['Fragments']==initial['Fragments']-paid+sum(r['realizedFragments'] for r in rr) and final['FragmentsSpent']==initial['FragmentsSpent']+paid
    assert final['Gold']==initial['Gold']+sum(r['realizedGold'] for r in rr) and final['Blueprints']==initial['Blueprints']-blue_paid+sum(r['marks']['Blueprints'] for r in rr) and final['OrangeBlueprints']==initial['OrangeBlueprints']-orange_paid+sum(r['marks']['OrangeBlueprints'] for r in rr)
    for row in rr:
        sc=row['scenario'];number=int(sc['Id'].rsplit('-A',1)[1]);before=json.loads((directory/f'before-match-{number:02}.original.json').read_bytes());after=json.loads((directory/f'checkpoint-{number:02}.original.json').read_bytes());assert sc['AdaptiveEquipment'] and sc['EarlyExtract']==(sc['Difficulty']==0 and len(before['deployed'])<3)
        ee=[e for e in events if e.get('Id',e.get('scenario',e.get('result',{}).get('scenario',{})).get('Id'))==sc['Id']];start=next(e for e in ee if e['kind']=='start');assert row['snapshot']['Map']==start['map'];actor=row['snapshot']['Players'][0]
        if row['outcome']=='Extracted':
            end_gear=actor['WornArmor']+[x for x in actor['Inventory']['Items'] if x['Kind']==5];assert {x['Item']['ItemId'] for x in before['deployed']}.issubset({x['ItemId'] for x in end_gear});assert actor['ExtractionCompletedAt']==row['expectedExtraction']
        else:assert row['outcome']=='Dead' and actor['Combat']['Hp']==0 and row['realizedGold']==row['realizedFragments']==0
        for reward in [e for e in ee if e['kind']=='reward' and e.get('equipped')]:
            assert reward['selected']['Kind']==1;equips+=1
    assert final['FirstQualityAttempt'] is None and final['FirstReadyAttempt'] is None and final['FirstTargetAttempt'] is None
    profiles.append(dict(id=final['Id'],cohort=final['Cohort'],hero=final['Hero'],attempts=final['Attempts'],deaths=final['Deaths'],gold=final['Gold'],fragments=final['Fragments'],paid_fragments=paid,blueprints=final['Blueprints'],orange_blueprints=final['OrangeBlueprints'],owned=len(final['Items']),recipes=len(final['Recipes']),stop=final['StopReason']));total_spent+=paid
    for file in directory.glob('*'):
        if file.is_file():source[file.relative_to(base).as_posix()]=hashlib.sha256(file.read_bytes()).hexdigest()
budget=json.loads(Path('docs/season-balance-20261102/D03-BUDGET.json').read_bytes());assert budget['used']==72 and budget['remaining']==228 and budget['current_handle'] is None
result=dict(status='D03_bank_continuation_and_salvage_pilot_not_accepted',new_matches=18,outcomes=dict(collections.Counter(x['outcome'] for x in rows)),no_kit_reset=True,no_double_debit=True,paid_fragment_costs=total_spent,real_mark_crafts=crafts,actual_reward_equips=equips,three_ledger_balances_reconciled_for_this_finite_trace=True,longrun_sustainability_not_proven=True,first_set_all9_right_censored_at_attempt4=True,novice_all3_four_deaths_zero_capital=True,need_default_or_loan_deck_support_investigation=True,profiles=profiles,D03_complete=False,D03_used=72,D03_remaining=228,model_bank_not_new_PG=True,source_sha256=source)
out.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({k:v for k,v in result.items() if k not in ['source_sha256','profiles']}));print(json.dumps(profiles))
