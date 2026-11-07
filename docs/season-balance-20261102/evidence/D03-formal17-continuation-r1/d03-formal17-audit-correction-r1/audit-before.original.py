from pathlib import Path
import json, hashlib, collections, math

b = Path(__file__).parent
root = b / 'd03-formal17-continuation-r1'
out = b / 'd03-formal17-continuation-audit-r1.derived.json'
assert not out.exists()
run = json.loads((root / 'result.json').read_bytes())
assert run['exit'] == 0 and run['actual_started'] == 9
assert all(run[k] for k in ['source_unchanged', 'binary_unchanged', 'all_original_bank_sources_unchanged'])
observations = root / 'observations'
read_lines = lambda name: [json.loads(line) for line in (observations / name).read_text(encoding='utf-8').splitlines()]
routes = read_lines('routes.original.jsonl')
attempts = read_lines('attempts.original.jsonl')
events = read_lines('events.original.jsonl')
roster = json.loads((root / 'roster.original.json').read_bytes())
assert len(routes) == len(attempts) == len(roster['tracks']) == 9
prices = {row['quality_id']: row for row in json.loads(Path('client/data/catalog.json').read_bytes())['tables']['SeasonEquipment']}
identity = lambda e: e.get('Id', e.get('scenario', e.get('result', {}).get('scenario', {})).get('Id'))
profiles = []
casts = resources = encounters = crafts = total_fragments_spent = 0
banks = []
for track, row, attempt in zip(roster['tracks'], routes, attempts, strict=True):
    sc = row['scenario']
    directory = observations / track['id']
    initial = json.loads((directory / 'bank-import.original.json').read_bytes())
    final_path = directory / 'bank-final.original.json'
    final = json.loads(final_path.read_bytes())
    number = initial['Attempts'] + 1
    assert sc['Id'] == attempt['scenario']['Id'] == track['id'] + '-A' + str(number).zfill(2)
    assert sc == attempt['scenario'] and sc['Seed'] == track['next_seed'] and sc['Loadout'] == track['loadout']
    assert hashlib.sha256(Path(track['source']).read_bytes()).hexdigest() == track['sha256']
    assert json.loads(Path(track['source']).read_bytes()) == initial
    assert final['Attempts'] == number and initial['Id'] == final['Id'] == track['id']
    before = json.loads((directory / ('before-match-' + str(number).zfill(2) + '.original.json')).read_bytes())
    deployed = {x['Item']['ItemId'] for x in before['deployed']}
    assert deployed.issubset({x['Item']['ItemId'] for x in initial['Items']})
    assert deployed == set(attempt['owned_worn_ids'])
    assert sc['EarlyExtract'] == (sc['Difficulty'] == 0 and len(deployed) < 3) and sc['AdaptiveEquipment']
    ee = [e for e in events if identity(e) == sc['Id']]
    start = next(e for e in ee if e['kind'] == 'start')
    assert start['Version'] == 'season-v1-config-17'
    assert start['ContentHash'] == '3e4efc7f04d2acc0d70f1ef3ba7f2ce9cc4b675543b443606880a10b6cc1e490'
    assert start['map'] == row['snapshot']['Map'] and row['original_map_unchanged']
    actor = row['snapshot']['Players'][0]
    assert start['player']['Combat']['MaximumHp'] == {'Mage': 70, 'Priest': 80, 'Guardian': 100}[sc['Hero']]
    # Vitality can legally exceed MaximumHp; no Hp <= MaximumHp assertion is imposed.
    actions = [e for e in events if e['kind'] == 'bank' and e['Id'] == track['id']]
    paid = blue_paid = orange_paid = 0
    for action in actions:
        payload = action['payload']
        if action['action'] == 'enhance':
            old, new = payload['before'], payload['after']
            eq = new['Item']['Equipment']
            assert old['Item']['ItemId'] == new['Item']['ItemId'] and new['Version'] == old['Version'] + 1
            assert eq['Level'] == old['Item']['Equipment']['Level'] + 1
            assert payload['cost'] == prices[eq['Quality'].lower()]['cost_' + str(eq['Level'])]
            paid += payload['cost']
        elif action['action'] == 'reforge':
            old, new = payload['before'], payload['after']
            assert old['Item']['ItemId'] == new['Item']['ItemId'] and new['Version'] == old['Version'] + 1
            assert new['Item']['Equipment']['Level'] == 0 and payload['cost'] in [1, 2]
            paid += payload['cost']
        elif action['action'] == 'craft':
            blue_paid += payload['payment']['Blueprints']
            orange_paid += payload['payment']['OrangeBlueprints']
            assert payload['payment']['Blueprints'] + payload['payment']['OrangeBlueprints'] == (14 if payload['item']['Equipment']['Quality'] == 'Orange' else 4)
            crafts += 1
    assert final['Gold'] == initial['Gold'] + row['realizedGold'] == final['GoldEarned']
    assert final['Fragments'] == initial['Fragments'] - paid + row['realizedFragments']
    assert final['FragmentsSpent'] == initial['FragmentsSpent'] + paid
    assert final['FragmentsEarned'] == initial['FragmentsEarned'] + row['realizedFragments']
    assert final['Fragments'] == final['FragmentsEarned'] - final['FragmentsSpent']
    assert final['Blueprints'] == initial['Blueprints'] - blue_paid + row['marks']['Blueprints']
    assert final['OrangeBlueprints'] == initial['OrangeBlueprints'] - orange_paid + row['marks']['OrangeBlueprints']
    assert final['BlueprintsSpent'] == initial['BlueprintsSpent'] + blue_paid
    assert final['OrangeBlueprintsSpent'] == initial['OrangeBlueprintsSpent'] + orange_paid
    assert min(final[k] for k in ['Gold', 'Fragments', 'Blueprints', 'OrangeBlueprints']) >= 0
    final_ids = {x['Item']['ItemId'] for x in final['Items']}
    assert len(final_ids) == len(final['Items']) and not final_ids.intersection(final['LostIds'])
    assert set(initial['SeenIds']).issubset(final['SeenIds']) and set(initial['LostIds']).issubset(final['LostIds'])
    assert final['Recycled'] == initial['Recycled']
    assert row['outcome'] == 'Extracted' and actor['Phase'] == 5 and final['Deaths'] == initial['Deaths']
    assert actor['ExtractionCompletedAt'] == row['expectedExtraction'] and row['recoveredExtraction']
    end_equipment = actor['WornArmor'] + [x for x in actor['Inventory']['Items'] if x['Kind'] == 5]
    assert deployed.issubset({x['ItemId'] for x in end_equipment})
    assert row['realizedGold'] == sum(x['Quantity'] for x in actor['Inventory']['Items'] if x['Kind'] == 0)
    assert row['realizedFragments'] == sum(x['Quantity'] for x in actor['Inventory']['Items'] if x['Kind'] == 3)
    aa = [e for e in ee if e['kind'] == 'cast']
    assert len(aa) == row['casts']
    spacing = {'novice': 1, 'returning': .7, 'skilled': .5}[sc['Cohort']]
    assert all(y['seconds'] - x['seconds'] >= spacing - 1e-9 for x, y in zip(aa, aa[1:]))
    assert all(not e['resolution']['ActionReplayed'] and 1 <= e['previews'] <= 3 for e in aa)
    starts = [e for e in ee if e['kind'] == 'encounter-start']
    ends = [e for e in ee if e['kind'] == 'encounter-end']
    assert len(starts) == len(ends)
    for first, last in zip(starts, ends, strict=True):
        assert first['pathIndex'] == last['pathIndex']
        rr = [e for e in ee if e['kind'] == 'resource' and e['pathIndex'] == first['pathIndex']]
        ac = [e for e in aa if e['pathIndex'] == first['pathIndex']]
        for e in rr:
            assert e['hpDelta'] == e['hpAfter'] - e['hpBefore'] + e['hpDamage']
            assert e['shieldDelta'] == e['shieldAfter'] - e['shieldBefore'] + e['shieldDamage']
        assert last['damage'] == sum(e['resolution']['HpDamage'] + e['resolution']['ShieldDamage'] for e in ac)
        assert last['damage'] == last['initialHp'] + last['initialShield'] + last['hpAdded'] + last['shieldAdded'] - last['hpOtherLoss'] - last['shieldDiscarded'] - last['remainingHp'] - last['remainingShield']
        resources += len(rr)
    assert row['totalDamage'] == sum(e['damage'] for e in ends)
    assert row['kills'] == sum(e['resolution']['TargetDefeated'] for e in aa)
    assert abs(final['CombatSeconds'] - initial['CombatSeconds'] - row['seconds']) < 1e-7
    milestones = {}
    for field in ['FirstQualityAttempt', 'FirstReadyAttempt', 'FirstTargetAttempt']:
        if initial[field] is not None: assert final[field] == initial[field]
        elif final[field] is not None:
            assert final[field] in [initial['Attempts'], final['Attempts']]
            milestones[field] = {'value': final[field], 'observed_in_current_stage': True,
                'interpretation': 'lobby after already completed attempts, or after this route; never backdated into old evidence'}
    profiles.append({'id': track['id'], 'hero': sc['Hero'], 'cohort': sc['Cohort'], 'difficulty': sc['Difficulty'],
        'attempts': final['Attempts'], 'seconds': row['seconds'], 'gold_net': row['realizedGold'],
        'fragment_net': row['realizedFragments'] - paid, 'fragment_lobby_paid': paid,
        'blue_marks_net': row['marks']['Blueprints'] - blue_paid, 'orange_marks_net': row['marks']['OrangeBlueprints'] - orange_paid,
        'wallet_after': {k: final[k] for k in ['Gold', 'Fragments', 'Blueprints', 'OrangeBlueprints']},
        'owned': len(final['Items']), 'overflow': len(final['Overflow']), 'stop': final['StopReason'],
        'first_quality': final['FirstQualityAttempt'], 'first_ready': final['FirstReadyAttempt'], 'first_target': final['FirstTargetAttempt'],
        'new_milestones': milestones})
    banks.append({'id': track['id'], 'source': str(final_path), 'sha256': hashlib.sha256(final_path.read_bytes()).hexdigest(),
                  'attempts': final['Attempts'], 'censor': final['StopReason']})
    casts += len(aa)
    encounters += len(ends)
    total_fragments_spent += paid

