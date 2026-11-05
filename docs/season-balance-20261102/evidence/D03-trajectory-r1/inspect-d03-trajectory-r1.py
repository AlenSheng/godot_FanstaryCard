from pathlib import Path
import collections,hashlib,json

base=Path(__file__).parent;root=base/'d03-trajectory-r1';out=base/'d03-trajectory-inspection-r1.derived.json';assert not out.exists();run=json.loads((root/'result.json').read_bytes());assert run['exit']==0 and run['actual_started']==9 and all(run[k] for k in ['source_unchanged','binary_unchanged','roster_identity_match','workbook_unchanged'])
p=root/'observations';rows=[json.loads(x) for x in (p/'routes.original.jsonl').read_text('utf-8').splitlines()];assert len(rows)==9;reports=[];source={}
tables=json.loads(Path('client/data/catalog.json').read_bytes())['tables'];prices={x['quality_id']:x for x in tables['SeasonEquipment']}
events=[json.loads(x) for x in (p/'events.original.jsonl').read_text('utf-8').splitlines()]
for row in rows:
    sc=row['scenario'];track=sc['Id'].rsplit('-A',1)[0];directory=p/track;initial=json.loads((directory/'bank-import.original.json').read_bytes());before=json.loads((directory/'before-match-02.original.json').read_bytes());final=json.loads((directory/'bank-final.original.json').read_bytes());snapshot=row['snapshot'];actor=snapshot['Players'][0]
    assert initial['Attempts']==1 and final['Attempts']==2 and initial['Id']==final['Id']==track
    assert final['Gold']==final['GoldEarned'] and final['Fragments']==final['FragmentsEarned']-final['FragmentsSpent'] and min(final['Gold'],final['Fragments'],final['Blueprints'],final['OrangeBlueprints'])>=0
    assert len(final['Items'])==len({x['Item']['ItemId'] for x in final['Items']}) and not ({x['Item']['ItemId'] for x in final['Items']}&set(final['LostIds']))
    old_ids={x['Item']['ItemId'] for x in initial['Items']};deployed={x['Item']['ItemId'] for x in before['deployed']};assert deployed.issubset(old_ids)
    if initial['Deaths']==1:
        assert initial['Items']==[] and before['deployed']==[] and sc['Difficulty']==0
    actions=[e for e in events if e['kind']=='bank' and e['Id']==track];spent=0
    for action in actions:
        if action['action']=='enhance':
            payload=action['payload'];b=payload['before'];a=payload['after'];assert b['Item']['ItemId']==a['Item']['ItemId'] and a['Version']==b['Version']+1
            eq0=b['Item']['Equipment'];eq1=a['Item']['Equipment'];assert eq1['Level']==eq0['Level']+1;assert payload['cost']==prices[eq0['Quality'].lower()]['cost_'+str(eq1['Level'])];spent+=payload['cost']
        elif action['action']=='reforge':spent+=action['payload']['cost']
    assert spent==final['FragmentsSpent']-initial['FragmentsSpent'] and final['Fragments']==initial['Fragments']-spent+row['realizedFragments'] and final['Gold']==initial['Gold']+row['realizedGold']
    assert final['Blueprints']==initial['Blueprints']+row['marks']['Blueprints'] and final['OrangeBlueprints']==initial['OrangeBlueprints']+row['marks']['OrangeBlueprints']
    if row['outcome']=='Extracted':assert actor['Phase']==5 and final['Deaths']==initial['Deaths']
    else:assert row['outcome']=='Dead' and actor['Combat']['Hp']==0 and final['Deaths']==initial['Deaths']+1 and row['realizedGold']==row['realizedFragments']==0
    assert final['FirstQualityAttempt'] is None and final['FirstReadyAttempt'] is None and final['FirstTargetAttempt'] is None
    reports.append(dict(track=track,cohort=initial['Cohort'],hero=initial['Hero'],difficulty=sc['Difficulty'],worn=len(deployed),outcome=row['outcome'],gold=final['Gold'],fragments=final['Fragments'],lobby_fragments_paid=spent,owned=len(final['Items']),deaths=final['Deaths'],stop=final['StopReason']))
    for file in directory.glob('*'):
        if file.is_file():source[file.relative_to(base).as_posix()]=hashlib.sha256(file.read_bytes()).hexdigest()
budget=json.loads(Path('docs/season-balance-20261102/D03-BUDGET.json').read_bytes());assert budget['used']==54 and budget['remaining']==246 and budget['current_handle'] is None
result=dict(status='D03_persistent_bank_first_continuation_verified_not_accepted',new_matches=9,outcomes=dict(collections.Counter(x['outcome'] for x in rows)),all_prior_dead_banks_no_free_armor=True,real_item_IDs_carried_and_lost_stay_lost=True,fragments_paid_actual_lobby=sum(x['lobby_fragments_paid'] for x in reports),no_death_double_debit=True,profiles=reports,
    first_set_quantiles_still_censored=True,none_of9_formed_quality_ready_or_strict_set_by_attempt2=True,model_bank_not_new_PG_execution=True,D03_complete=False,D03_used=54,D03_remaining=246,source_sha256=source)
out.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({k:v for k,v in result.items() if k!='source_sha256'}))
