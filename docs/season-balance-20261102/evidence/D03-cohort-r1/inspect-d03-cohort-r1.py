from pathlib import Path
import collections,hashlib,json,math

base=Path(__file__).parent;root=base/'d03-cohort-r1';out=base/'d03-cohort-inspection-r1.derived.json';assert not out.exists()
run=json.loads((root/'result.json').read_bytes());assert run['exit']==0 and run['actual_started']==9 and all(run[k] for k in ['roster_identity_match','source_unchanged','binary_unchanged','workbook_unchanged'])
p=root/'observations';rows=[json.loads(x) for x in (p/'routes.original.jsonl').read_text('utf-8').splitlines()];attempts=[json.loads(x) for x in (p/'attempts.original.jsonl').read_text('utf-8').splitlines()];events=[json.loads(x) for x in (p/'events.original.jsonl').read_text('utf-8').splitlines()];assert len(rows)==len(attempts)==9
casts=resources=kills=0;summaries=[]
for row,attempt in zip(rows,attempts,strict=True):
    sc=row['scenario'];assert sc==attempt;ee=[x for x in events if x.get('Id',x.get('scenario',x.get('result',{}).get('scenario',{})).get('Id'))==sc['Id']];start=ee[0];assert start['kind']=='start' and ee[-1]['result']==row
    assert start['Version']=='season-v1-config-15' and start['ContentHash']=='2bc11db4b287055d119aceda45deeeb6fb00c3df524b3acad9887deaa04d9d8a'
    path=start['path'];assert len(path)==8 and path[0]==dict(Row=0,Column=0) and path[-1]==dict(Row=2,Column=3) and row['snapshot']['Map']==start['map']
    cells={(x['Position']['Row'],x['Position']['Column']):x for x in start['map']['Cells']}
    for a,b in zip(path,path[1:]):assert abs(a['Row']-b['Row'])+abs(a['Column']-b['Column'])==1 and cells[(b['Row'],b['Column'])]['Layer']>=cells[(a['Row'],a['Column'])]['Layer']
    own=start['player'];assert own['Inventory']['Capacity']==20 and own['Inventory']['SafeSlots']==0 and own['Inventory']['Items']==[]
    assert len(own['WornArmor'])==5 and all(x['Equipment']['Quality']=='Blue' and x['Equipment']['Level']==1 and x['Equipment']['EffectAffix'] is None for x in own['WornArmor'])
    aa=[x for x in ee if x['kind']=='cast'];assert len(aa)==row['casts'];spacing={'novice':1,'returning':.7,'skilled':.5}[sc['Cohort']]
    assert all(y['seconds']-x['seconds']>=spacing-1e-9 for x,y in zip(aa,aa[1:]));assert all(not x['resolution']['ActionReplayed'] and 1<=x['previews']<=3 for x in aa)
    bs=[x for x in ee if x['kind']=='encounter-start'];be=[x for x in ee if x['kind']=='encounter-end'];assert len(bs)==len(be)
    for s,e in zip(bs,be,strict=True):
        index=s['pathIndex'];assert index==e['pathIndex'];rr=[x for x in ee if x['kind']=='resource' and x['pathIndex']==index];ac=[x for x in aa if x['pathIndex']==index]
        for x in rr:assert x['hpDelta']==x['hpAfter']-x['hpBefore']+x['hpDamage'] and x['shieldDelta']==x['shieldAfter']-x['shieldBefore']+x['shieldDamage']
        assert e['damage']==sum(x['resolution']['HpDamage']+x['resolution']['ShieldDamage'] for x in ac)
        assert e['damage']==e['initialHp']+e['initialShield']+e['hpAdded']+e['shieldAdded']-e['hpOtherLoss']-e['shieldDiscarded']-e['remainingHp']-e['remainingShield'];resources+=len(rr)
    assert row['totalDamage']==sum(x['damage'] for x in be);assert row['kills']==sum(x['resolution']['TargetDefeated'] for x in aa)
    final=row['snapshot']['Players'][0];assert row['potions']==0
    if row['outcome']=='Extracted':
        assert final['Phase']==5 and final['ExtractionCompletedAt']==row['expectedExtraction'] and row['clears']==8 and row['recoveredExtraction']
        inv=final['Inventory']['Items'];assert row['realizedGold']==sum(x['Quantity'] for x in inv if x['Kind']==0) and row['realizedFragments']==sum(x['Quantity'] for x in inv if x['Kind']==3)
        assert row['marks']==dict(Blueprints=0,OrangeBlueprints=3) and row['lostBlueBodies']==row['lostEnhancementInvestment']==0
    else:
        assert row['outcome']=='Dead' and final['Phase']==4 and final['Combat']['Hp']==0 and row['realizedGold']==row['realizedFragments']==0
        assert row['marks']==dict(Blueprints=0,OrangeBlueprints=0) and row['lostBlueBodies']==5 and row['lostEnhancementInvestment']==10
        pile=next(x for x in row['snapshot']['RelicPiles'] if x['VictimId']==own['PlayerId']);assert {x['ItemId'] for x in own['WornArmor']}.issubset({x['ItemId'] for x in pile['Items']});inv=[]
    equipment=[x['Equipment'] for x in inv if x['Kind']==5];bodies=dict(collections.Counter(x['Quality'] for x in equipment))
    summaries.append(dict(scenario=sc,outcome=row['outcome'],seconds=row['seconds'],gold_credited=row['realizedGold'],fragments_credited=row['realizedFragments'],orange_marks_credited=row['marks']['OrangeBlueprints'],equipment_bodies_credited=bodies,blue_bodies_lost=row['lostBlueBodies'],historical_enhancement_investment_lost=row['lostEnhancementInvestment'],conditional_fragment_replacement_surplus=row['realizedFragments']-row['lostEnhancementInvestment']))
    casts+=len(aa);kills+=row['kills']
