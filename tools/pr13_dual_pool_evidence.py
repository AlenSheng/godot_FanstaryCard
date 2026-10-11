"""Read native two-player JSON/Protobuf evidence; executes no game code."""
from collections import Counter, defaultdict
import copy
import hashlib
import json
from pathlib import Path
import uuid

from tools.pr13_natural_choice_evidence import CLIENT, SERVER, SPECIES, wire, piles
from tools.pr13_pool_render_evidence import choose_command, protobuf_fields


def identity(value):
    return str(uuid.UUID(bytes_le=hashlib.sha256(value.encode()).digest()[:16]))


def player(snapshot, owner):
    return next(x for x in snapshot['players'] if x['playerId'] == owner)


def audit(snapshot, capacity, hero=None):
    pool = snapshot['monsterPool']
    cards = piles(snapshot['combat']['deck'])
    ids = [c['instanceId'] for c in cards]
    assert len(ids) == len(set(ids))
    if hero:
        prefix = {'Mage': 'MAG', 'Priest': 'PRI', 'Guardian': 'GUA'}[hero]
        expected = {f'C{i:02}' for i in range(1, 14)} | {f'{prefix}-{i:02}' for i in range(1, 8)}
        base = [c for c in cards if c['cardId'] in expected]
        assert len(base) == 20 and {c['cardId'] for c in base} == expected
    if capacity:
        assert len(ids) == 20 + len(pool['active']) and len(pool['active']) <= capacity
        assert {c['instanceId'] for c in pool['active']}.issubset(ids)
        assert not {c['instanceId'] for c in pool['pending']} & set(ids)
    return set(ids)


def command(data, row, expected_type):
    value = wire(data['command'], CLIENT)
    assert value[1] == 1 and value[2] == expected_type.encode()
    assert value[6].decode() == identity(f"room:{row['hero']}:{row['seed']}")
    assert value[7].decode() == identity(f"match:{row['hero']}:{row['seed']}:{row['capacity']}")
    responses = [wire(x, SERVER) for x in data['responses']]
    assert responses and all(x.get(8) == value[3] for x in responses)
    return value, responses


def provenance(candidate, snapshot, kills, cards):
    assert candidate['level'] == 0 and cards[candidate['cardId']]['monster_type']
    battle = snapshot['pve']['battleId']
    owner = snapshot['playerId']
    sources = set(snapshot['monsterPool']['grantedSources'])
    matches = []
    for monster in snapshot['pve']['monsters']:
        name = monster['monsterId']
        species = name[:-2] if name.endswith(('-a', '-b')) else name
        if (monster['hp'] == 0 and SPECIES.get(species) == cards[candidate['cardId']]['monster_type']
                and (owner, battle, name) in kills and battle + ':' + name in sources):
            matches.append(name)
    assert matches, 'Missing matching actual owner kill batch'
    return len(matches)


