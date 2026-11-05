from pathlib import Path
import collections, hashlib, json, math, sys

base=Path(__file__).parent;families=sys.argv[1:];assert families and all(x in ['growth','groups','effects','boxelements'] for x in families)
target=base/('d01-inspection-'+'-'.join(families)+'-r2.derived.json');assert not target.exists()
combined=[];total_casts=0;total_kills=0;total_changes=0;shas={}
for family in families:
    root=base/('d01-'+family+'-r1');run=json.loads((root/'result.json').read_bytes())
    assert run['exit']==0 and run['started_encounters']==run['planned_encounters'] and all(run[x] for x in ['source_unchanged','binary_unchanged','workbook_unchanged','roster_identity_match'])
    expected=json.loads((root/'roster.original.json').read_bytes())['cases'];p=root/'observations'
    rows=[json.loads(x) for x in (p/'encounters.original.jsonl').read_text('utf-8').splitlines()]
    attempts=[json.loads(x) for x in (p/'attempts.original.jsonl').read_text('utf-8').splitlines()]
    events=[json.loads(x) for x in (p/'events.original.jsonl').read_text('utf-8').splitlines()]
    assert len(rows)==len(attempts)==len(expected)==run['started_encounters']
    grouped=collections.defaultdict(list)
    for event in events:
        identifier=event['row']['Id'] if event['kind']=='start' else event['result']['row']['Id'] if event['kind']=='end' else event['Id']
        grouped[identifier].append(event)
    assert set(grouped)=={x['row']['Id'] for x in rows}
    for row,attempt,case in zip(rows,attempts,expected,strict=True):
        case_row=row['row'];identifier=case_row['Id'];assert case_row==attempt and identifier==case['id'];ee=grouped[identifier]
        assert ee[0]['kind']=='start' and ee[-1]['kind']=='end' and ee[0]['row']==case_row and ee[-1]['result']==row
        start=ee[0];assert start['Version']=='season-v1-config-15' and start['ContentHash']=='2bc11db4b287055d119aceda45deeeb6fb00c3df524b3acad9887deaa04d9d8a'
        casts=[x for x in ee if x['kind']=='cast'];changes=[x for x in ee if x['kind']=='resource'];assert len(casts)==row['casts']
        assert all(y['seconds']-x['seconds']>=.5-1e-9 for x,y in zip(casts,casts[1:]));assert all(not x['resolution']['ActionReplayed'] for x in casts)
        assert len({x['resolution']['CombatActionId'] for x in casts})==len(casts)
        assert sum(x['resolution']['HpDamage']+x['resolution']['ShieldDamage'] for x in casts)==row['totalDamage']
        for event in changes:
            assert event['hpDelta']==event['hpAfter']-event['hpBefore']+event['hpDamage'] and event['shieldDelta']==event['shieldAfter']-event['shieldBefore']+event['shieldDamage']
        sums={'hpAdded':sum(max(0,x['hpDelta']) for x in changes),'shieldAdded':sum(max(0,x['shieldDelta']) for x in changes),'hpOtherLoss':sum(max(0,-x['hpDelta']) for x in changes),'shieldDiscarded':sum(max(0,-x['shieldDelta']) for x in changes)}
        assert all(row[n]==v for n,v in sums.items())
        assert row['totalDamage']==row['initialHp']+row['initialShield']+row['hpAdded']+row['shieldAdded']-row['hpOtherLoss']-row['shieldDiscarded']-row['remainingHp']-row['remainingShield']
        base_hp={'Mage':70,'Priest':80,'Guardian':100}[case_row['Hero']];maximum=min(math.floor(base_hp*1.4),math.floor(base_hp*(1+start['Equipment']['VitalityOvercapBonus'])))
        assert start['startingCombat']['MaximumHp']==base_hp and start['startingCombat']['Hp']==max(1,base_hp*case_row['HpPercent']//100)
        assert all(0<=x['hpBefore']<=maximum and 0<=x['hpAfter']<=maximum and 0<=x['shieldBefore']<=base_hp//2 and 0<=x['shieldAfter']<=base_hp//2 for x in casts)
        initial_deck=start['startingCombat']['Deck'];initial_cards=initial_deck['Hand']+initial_deck['Library']+initial_deck['Discard'];assert len(initial_cards)==20+case_row['MonsterCards']
        assert all(x['Level']==0 for x in initial_cards if x['CardId'].startswith('M-'))
        actual_kills=sum(x['resolution']['TargetDefeated'] for x in casts);assert actual_kills==row['kills']
        for cast in casts:
            assert len(cast['added'])==(1 if cast['resolution']['TargetDefeated'] else 0)
            assert all(x['Level']==0 and x['CardId'].startswith('M-') for x in cast['added'])
        assert row['effectiveLevel']==min(case_row['Growth'],case_row['Difficulty'])
        assert row['outcome'] in ['Win','Dead','Timeout'] and 0<=row['seconds']<=600
        if row['outcome']=='Win':assert row['remainingHp']==row['remainingShield']==0 and row['endingHp']>0
        if row['outcome']=='Dead':assert row['endingHp']==0
        if row['outcome']=='Timeout':assert row['seconds']==600
        total_casts+=len(casts);total_kills+=actual_kills;total_changes+=len(changes);combined.append(row)
    for file in [root/'result.json',root/'roster.original.json',p/'attempts.original.jsonl',p/'encounters.original.jsonl',p/'events.original.jsonl']:
        shas[file.relative_to(base).as_posix()]=hashlib.sha256(file.read_bytes()).hexdigest()
result=dict(families=families,encounters=len(combined),outcomes=dict(collections.Counter(x['outcome'] for x in combined)),independently_checked_casts=total_casts,actual_species_kills=total_kills,resource_changes=total_changes,original_sha256=shas,
    resource_conservation=True,legal_hp_and_shield=True,successful_cast_interval_at_least500ms=True,monster_base0_addition=True,prior_monster_pool_is_fixture_not_previous_route=True,
    growth_class_difficulty_combinations=len({(x['row']['Hero'],x['row']['Growth'],x['row']['Difficulty']) for x in combined if x['row']['Family']=='growth'}),
    group_difficulty_combinations=len({(x['row']['Group'],x['row']['Difficulty']) for x in combined if x['row']['Family']=='groups'}),
    effect_class_health_combinations=len({(x['row']['Variant'],x['row']['Hero'],x['row']['HpPercent']) for x in combined if x['row']['Family']=='effects'}),
    no_terminal_evidence_for_timeouts=any(x['outcome']=='Timeout' for x in combined),D03_not_accepted=True,D02_routes_not_accepted=True,capacity100_retest=False)
target.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({k:v for k,v in result.items() if k!='original_sha256'}))
