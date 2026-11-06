from pathlib import Path
import collections,datetime,hashlib,json,math

base=Path(__file__).parent;target=base/'d02-duels-inspection-r1.derived.json';assert not target.exists()
all_rows=[];sources={};casts=[];reconnect=0;expired=0;hp={1:80,2:70,3:100}
def players(snapshot):return {p['PlayerId']:p for p in snapshot['Players']}
for label in ['pilot','expiry-followup','unstarted']:
    root=base/('d02-duels-'+label+'-r1');run=json.loads((root/'result.json').read_bytes());assert all(run[k] for k in ['roster_identity_match','source_unchanged','binary_unchanged','workbook_unchanged'])
    if label=='pilot':assert run['exit']==1 and run['actual_started']==2
    else:assert run['exit']==0 and run['actual_started']==run['planned']
    p=root/'observations';rows=[json.loads(x) for x in (p/'cases.original.jsonl').read_text('utf-8').splitlines()]
    events=[json.loads(x) for x in (p/'events.original.jsonl').read_text('utf-8').splitlines()]
    for row in rows:
        scenario=row['scenario'];identifier=scenario['Id'];ee=[e for e in events if e.get('Id',e.get('scenario',e.get('result',{}).get('scenario',{})).get('Id'))==identifier]
        assert ee[0]['kind']=='start' and ee[-1]['kind']=='end' and ee[-1]['result']==row
        bykind={e['kind']:e for e in ee};start=bykind['start'];assert start['Version']=='season-v1-config-15' and start['ContentHash']=='2bc11db4b287055d119aceda45deeeb6fb00c3df524b3acad9887deaa04d9d8a'
        first=start['firstId'];late=start['lateId'];original={first:start['firstBefore'],late:start['lateBefore']};ss=start['snapshot'];duel=ss['Duels'][0]
        assert duel['FirstPlayerId']==first and duel['LatePlayerId']==late and duel['FirstFrozen']['Combat']==original[first]['Combat'] and duel['LateFrozen']['Combat']==original[late]['Combat']
        start_time=datetime.datetime.fromisoformat(duel['StartedAt']);unlock=datetime.datetime.fromisoformat(duel['LatePlayerUnlockAt']);assert (unlock-start_time).total_seconds()==.8
        first_cast=bykind['cast-first'];late_cast=bykind['cast-late'];assert first_cast['result']==row['firstCast'] and late_cast['result']==row['lateCast']
        assert first_cast['seconds']==.1 and late_cast['seconds']>=.9
        for event,attacker,other,before in [(first_cast,first,late,start['snapshot']),(late_cast,late,first,first_cast['snapshot'])]:
            result=event['result'];after=players(event['snapshot']);before_players=players(before)
            assert not result['ActionReplayed'] and not result['TargetDefeated'] and result['BattleId']==duel['DuelId'] and result['AttackerId']==attacker and result['TargetId']==other
            assert result['HpDamage']==before_players[other]['Combat']['Hp']-after[other]['Combat']['Hp'] and result['ShieldDamage']==before_players[other]['Combat']['Shield']-after[other]['Combat']['Shield']
            casts.append(result)
        frozen=players(late_cast['snapshot']);restored=bykind['restored-disconnected']['snapshot'];rp=players(restored)
        for identifier2 in [first,late]:
            assert rp[identifier2]['Combat']==frozen[identifier2]['Combat'] and rp[identifier2]['Pve']['Monsters']==original[identifier2]['Pve']['Monsters']
            for snapshot in [start['snapshot'],first_cast['snapshot'],late_cast['snapshot'],restored]:
                player=players(snapshot)[identifier2];combat=player['Combat'];base_hp=hp[player['HeroClass']];limit=min(math.floor(base_hp*1.4),math.floor(base_hp*(1+combat['Equipment']['VitalityOvercapBonus'])))
                assert combat['MaximumHp']==base_hp and 0<combat['Hp']<=limit and 0<=combat['Shield']<=base_hp//2
                assert len(combat['Deck']['Hand'])<=5 and 0<=combat['Deck']['DrawCharge']<1
        replay=bykind['action-replay']['result'];expected=dict(row['firstCast'],ActionReplayed=True);assert replay==expected and bykind['action-replay']['unchanged_snapshot']
        final=row['snapshot'];assert final['Duels']==[] and row['firstSequence']==row['lateSequence']==2
        fp=players(final)
        if scenario['Outcome']=='Reconnect':
            reconnect+=1
            for identifier2 in [first,late]:assert fp[identifier2]['Combat']==original[identifier2]['Combat'] and fp[identifier2]['Pve']==original[identifier2]['Pve'] and fp[identifier2]['Phase']==original[identifier2]['Phase']
        else:
            expired+=1;disconnected=first if scenario['DisconnectRole']=='First' else late;winner=late if disconnected==first else first
            assert bykind['before-expiry']['remaining']=='00:00:00.1000000';control=bykind['expiry-resume-control'];assert control['expected_pve_ticks_after_restore']==1
            assert fp[winner]['Combat']==control['expectedWinner']['Combat'] and fp[winner]['Pve']==control['expectedWinner']['Pve']
            assert fp[disconnected]['Combat']['Hp']==0 and fp[disconnected]['Pve'] is None and fp[disconnected]['WornArmor']==[]
            pile=next(x for x in final['RelicPiles'] if x['VictimId']==disconnected)
            assert {(x['ItemId'],json.dumps(x['Equipment'],sort_keys=True)) for x in pile['Items']}=={(x['ItemId'],json.dumps(x['Equipment'],sort_keys=True)) for x in original[disconnected]['WornArmor']}
        all_rows.append(row)
    for file in [root/'result.json',p/'attempts.original.jsonl',p/'cases.original.jsonl',p/'events.original.jsonl']:sources[file.relative_to(base).as_posix()]=hashlib.sha256(file.read_bytes()).hexdigest()
