"""Validate actual typed native vector metadata without executing game code."""
import base64
from collections import Counter
import hashlib
import json
from pathlib import Path

from tools.pr13_natural_choice_evidence import CLIENT, SERVER, wire
from tools.pr13_pool_render_evidence import choose_command, varint


def fields(raw):
    assert 0 <= len(raw) <= 1024 * 1024
    result = {}
    offset = 0
    while offset < len(raw):
        tag, offset = varint(raw, offset)
        number, kind = tag >> 3, tag & 7
        assert number > 0 and kind in (0, 2)
        if kind == 0:
            value, offset = varint(raw, offset)
        else:
            size, offset = varint(raw, offset)
            assert size <= len(raw) - offset
            value = raw[offset:offset + size]
            offset += size
        result.setdefault(number, []).append(value)
    return result


def one(values, number, default=None):
    found = values.get(number, [])
    assert len(found) <= 1
    return found[0] if found else default


def snapshot(encoded):
    envelope = wire(encoded, SERVER)
    assert envelope[2] == b'room.snapshot'
    data = fields(envelope[4])
    player = fields(one(data, 9))
    pool = fields(one(player, 20, b''))
    return {'room_id': one(data, 1).decode(), 'match_id': one(data, 2).decode(),
            'revision': one(data, 3, 0), 'owner_id': one(player, 1).decode(),
            'hero': one(player, 2).decode(), 'phase': one(player, 3).decode(),
            'pool': pool, 'hand': player.get(5, []),
            'library': one(player, 6, 0), 'discard': one(player, 7, 0),
            'duel': fields(one(data, 11, b'')), 'payload': envelope[4]}


def verify_vector(row):
    before = snapshot(row['beforeWire'])
    assert (before['room_id'], before['match_id'], before['owner_id']) == (row['roomId'], row['matchId'], row['ownerId'])
    command = wire(row['commandWire'], CLIENT)
    assert command[6].decode() == row['roomId'] and command[7].decode() == row['matchId']
    responses = [wire(x, SERVER) for x in row['responseWires']]
    assert responses and all(x.get(8) == command[3] for x in responses)
    if row['operation'] == 'foreign':
        assert before['phase'] == 'Choice' and command[2] == b'monster.choose'
        candidate = choose_command(command[5])['candidate_id']
        own_candidates = [one(fields(card), 1).decode() for card in before['pool'].get(2, [])]
        assert own_candidates and candidate not in own_candidates
        assert len(responses) == 1 and responses[0][2] == b'error.command_rejected'
    elif row['operation'] == 'choice-replay':
        assert command[2] == b'monster.choose' and before['phase'] == 'Choice'
        replay = [wire(x, SERVER) for x in row['replayWires']]
        assert replay and all(x.get(8) == command[3] for x in replay)
        first_snapshots = [snapshot(x) for x in row['responseWires'] if wire(x, SERVER)[2] == b'room.snapshot']
        replay_snapshots = [snapshot(x) for x in row['replayWires'] if wire(x, SERVER)[2] == b'room.snapshot']
        assert len(first_snapshots) == len(replay_snapshots) == 1
        assert first_snapshots[0]['payload'] == replay_snapshots[0]['payload']
    else:
        assert row['operation'] == 'pvp-state' and before['phase'] == 'Pvp' and before['duel']
        assert command[2] == b'duel.leave'
        after = snapshot(row['afterSnapshotWire'])
        assert after['owner_id'] == before['owner_id'] and after['room_id'] == before['room_id'] and after['match_id'] == before['match_id']
        assert after['phase'] != 'Pvp' and not after['duel']
        assert after['pool'] == before['pool']
    return row['operation']


def verify(directory, hero, source):
    path = Path(directory) / 'render-vectors.jsonl'
    counts = Counter()
    with path.open() as f:
        for line in f:
            row = json.loads(line)
            assert row['hero'] == hero and row['source'] == source
            assert 484001 <= row['seed'] < 484005 and row['capacity'] in (0, 3, 5, 8)
            counts[(row['capacity'], verify_vector(row))] += 1
    return {'hero': hero, 'vectors_verified': sum(counts.values()),
            'groups': [{'capacity': c, 'operation': op, 'vectors': n} for (c, op), n in sorted(counts.items())],
            'original_vector_sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
            'actual_original_typed_frames_only': True, 'RENDER_executed': False}
