"""Inspect exact natural choice JSON and Protobuf metadata; executes no game code."""
import base64
from collections import Counter
import hashlib
import json
from pathlib import Path

from tools.pr13_pool_render_evidence import choose_command, protobuf_fields


CLIENT = {1: 0, 2: 2, 3: 2, 4: 0, 5: 2, 6: 2, 7: 2}
SERVER = {1: 0, 2: 2, 3: 2, 4: 2, 5: 2, 6: 0, 7: 0, 8: 2, 9: 0}
SPECIES = dict(zip(
    ('fire-bat', 'thorn-mite', 'murk-snail', 'sand-lizard', 'rust-rat',
     'box-spirit', 'metal-guard', 'fire-herald', 'marsh-mother',
     'stone-guard', 'thorn-guard', 'annihilation-core'),
    ('FireBat', 'ThornMite', 'MudHydra', 'SandLizard', 'RustRat',
     'BoxSpirit', 'GoldGuard', 'FireReaver', 'SwampMother',
     'StoneGuard', 'ThornGuard', 'VoidCore')))


def wire(value, schema):
    return protobuf_fields(base64.b64decode(value, validate=True), schema)


def piles(deck):
    return [card for name in ('hand', 'library', 'discard') for card in deck[name]]


def verify_choice(row, cards):
    data = row['data']
    cap = row['capacity']
    assert cap in (3, 5, 8)
    candidate = data['candidate']
    assert candidate['level'] == 0 and cards[candidate['cardId']]['monster_type']
    before, after = data['beforeDeck'], data['afterDeck']
    old, new = piles(before), piles(after)
    old_ids = {c['instanceId'] for c in old}
    new_ids = {c['instanceId'] for c in new}
    assert len(old_ids) == len(old) and len(new_ids) == len(new)
    assert candidate['instanceId'] not in old_ids
    assert json.loads(data['resourcesBefore']) == json.loads(data['resourcesAfter'])
    before_active = data['activeBefore']
    after_active = data['activeAfter']
    assert len(old) == 20 + len(before_active)
    assert len(new) == 20 + len(after_active) and len(after_active) <= cap
    accept, replacement = data['accept'], data['replacement']
    if accept:
        assert new_ids == (old_ids - {replacement}) | {candidate['instanceId']}
        assert sum(c['instanceId'] == candidate['instanceId'] for c in after['discard']) == 1
        assert after['hand'] == [c for c in before['hand'] if c['instanceId'] != replacement]
        if replacement:
            assert len(before_active) == cap
            assert any(c['instanceId'] == replacement for c in before_active)
        else:
            assert len(before_active) < cap and len(new) == len(old) + 1
    else:
        assert before == after and before_active == after_active and replacement is None
    assert all(data[k] is True for k in
               ('sameRequestReplayPreserved', 'conflictingReplayRejected', 'foreignOwnerRejected'))
    original = wire(data['firstCommandWire'], CLIENT)
    conflict = wire(data['conflictCommandWire'], CLIENT)
    foreign = wire(data['foreignCommandWire'], CLIENT)
    for command in (original, conflict, foreign):
        assert command[1] == 1 and command[2] == b'monster.choose'
        assert command[3] and command[6] and command[7]
        assert choose_command(command[5])['candidate_id'] == candidate['instanceId']
    assert choose_command(original[5]) == {
        'candidate_id': candidate['instanceId'], 'accept': accept,
        'replace_instance_id': replacement or ''}
    assert conflict[3] == original[3] and conflict[5] != original[5]
    assert choose_command(conflict[5])['accept'] is not accept
    assert all(command[6] == original[6] and command[7] == original[7]
               for command in (conflict, foreign))
    assert foreign[3] != original[3]
    positives = [wire(x, SERVER) for x in data['firstResponseWires']]
    assert positives and not any(x[2].startswith(b'error.') for x in positives)
    assert all(x.get(8) == original[3] for x in positives)
    for frames, request in ((data['conflictResponseWires'], conflict),
                            (data['foreignResponseWires'], foreign)):
        responses = [wire(x, SERVER) for x in frames]
        rejected = [x for x in responses if x[2] == b'error.command_rejected']
        assert len(rejected) == 1 and rejected[0].get(8) == request[3]
        assert protobuf_fields(rejected[0][4], {1: 2, 2: 2})[1]
    monster_type = cards[candidate['cardId']]['monster_type']
    matches = []
    for monster in data['actualNativeDeadMonsters']:
        species = monster[:-2] if monster.endswith(('-a', '-b')) else monster
        if SPECIES.get(species) == monster_type:
            source = data['candidateNativeBattleId'] + ':' + monster
            if source in data['grantedSources']:
                matches.append(source)
    assert matches, 'Candidate has no actual matching native kill batch source'
    # Multiple identical native kills are a batch relation. Do not invent an
    # individual candidate-to-monster assignment absent from the original data.
    return {'operation': data['operation'], 'replaced_pile': data['replacedPile'],
            'matching_native_kill_batch_sources': len(matches)}


def verify_segment(directory, hero, seed_start, seed_count, catalog_path):
    directory = Path(directory)
    cards = {x['id']: x for x in json.loads(Path(catalog_path).read_bytes())['tables']['Cards']}
    routes = [json.loads(line) for line in (directory / 'routes.jsonl').read_text().splitlines()]
    assert len(routes) == seed_count * 4
    assert {(x['hero'], x['seed'], x['capacity']) for x in routes} == {
        (hero, seed, cap) for seed in range(seed_start, seed_start + seed_count) for cap in (0, 3, 5, 8)}
    groups = {cap: Counter() for cap in (0, 3, 5, 8)}
    for row in routes:
        assert row['source'] == '700d237d8ffe155582a3bbd381257da2a688ad8d'
        assert row['hiddenOrderNegativeRejected'] and row['instanceConservationChecks'] > 0
        assert row['nativeCommandCalls'] == row['typedRequestCount']
        assert row['outcome'] in ('Dead', 'Extracted', 'ObservationBudgetCensored')
        if row['outcome'] == 'ObservationBudgetCensored':
            assert row['censorReason'] and row['finalPhase']
        groups[row['capacity']]['routes'] += 1
        groups[row['capacity']]['outcome:' + row['outcome']] += 1
    event_count = 0
    with (directory / 'events.jsonl').open(encoding='utf-8') as stream:
        for line in stream:
            row = json.loads(line)
            assert row['hero'] == hero and seed_start <= row['seed'] < seed_start + seed_count
            assert row['source'] == '700d237d8ffe155582a3bbd381257da2a688ad8d'
            if row['kind'] != 'monster-choice':
                continue
            value = verify_choice(row, cards)
            groups[row['capacity']]['operation:' + value['operation']] += 1
            groups[row['capacity']]['replacement-pile:' + value['replaced_pile']] += 1
            event_count += 1
    assert event_count == sum(x['monsterChoices'] for x in routes)
    return {'hero': hero, 'routes': len(routes), 'choice_events_independently_verified': event_count,
            'groups': {cap: dict(values) for cap, values in groups.items()},
            'route_bytes_sha256': hashlib.sha256((directory / 'routes.jsonl').read_bytes()).hexdigest(),
            'all_declared_routes_and_terminal_censored_outcomes_retained': True,
            'no_native_game_code_or_statistics_executed_by_verifier': True}
