from pathlib import Path
import hashlib,json,math,sys,xml.etree.ElementTree as ET

base=Path(__file__).parent;heroes=sys.argv[1:];assert heroes and all(x in ['Priest','Mage','Guardian'] for x in heroes)
out=base/('d02-rebuild-inspection-'+'-'.join(heroes)+'-r1.derived.json');assert not out.exists()
prices={x['quality_id']:x for x in json.loads(Path('client/data/catalog.json').read_bytes())['tables']['SeasonEquipment']};rows=[];sources={}
for hero in heroes:
    stage=base/('d02-rebuild-pg-r1' if hero=='Priest' else 'd02-rebuild-pg-'+hero.lower()+'-r1');p=stage/'observations'/hero
    result=json.loads((p/'result.original.json').read_bytes());fixture=json.loads((p/'fixture.original.json').read_bytes());schema=json.loads((p/'schema.original.json').read_bytes())['schema']
    death=json.loads((p/'death.original.json').read_bytes());committed=json.loads((p/'death-committed.original.json').read_bytes());before=json.loads((p/'BeforeDeath-ready.original.json').read_bytes());after=json.loads((p/'AfterRebuild-ready.original.json').read_bytes())
    assert result['passed'] and result['real_storage_and_real_two_match_launches'] and result['missing_and_lost_body_rejected'] and result['old_dropped_items_not_restored']
    assert result['oldMatch']==before['MatchId'] and result['newMatch']==after['MatchId'] and before['MatchId']!=after['MatchId']
    player=fixture['Player'];bp=next(x for x in before['snapshot']['Players'] if x['PlayerId']==player);ap=next(x for x in after['snapshot']['Players'] if x['PlayerId']==player)
    assert before['snapshot']['ConfigVersion']==after['snapshot']['ConfigVersion']=='season-v1-config-15';assert before['snapshot']['Season']==after['snapshot']['Season']==result['source_context']
    assert bp['Combat']['WeaponLevel']==ap['Combat']['WeaponLevel']==2 and bp['Combat']['Equipment']==ap['Combat']['Equipment']
    lost=result['worn'];spare=result['spare'];assert len(set(lost))==len(set(spare))==5 and set(lost).isdisjoint(spare)
    assert {x['ItemId'] for x in bp['WornArmor']}==set(lost) and {x['ItemId'] for x in ap['WornArmor']}==set(spare)
    assert all(x['Equipment']['Level']==3 for x in bp['WornArmor']+ap['WornArmor'])
    dead=next(x for x in death['Players'] if x['PlayerId']==player);assert dead['Phase']==4 and dead['Combat']['Hp']==0 and dead['WornArmor']==[]
    pile=next(x for x in death['RelicPiles'] if x['VictimId']==player);assert {x['ItemId'] for x in pile['Items']}==set(lost)
    assert committed['committed']==5 and committed['receipt']['Result']=='Dead' and committed['receipt']['MatchId']==before['MatchId'] and committed['preparation_status']=='Settled'
    assert len(set(result['recipes']))==5 and result['recipes']==committed['recipes']
    balance=fixture['initial_wallet_fragments'];assert balance==5000;cost=reforge=enhance=0
    for index,slot in enumerate(['Head','Chest','Hands','Legs','Feet']):
        gear=json.loads((p/('rebuilt-'+slot+'.original.json')).read_bytes());quote=gear['quote'];rebuilt=gear['rebuilt'];enhanced=gear['enhanced'];after_reforge=rebuilt['Equipment']
        assert quote['Before']['InstanceId']==spare[index] and quote['Before']['Location']=='Inventory' and quote['CanReforge']
        assert quote['After']['Level']==0 and after_reforge['InstanceId']==enhanced['InstanceId']==spare[index] and after_reforge['Level']==0 and enhanced['Level']==3
        assert enhanced['Slot']==slot and enhanced['SourceKind']=='TemplateReforge' and not enhanced['RecipeExtracted'] and enhanced['Version']==after_reforge['Version']+3
        fee=quote['FragmentCost'];assert fee==(2 if slot=='Head' else 1) and quote['AvailableFragments']==balance and rebuilt['Wallet']['EquipmentFragments']==balance-fee
        tier=prices[enhanced['Quality'].lower()];upgrade=sum(tier['cost_'+str(i)] for i in [1,2,3]);balance-=fee+upgrade;cost+=fee+upgrade;reforge+=fee;enhance+=upgrade
    assert cost==result['spent_fragments']==66 and balance==4934 and reforge==6 and enhance==60
    actual=result['actual_first_play'];assert actual['CombatActionId'].startswith('1:') and not actual['ActionReplayed'];next_player=next(x for x in result['next_snapshot']['Players'] if x['PlayerId']==player)
    base_hp={'Priest':80,'Mage':70,'Guardian':100}[hero];cap=min(math.floor(base_hp*1.4),math.floor(base_hp*(1+ap['Combat']['Equipment']['VitalityOvercapBonus'])))
    assert next_player['Combat']['MaximumHp']==base_hp and 0<next_player['Combat']['Hp']<=cap and next_player['LastCombatActionSequence']==1
    attempts=[json.loads(x) for x in (p/'attempts.original.jsonl').read_text('utf-8').splitlines()];assert len(attempts)==2 and {x['phase'] for x in attempts}=={'BeforeDeath','AfterRebuild'} and {x['MatchId'] for x in attempts}=={before['MatchId'],after['MatchId']}
    proof=json.loads((stage/'result.json').read_bytes());assert proof['source_unchanged'] and proof['binary_unchanged'] and proof['cloud_guard_ok']
    cleanup=json.loads((stage/'schema-cleanup.original.json').read_bytes());assert cleanup['success'] and schema not in cleanup['schemas_still_present']
    if hero=='Priest':
        assert proof['guard_reason']=='600s observation limit' and ('PriestDeathAndRealBodyBackedRebuildEntersAnotherPreparedMatch [FINISHED]') in (stage/'test.original.log').read_text('utf-8')
    else:
        assert proof['exit']==0 and proof['actual_match_attempts']==2 and proof['cleanup_verified'];c=next(x.attrib for x in ET.fromstring((stage/'cases.trx').read_bytes()).iter() if x.tag.endswith('Counters'));assert c['passed']=='1' and c['failed']==c['notExecuted']=='0'
    rows.append(dict(hero=hero,real_matched_rooms=2,settled_dropped_items=5,spare_body_ids_preserved=5,template_recipes_retained=5,reforge_cost=reforge,enhancement_cost=enhance,derived_final_wallet=balance,ready_derived_equipment_equal_before_and_after=True,actual_new_match_play=True,owned_schema_absent=True,old_batch_timeout_preserved=hero=='Priest'))
    for file in p.glob('*'):
        if file.is_file():sources[file.relative_to(base).as_posix()]=hashlib.sha256(file.read_bytes()).hexdigest()
result=dict(verified_heroes=rows,new_test_executions=0,real_original_match_launches=2*len(rows),actual_PG_storage=True,missing_or_lost_body_cannot_mint=True,all_lost_items_kept_dropped=True,permanent_progression_initial5_is_explicit_fixture=True,death_is_authoritative_abandonment_not_enemy_kill=True,OS_process_restart_not_claimed=True,source_sha256=sources)
out.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({k:v for k,v in result.items() if k!='source_sha256'}))
