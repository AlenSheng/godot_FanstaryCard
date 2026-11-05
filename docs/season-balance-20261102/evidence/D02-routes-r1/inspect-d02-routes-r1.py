from pathlib import Path
import collections,hashlib,json,math

base=Path(__file__).parent;out=base/'d02-routes-inspection-r1.derived.json';assert not out.exists()
cards={r['monster_type']:r['id'] for r in json.loads(Path('client/data/catalog.json').read_bytes())['tables']['Cards'] if r['monster_type'] is not None}
species={'fire-bat':'FireBat','thorn-mite':'ThornMite','murk-snail':'MudHydra','sand-lizard':'SandLizard','rust-rat':'RustRat','box-spirit':'BoxSpirit','metal-guard':'GoldGuard','fire-herald':'FireReaver','marsh-mother':'SwampMother','stone-guard':'StoneGuard','thorn-guard':'ThornGuard','annihilation-core':'VoidCore'}
rows=[];cast_count=kill_count=clear_count=resource_count=recoveries=red_rolls=heal_choices=0;sources={};path_lengths=set()
for label,n in [('pilot',3),('unstarted',15)]:
    root=base/('d02-routes-'+label+'-r1');run=json.loads((root/'result.json').read_bytes());assert run['exit']==0 and run['actual_started']==n and all(run[k] for k in ['roster_identity_match','source_unchanged','binary_unchanged','workbook_unchanged'])
    p=root/'observations';attempts=[json.loads(x) for x in (p/'attempts.original.jsonl').read_text('utf-8').splitlines()];rr=[json.loads(x) for x in (p/'routes.original.jsonl').read_text('utf-8').splitlines()];events=[json.loads(x) for x in (p/'events.original.jsonl').read_text('utf-8').splitlines()];assert len(attempts)==len(rr)==n
    for row,attempt in zip(rr,attempts,strict=True):
        scenario=row['scenario'];identifier=scenario['Id'];assert scenario==attempt;ee=[e for e in events if e.get('Id',e.get('scenario',e.get('result',{}).get('scenario',{})).get('Id'))==identifier]
        start=ee[0];end=ee[-1];assert start['kind']=='start' and end['kind']=='end' and end['result']==row
        assert start['Version']=='season-v1-config-15' and start['ContentHash']=='2bc11db4b287055d119aceda45deeeb6fb00c3df524b3acad9887deaa04d9d8a'
        assert row['outcome']=='Extracted' and row['recoveredAction'] and row['recoveredExtraction']
        key=lambda x:(x['Row'],x['Column']);path=[key(x) for x in start['path']];cells={key(x['Position']):x for x in start['map']['Cells']};assert path[0]==key(start['map']['SpawnPositions'][0]) and path[-1]==key(start['map']['BossPosition'])
        assert all(abs(a[0]-b[0])+abs(a[1]-b[1])==1 and cells[b]['Layer']>=cells[a]['Layer'] for a,b in zip(path,path[1:]));assert len(path)==len(set(path))
        assert row['snapshot']['Map']==start['map'] and row['clears']==len(path) and row['pathIndex']==len(path)-1
        cc=[e for e in ee if e['kind']=='cast'];assert len(cc)==row['casts'];assert all(b['seconds']-a['seconds']>=.5-1e-9 for a,b in zip(cc,cc[1:]));assert all(not e['resolution']['ActionReplayed'] and 1<=e['previews']<=3 for e in cc)
        assert len({e['resolution']['CombatActionId'] for e in cc})==len(cc)
        starts=[e for e in ee if e['kind']=='encounter-start'];ends=[e for e in ee if e['kind']=='encounter-end'];assert len(starts)==len(ends)==len(path)
        for index,(bs,be) in enumerate(zip(starts,ends,strict=True)):
            assert bs['pathIndex']==be['pathIndex']==index and key(bs['position'])==path[index] and be['outcome']=='Clear' and be['remainingHp']==be['remainingShield']==0
            aa=[e for e in cc if e['pathIndex']==index];changes=[e for e in ee if e['kind']=='resource' and e['pathIndex']==index]
            assert be['initialHp']==sum(x['Hp'] for x in bs['monsters']) and be['initialShield']==sum(x['Shield'] for x in bs['monsters'])
            sums={'hpAdded':sum(max(0,x['hpDelta']) for x in changes),'shieldAdded':sum(max(0,x['shieldDelta']) for x in changes),'hpOtherLoss':sum(max(0,-x['hpDelta']) for x in changes),'shieldDiscarded':sum(max(0,-x['shieldDelta']) for x in changes)}
            assert all(be[k]==v for k,v in sums.items());assert be['damage']==sum(e['resolution']['HpDamage']+e['resolution']['ShieldDamage'] for e in aa)
            assert be['damage']==be['initialHp']+be['initialShield']+be['hpAdded']+be['shieldAdded']-be['hpOtherLoss']-be['shieldDiscarded']
            monster_by_id={m['MonsterId']:m for m in bs['monsters']}
            for cast in aa:
                defeated=cast['resolution']['TargetDefeated'];assert len(cast['added'])==(1 if defeated else 0)
                if defeated:
                    monster=cast['resolution']['TargetId'];monster=monster[:-2] if monster.endswith(('-a','-b')) else monster;card=cast['added'][0]
                    assert card['CardId']==cards[species[monster]] and card['Level']==0
                    expected=monster_by_id[cast['resolution']['TargetId']]['Intents'][0]['Element'] if monster=='box-spirit' else None;assert card['ElementOverride']==expected
            resource_count+=len(changes)
        assert row['totalDamage']==sum(x['damage'] for x in ends)
        base_hp={'Mage':70,'Priest':80,'Guardian':100}[scenario['Hero']];equipment=start['player']['Combat']['Equipment'];limit=min(math.floor(base_hp*1.4),math.floor(base_hp*(1+equipment['VitalityOvercapBonus'])))
        assert all(0<e['hpBefore']<=limit and 0<e['hpAfter']<=limit and 0<=e['shieldAfter']<=base_hp//2 for e in cc)
        recovered=[e for e in ee if e['kind']=='recovered'];assert len(recovered)==2 and {e['stage'] for e in recovered}=={'FirstAcceptedAction','ExtractionReading'} and all(e['full_snapshot_equivalent'] for e in recovered)
        action=next(e for e in recovered if e['stage']=='FirstAcceptedAction');assert action['replay']==dict(cc[0]['resolution'],ActionReplayed=True)
        reading=next(e for e in ee if e['kind']=='extraction-reading');assert reading['duration']=='00:00:03' and reading['remaining']=='00:00:02.9000000' and reading['expectedExtraction']==row['expectedExtraction']
        final=row['snapshot']['Players'][0];assert final['Phase']==5 and final['ExtractionCompletedAt']==row['expectedExtraction'] and key(final['Position'])==path[-1]
        assert final['LastCombatActionSequence']==len(cc);pool=final['Combat']['Deck'];pool_cards=pool['Hand']+pool['Library']+pool['Discard'];assert len(pool_cards)==20+row['kills'] and len({x['InstanceId'] for x in pool_cards})==len(pool_cards)
        assert row['kills']==sum(e['resolution']['TargetDefeated'] for e in cc)
        rewards=[e for e in ee if e['kind']=='reward'];assert len(rewards)==len(path);heal_choices+=sum(e['selected']['Kind']==3 for e in rewards)
        red=[e for e in ee if e['kind']=='red-adjudication'];assert len(red)==row['redRolls']
        for e in red:
            hit=scenario['Difficulty']>=2 and e['evaluation']['Roll']<40;assert e['evaluation']['Source']=='ChaosBoss' and e['hits']==hit and e['status']==('Exhausted' if hit else 'Miss') and e['fixture_only_no_mint']
        cast_count+=len(cc);kill_count+=row['kills'];clear_count+=len(path);recoveries+=len(recovered);red_rolls+=len(red);path_lengths.add(len(path));rows.append(row)
    for file in [root/'result.json',p/'attempts.original.jsonl',p/'routes.original.jsonl',p/'events.original.jsonl']:sources[file.relative_to(base).as_posix()]=hashlib.sha256(file.read_bytes()).hexdigest()
assert len(rows)==18 and len({(x['scenario']['Hero'],x['scenario']['Difficulty']) for x in rows})==18
budget=json.loads(Path('docs/season-balance-20261102/D02-BUDGET.json').read_bytes());assert budget['used']==91 and budget['remaining']==209 and budget['current_handle'] is None
result=dict(status='D02_natural_route_recovery_extraction_subscope_verified_not_whole_D02',cases=18,extracted=18,dead=0,timeout=0,casts=cast_count,kills=kill_count,cleared_cells=clear_count,resource_events=resource_count,snapshot_recoveries=recoveries,real3second_extraction_completed=18,all_original_maps_unchanged=True,route_cell_counts=sorted(path_lengths),real_red_rolls=red_rolls,actual_heal_rewards=heal_choices,weekly_quota_hit_is_explicit_exhausted_fixture_not_PG=True,
    not_R1_or_random_population_mean=True,D02_complete=False,D02_used=91,D02_remaining=209,B05_new_runs=0,C16_new_runs=0,D01_new_runs=0,source_sha256=sources)
out.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({k:v for k,v in result.items() if k!='source_sha256'}))