groups=[]
for cohort in ['novice','returning','skilled']:
    rr=[x for x in summaries if x['scenario']['Cohort']==cohort];assert len(rr)==3;elapsed=sum(x['seconds'] for x in rr);bodies=collections.Counter()
    for r in rr:bodies.update(r['equipment_bodies_credited'])
    groups.append(dict(cohort=cohort,independent_oneattempt_profiles=3,outcomes=dict(collections.Counter(x['outcome'] for x in rr)),seconds_including_deaths=elapsed,gold=sum(x['gold_credited'] for x in rr),fragments=sum(x['fragments_credited'] for x in rr),orange_marks=sum(x['orange_marks_credited'] for x in rr),credited_bodies=dict(bodies),blue_body_loss=sum(x['blue_bodies_lost'] for x in rr),historical_fragment_loss=sum(x['historical_enhancement_investment_lost'] for x in rr),conditional_fragment_surplus=sum(x['conditional_fragment_replacement_surplus'] for x in rr),gold_per_simulated_hour=sum(x['gold_credited'] for x in rr)*3600/elapsed,first_set_P50=None,first_set_P90=None))
budget=json.loads(Path('docs/season-balance-20261102/D03-BUDGET.json').read_bytes());assert budget['used']==45 and budget['remaining']==255 and budget['current_handle'] is None
result=dict(status='D03_R1_entry_cohort_stream_pilot_not_population_or_sustainability_acceptance',new_routes=9,outcomes=dict(collections.Counter(x['outcome'] for x in rows)),casts=casts,resource_events=resources,kills=kills,one_generated_layout_seed=73179,initial_blue_kit_is_explicit_preowned_not_free_replacement=True,body_loss_is_not_destroyed_world_supply=True,model_cohorts_not_human_observations=True,independent_oneattempts_not_persistent_trajectories=True,profiles=summaries,cohorts=groups,
    D03_complete=False,D03_used=45,D03_remaining=255,first_set_quantiles_not_measured=True,long_run_sustainable_three_ledgers_not_proven=True,failed_D2novice_entry_needs_lower_risk_fallback_or_progression=True,source_sha256={f.relative_to(base).as_posix():hashlib.sha256(f.read_bytes()).hexdigest() for f in [root/'result.json',p/'attempts.original.jsonl',p/'routes.original.jsonl',p/'events.original.jsonl']})
out.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({k:v for k,v in result.items() if k not in ['profiles','source_sha256']}))