quantiles = []
for cohort in ['novice', 'returning', 'skilled']:
    pp = [p for p in profiles if p['cohort'] == cohort]
    rates = {}
    for field in ['gold_net', 'fragment_net', 'blue_marks_net', 'orange_marks_net']:
        values = sorted(p[field] * 3600 / p['seconds'] for p in pp)
        rates[field] = {name: values[math.ceil(q * len(values)) - 1] for name, q in [('P10', .1), ('P50', .5), ('P90', .9)]}
    quantiles.append({'cohort': cohort, 'sample_count': 3, 'current_stage_net_per_simulated_game_hour': rates,
                     'population_or_wall_clock_or_long_run_claim': False})
budget = json.loads(Path('docs/season-balance-20261102/D03-BUDGET.json').read_bytes())
assert budget['used'] == 293 and budget['remaining'] == 7 and budget['current_handle'] is None
proof = {'status': 'finite current17 capital continuation verified; D03 not accepted', 'new_matches': 9,
    'outcomes': dict(collections.Counter(row['outcome'] for row in routes)), 'casts': casts, 'resource_events': resources,
    'encounters_independently_closed': encounters, 'real_mark_crafts': crafts, 'lobby_fragment_cost': total_fragments_spent,
    'three_ledger_balances_reconciled_for_this_finite_trace': True, 'no_free_initial_gear_or_development_income': True,
    'all_prior_bank_bytes_and_losses_preserved': True, 'legal_mage70_priest80_guardian100_and_vitality_overcap': True,
    'profiles': profiles, 'sample_quantiles': quantiles, 'next_bank_sources': banks,
    'D03_used': 293, 'D03_remaining': 7, 'D03_complete': False, 'class_ratio_limit': 1.15,
    'not_claimed': ['population P50/P90', 'long-run stationarity', 'day1/7/14 current-calendar acceptance',
                    'same-kit class efficiency from unequal bank loadouts', 'new PostgreSQL execution', 'new deaths/rebuilds in this all-extracted stage'],
    'F01_252_started': False, 'production_changed': False}
out.write_text(json.dumps(proof, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print(json.dumps({k:v for k,v in proof.items() if k not in ['profiles', 'sample_quantiles', 'next_bank_sources']}, ensure_ascii=True))