def verify_event(row, kills, cards, case=None):
    kind, d, capacity = row['kind'], row['data'], row['capacity']
    roles = {identity(f"A:{row['hero']}:{row['seed']}"): row['hero'],
             identity(f"B:{row['hero']}:{row['seed']}"): (case or {}).get('peerHero', row['hero'])}
    def role_audit(p):
        assert p['playerId'] in roles
        hero = roles[p['playerId']]
        assert p['heroClass'] == {'Priest': 1, 'Mage': 2, 'Guardian': 3}[hero]
        return audit(p, capacity, hero)
    if kind == 'known-foreign-candidate':
        assert capacity and d['owner'] != d['requester']
        assert d['before'] == d['after']
        assert {x['playerId'] for x in d['before']['players']} == {
            identity(f"{label}:{row['hero']}:{row['seed']}") for label in ('A', 'B')}
        owner, requester = player(d['before'], d['owner']), player(d['before'], d['requester'])
        assert owner['phase'] == requester['phase'] == 6  # Actual Choice enum.
        assert requester['monsterPool']['pending'] == d['requesterOwnPending'] and d['requesterOwnPending']
        candidate = d['candidate']
        assert candidate in owner['monsterPool']['pending']
        assert candidate['instanceId'] not in {x['instanceId'] for x in d['requesterOwnPending']}
        assert not set(d['ownerSources']) & set(requester['monsterPool']['grantedSources'])
        provenance(candidate, owner, kills, cards)
        for p in (owner, requester): role_audit(p)
        cmd, responses = command(d, row, 'monster.choose')
        assert choose_command(cmd[5]) == {'candidate_id': candidate['instanceId'], 'accept': True, 'replace_instance_id': ''}
        assert len(responses) == 1 and responses[0][2] == b'error.command_rejected'
        rejection = protobuf_fields(responses[0][4], {1: 2, 2: 2})
        assert rejection[1] == b'COMMAND_REJECTED' and rejection[2] == b'The monster candidate no longer exists.'
    elif kind == 'own-candidate-choice':
        before, after = d['before'], d['after']
        assert before['playerId'] == after['playerId'] == d['owner'] and before['phase'] == after['phase'] == 6
        provenance(d['candidate'], before, kills, cards)
        old, new = role_audit(before), role_audit(after)
        assert after['combat']['deck']['hand'] == before['combat']['deck']['hand']
        if d['accept']:
            assert new == old | {d['candidate']['instanceId']}
            assert sum(c['instanceId'] == d['candidate']['instanceId'] for c in after['combat']['deck']['discard']) == 1
        else:
            assert before['combat']['deck'] == after['combat']['deck']
            assert before['monsterPool']['active'] == after['monsterPool']['active']
        a, b = copy.deepcopy(before), copy.deepcopy(after)
        for v in (a, b): v.pop('monsterPool'); v['combat'].pop('deck')
        assert a == b
        cmd, responses = command(d, row, 'monster.choose')
        assert choose_command(cmd[5]) == {'candidate_id': d['candidate']['instanceId'], 'accept': d['accept'], 'replace_instance_id': ''}
        assert not any(x[2].startswith(b'error.') for x in responses)
    elif kind == 'natural-pvp-entry':
        snapshot = d['checkpoint']; assert len(snapshot['duels']) == 1
        duel = snapshot['duels'][0]; ids = {duel['firstPlayerId'], duel['latePlayerId']}
        assert ids == {x['playerId'] for x in snapshot['players']}
        assert all(p['phase'] == 3 and p['currentDuelId'] == duel['duelId'] and p['position'] == d['entryPosition'] for p in snapshot['players'])
        cmd, responses = command(d, row, 'room.move')
        move = protobuf_fields(cmd.get(5, b''), {1: 0, 2: 0})
        assert (move.get(1, 0), move.get(2, 0)) == (d['entryPosition']['row'], d['entryPosition']['column'])
        assert not any(x[2].startswith(b'error.') for x in responses)
        for p in snapshot['players']:
            ids = role_audit(p)
            frozen = duel['firstFrozen'] if p['playerId'] == duel['firstPlayerId'] else duel['lateFrozen']
            assert ids == {c['instanceId'] for c in piles(frozen['combat']['deck'])}
            assert not capacity or p['monsterPool']['active']
    elif kind == 'actual-pvp-checkpoint-restored':
        assert d['before']['duels'] == d['after']['duels']
        assert d['before']['roomId'] == d['after']['roomId']
        for p in d['before']['players']:
            restored = player(d['after'], p['playerId'])
            assert p['monsterPool'] == restored['monsterPool']
            assert p['combat']['deck'] == restored['combat']['deck']
            assert p['phase'] == restored['phase'] == 3
            role_audit(restored)
    elif kind == 'pvp-mutual-leave-return':
        assert not d['after']['duels'] and len(d['before']['duels']) == 1
        duel = d['before']['duels'][0]
        cmd, responses = command(d, row, 'duel.leave')
        assert protobuf_fields(cmd[5], {1: 2})[1].decode() == duel['duelId']
        assert any(x[2] == b'duel.leave_ack' and protobuf_fields(x[4], {1: 2, 2: 0}).get(2) == 1 for x in responses)
        for p in d['after']['players']:
            frozen = duel['firstFrozen'] if p['playerId'] == duel['firstPlayerId'] else duel['lateFrozen']
            assert p['phase'] == frozen['phase'] and p['currentDuelId'] is None
            assert p['combat'] == frozen['combat'] and p['pve'] == frozen['pve']
            assert p['monsterPool'] == player(d['before'], p['playerId'])['monsterPool']
            role_audit(p)
    elif kind == 'terminal-pool-cleared':
        p = d['snapshot']; assert p['playerId'] == d['owner'] and p['phase'] in (4, 5)
        assert not p['monsterPool']['active'] and not p['monsterPool']['pending']
        ids = role_audit(p); original = set(d['originalBaseInstances'])
        assert len(original) == 20 and original.issubset(ids)
        assert not capacity or ids == original
    else:
        assert kind == 'native-kill'


def verify_segment(directory, hero, count, catalog, source, terminal_events=True):
    directory = Path(directory)
    cards = {x['id']: x for x in json.loads(Path(catalog).read_bytes())['tables']['Cards']}
    routes = [json.loads(line) for line in (directory / 'routes.jsonl').read_text().splitlines()]
    assert len(routes) == count * 4
    assert {(x['seed'], x['capacity']) for x in routes} == {(s, c) for s in range(484001, 484001 + count) for c in (0, 3, 5, 8)}
    cases = {(x['seed'], x['capacity']): x for x in routes}
    counts = defaultdict(Counter); kills = defaultdict(set); groups = defaultdict(Counter)
    with (directory / 'events.jsonl').open() as f:
        for line in f:
            row = json.loads(line); assert row['hero'] == hero and row['source'] == source
            key = (row['seed'], row['capacity']); assert key in cases
            if row['kind'] == 'native-kill':
                d = row['data']; assert d['owner'] in {identity(f"{label}:{hero}:{row['seed']}") for label in ('A', 'B')}
                kills[key].add((d['owner'], d['battleId'], d['monsterId']))
            verify_event(row, kills[key], cards, cases[key]); counts[key][row['kind']] += 1
    for r in routes:
        assert r['hero'] == hero and r['source'] == source and r['instanceAudits'] > 0
        assert set(r['players']) == {identity(f"{label}:{hero}:{r['seed']}") for label in ('A', 'B')}
        actual = counts[(r['seed'], r['capacity'])]
        for field, kind in [('knownForeignProbes', 'known-foreign-candidate'), ('ownChoices', 'own-candidate-choice'), ('naturalPvpEntries', 'natural-pvp-entry'), ('checkpointRestores', 'actual-pvp-checkpoint-restored'), ('mutualLeaveReturns', 'pvp-mutual-leave-return')]:
            assert r[field] == actual[kind]
        if terminal_events: assert r['terminalInvariantChecks'] == actual['terminal-pool-cleared'] <= 2
        groups[r['capacity']].update(actual)
        groups[r['capacity']]['routes'] += 1
        groups[r['capacity']]['outcome:' + r['outcome']] += 1
        if 'Pvp' in r['finalPhases']: groups[r['capacity']]['final_PVP_waiting_routes'] += 1
    return {'hero': hero, 'paired_routes': len(routes), 'groups': {k: dict(v) for k, v in groups.items()}, 'metadata_and_Protobuf_only': True, 'no_zero_branch_acceptance': True}