assert len(all_rows)==len({r['scenario']['Id'] for r in all_rows})==72 and reconnect==expired==36
assert len({(r['scenario']['First'],r['scenario']['Late'],r['scenario']['Difficulty'],r['scenario']['Outcome'],r['scenario']['DisconnectRole']) for r in all_rows})==72
budget=json.loads(Path('docs/season-balance-20261102/D02-BUDGET.json').read_bytes());assert budget['used']==73 and budget['remaining']==227 and budget['current_handle'] is None
old=json.loads((base/'d02-duel-preflight-r2/source-pin.json').read_bytes());new=json.loads((base/'d02-duel-preflight-r3/source-pin.json').read_bytes());domain=[x for x in old if x.startswith('server/src/FantasyCard.Domain/')];assert all(old[n]==new[n] for n in domain)
result=dict(status='published_D02_duel_recovery_subscope_verified_not_whole_D02',unique_completed_scenarios=72,actual_attempts=73,original_failed_attempts_retained=1,
    first_pilot_complete_reused=1,targeted_expiry_retry_complete=1,previously_unstarted_complete=70,reconnect=36,expiry=36,actual_successful_casts=len(casts),
    actual_stun_casts=sum(x['StunSeconds']>0 for x in casts),actual_draw_block_casts=sum(x['DrawBlockSeconds']>0 for x in casts),actual_immediate_draw_casts=sum(x['ImmediateDraw']>0 for x in casts),
    original_PVE_preserved=True,JSON_disconnected_roundtrip=True,action_replay_and_sequences_preserved=True,legal_health=True,dead_armor_identity_preserved=True,
    expiry_oracle='original PVE plus exactly one100ms continuation in expiry tick; reconnect mutual-leave compares exact original state',
    domain_source_files_unchanged_between_pilot_and_retry=len(domain),not_one_all_green_run=True,D02_complete=False,remaining=['full legal routes/extraction with current config and recovery','death settlement through actual storage and recipe/body-backed rebuild','remaining specific control/return boundary evidence audit'],
    D02_used=73,D02_remaining=227,threshold_relaxed=False,B05_new_attempts=0,C16_new_attempts=0,D01_new_attempts=0,source_sha256=sources)
target.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({k:v for k,v in result.items() if k!='source_sha256'}))
