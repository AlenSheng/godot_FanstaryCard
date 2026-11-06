from pathlib import Path
import json, hashlib, collections, math

base = Path(__file__).parent
proof = json.loads((base / 'd03-entry16-longitudinal-summary-r1.derived.json').read_bytes())
for name, digest in proof['source_sha256'].items():
    assert hashlib.sha256((base / name).read_bytes()).hexdigest() == digest
rows = []
for stage in proof['stages']:
    root = base / stage['stage'] / 'observations'
    rr = [json.loads(line) for line in (root / 'routes.original.jsonl').read_text().splitlines()]
    ee = [json.loads(line) for line in (root / 'events.original.jsonl').read_text().splitlines()]
    assert len(rr) == stage['matches']
    casts = resources = 0
    for row in rr:
        identity = row['scenario']['Id']
        events = [e for e in ee if e.get('Id', e.get('scenario', e.get('result', {}).get('scenario', {})).get('Id')) == identity]
        actions = [e for e in events if e['kind'] == 'cast']
        starts = [e for e in events if e['kind'] == 'encounter-start']
        ends = [e for e in events if e['kind'] == 'encounter-end']
        assert len(actions) == row['casts'] and len(starts) == len(ends)
        reaction = {'novice': 1, 'returning': .7, 'skilled': .5}[row['scenario']['Cohort']]
        assert all(b['seconds'] - a['seconds'] >= reaction - 1e-9 for a, b in zip(actions, actions[1:]))
        for a, b in zip(starts, ends, strict=True):
            assert a['pathIndex'] == b['pathIndex']
            actual = sum(e['resolution']['HpDamage'] + e['resolution']['ShieldDamage'] for e in actions if e['pathIndex'] == a['pathIndex'])
            assert b['damage'] == actual == b['initialHp'] + b['initialShield'] + b['hpAdded'] + b['shieldAdded'] - b['hpOtherLoss'] - b['shieldDiscarded'] - b['remainingHp'] - b['remainingShield']
        assert row['totalDamage'] == sum(e['damage'] for e in ends)
        casts += len(actions)
        resources += sum(e['kind'] == 'resource' for e in events)
    assert casts == stage['casts'] and resources == stage['resource_changes']
    rows += rr
assert dict(collections.Counter(r['outcome'] for r in rows)) == proof['outcomes']
for profile in proof['profiles']:
    bank = json.loads(Path(profile['source']).read_bytes())
    assert profile['hours'] == bank['CombatSeconds'] / 3600
    assert profile['attempts'] == bank['Attempts'] and profile['deaths'] == bank['Deaths']
    assert profile['gold_net_per_game_hour'] == bank['Gold'] / profile['hours']
    assert profile['fragment_net_per_game_hour'] == bank['Fragments'] / profile['hours']
for cohort, result in proof['cohorts'].items():
    pp = [p for p in proof['profiles'] if p['cohort'] == cohort]
    for key, recorded in result['first_set_nearest_rank_empirical_quantiles'].items():
        values = sorted(p[key] if p[key] is not None else math.inf for p in pp)
        for q in [.1, .5, .9]:
            value = values[math.ceil(len(values) * q) - 1]
            assert recorded[f'P{int(q*100)}'] == (value if math.isfinite(value) else None)
assert len(rows) == 104 and proof['D03_used'] == 218 and proof['D03_remaining'] == 82
print('104 raw routes, 15992 casts, 741 resource changes and censored empirical quantiles reproduced.')
