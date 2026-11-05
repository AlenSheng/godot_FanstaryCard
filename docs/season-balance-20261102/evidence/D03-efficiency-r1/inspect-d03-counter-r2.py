from pathlib import Path
import collections,hashlib,json,math,statistics

base=Path(__file__).parent;root=base/'d03-counter-pilot-r1';out=base/'d03-counter-inspection-r2.derived.json';assert not out.exists()
run=json.loads((root/'result.json').read_bytes());assert run['exit']==0 and run['actual_started']==12 and all(run[k] for k in ['roster_identity_match','source_unchanged','binary_unchanged','workbook_unchanged'])
p=root/'observations';rows=[json.loads(x) for x in (p/'encounters.original.jsonl').read_text('utf-8').splitlines()];events=[json.loads(x) for x in (p/'events.original.jsonl').read_text('utf-8').splitlines()];assert len(rows)==12
casts=resources=0;all_wins=True
for row in rows:
    scenario=row['row'];ee=[x for x in events if x.get('Id',x.get('row',x.get('result',{}).get('row',{})).get('Id'))==scenario['Id']];start=ee[0];assert start['kind']=='start' and ee[-1]['kind']=='end' and ee[-1]['result']==row
    assert start['Version']=='season-v1-config-15' and start['ContentHash']=='2bc11db4b287055d119aceda45deeeb6fb00c3df524b3acad9887deaa04d9d8a'
    aa=[x for x in ee if x['kind']=='cast'];rr=[x for x in ee if x['kind']=='resource'];assert len(aa)==row['casts'] and sum(x['previews'] for x in aa)==row['previews']
    assert all(1<=x['previews']<=3 and not x['result']['ActionReplayed'] and 1<=x['candidates']<=155 for x in aa)
    assert all(y['seconds']-x['seconds']>=.5-1e-9 for x,y in zip(aa,aa[1:]));assert row['damage']==sum(x['result']['HpDamage']+x['result']['ShieldDamage'] for x in aa)
    for x in rr:assert x['hpDelta']==x['hpAfter']-x['hpBefore']+x['hpDamage'] and x['shieldDelta']==x['shieldAfter']-x['shieldBefore']+x['shieldDamage']
    expected={'addedHp':sum(max(0,x['hpDelta']) for x in rr),'addedShield':sum(max(0,x['shieldDelta']) for x in rr),'otherHpLoss':sum(max(0,-x['hpDelta']) for x in rr),'discardedShield':sum(max(0,-x['shieldDelta']) for x in rr)};assert all(row[k]==v for k,v in expected.items())
    assert row['damage']==row['initialHp']+row['initialShield']+row['addedHp']+row['addedShield']-row['otherHpLoss']-row['discardedShield']-row['remainingHp']-row['remainingShield']
    hp={'Mage':70,'Priest':80,'Guardian':100}[scenario['Hero']];cap=min(math.floor(hp*1.4),math.floor(hp*(1+start['player']['Combat']['Equipment']['VitalityOvercapBonus'])))
    assert all(0<x['hpBefore']<=cap and 0<x['hpAfter']<=cap and 0<=x['shield']<=hp//2 for x in aa)
    assert all(x['Equipment']['Level']==3 and x['Equipment']['Quality']!='Red' for x in start['gear'])
    all_wins&=row['outcome']=='Win';casts+=len(aa);resources+=len(rr)
comparisons=[]
for deck in ['counter-tempo','universal-tempo']:
    for armor in ['counter-offense']:
        medians={}
        for hero in ['Mage','Priest','Guardian']:
            selected=[r for r in rows if r['row']['Hero']==hero and r['row']['Deck']==deck and r['row']['Armor']==armor];assert len(selected)==2 and {r['row']['Seed'] for r in selected}=={73,137};medians[hero]=statistics.median(r['seconds'] for r in selected if r['outcome']=='Win')
        matched=[r for r in rows if r['row']['Deck']==deck and r['row']['Armor']==armor];all_success=all(r['outcome']=='Win' for r in matched);ratio=max(medians.values())/min(medians.values());comparisons.append(dict(deck=deck,armor=armor,conditional_win_median_seconds=medians,conditional_class_ratio=ratio,all_matched_cases_win=all_success,censored_failed_cases=[r['row']['Id'] for r in matched if r['outcome']!='Win'],original_class15_passed=all_success and ratio<=1.15,boss75_120_all_passed=all_success and all(75<=v<=120 for v in medians.values())))
all_class_targets_passed=all(x['original_class15_passed'] for x in comparisons)
budget=json.loads(Path('docs/season-balance-20261102/D03-BUDGET.json').read_bytes());assert budget['used']==36 and budget['remaining']==264 and budget['current_handle'] is None
result=dict(status='D03_counter_development12_observed_not_final_acceptance',new_encounters=12,outcomes=dict(collections.Counter(r['outcome'] for r in rows)),independently_checked_casts=casts,resource_events=resources,readonly_forecast_and_preview_assertions_passed=True,all_legal_health=True,no_red_and_armor3=True,
    comparisons=comparisons,development_seeds_only=True,not_final_holdout=True,original_class_targets_passed=all_class_targets_passed,
    D03_complete=False,D03_used=36,D03_remaining=264,targets_relaxed=False,population_P50_P90_complete=False,sustainable_three_ledgers_complete=False,production_or_cloud_modified=False,
    next_action='Counterclass tempo reaches D5Boss median75-120, but class ratio1.545 still fails15. Need independent holdout/normal-elite/route/cohort economy and class balance solution; never count death time as clear time or slow Mage deliberately.',prior_derived_r1_scope_error='Conditional clear medians initially included failed130.5s forPriestuniversal; originals unchanged. r2 excludesfailurefromclear-time medians and requires allmatchedcasesWin for any efficiency/range pass.',
    source_sha256={f.relative_to(base).as_posix():hashlib.sha256(f.read_bytes()).hexdigest() for f in [root/'result.json',p/'attempts.original.jsonl',p/'encounters.original.jsonl',p/'events.original.jsonl']})
out.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({k:v for k,v in result.items() if k not in ['source_sha256','comparisons']}));print(json.dumps(comparisons))
