"""Cloud-only exact old/current B08.3 cast and encounter reconciliation.

This gate compares three paired seeds in one of 36 frozen families. It does
not relabel the original 216000 encounters as current-source executions.
Only Selected.InstanceId has a stable semantic UUID bijection; every other
field, ordered position, outcome and numeric value remains exact.
"""
import argparse
from collections import Counter
import copy
from decimal import Decimal
import gzip
import hashlib
from itertools import zip_longest
import json
import os
from pathlib import Path
import sys
import uuid

OLD = '3a984bc64f5346b7f1d134926deec54be928a060'
CURRENT_RUNTIME = '581cd9f74962dd61424e77c529b1259afbb39fe7'
ARMS = ('BaselineGreenWater', 'SingleGreenReplacement')
FAMILIES = {(h, g, r) for h in ('Mage', 'Priest', 'Guardian')
            for g in ('O1', 'O6', 'E1', 'BOSS')
            for r in ('ET-WOOD-G', 'ET-EARTH-G', 'ET-METAL-G')}
STORAGE = {'raw_sha256', 'stored_bytes', 'stored_sha256'}


def require(value, message):
    if not value:
        raise ValueError(message)


def digest(path):
    value = hashlib.sha256()
    with path.open('rb') as handle:
        for block in iter(lambda: handle.read(65536), b''):
            value.update(block)
    return value.hexdigest()


def read(path):
    require(path.is_file() and not path.is_symlink(), 'Missing or linked original metadata')
    return json.loads(path.read_text(encoding='utf-8'), parse_float=Decimal)


def exact(a, b, path='value'):
    require(type(a) is type(b), 'Exact type differs at ' + path)
    if isinstance(a, dict):
        require(set(a) == set(b), 'Object keys differ at ' + path)
        for key in a:
            exact(a[key], b[key], path + '.' + key)
    elif isinstance(a, list):
        require(len(a) == len(b), 'Array count differs at ' + path)
        for i, (left, right) in enumerate(zip(a, b)):
            exact(left, right, path + '[' + str(i) + ']')
    else:
        require(a == b, 'Exact scalar differs at ' + path)


class CardBijection:
    def __init__(self):
        self.forward = {}
        self.reverse = {}
        self.semantic = {}
        self.uses = 0

    def selected(self, old, current, identity):
        require(isinstance(old, list) and isinstance(current, list)
                and 1 <= len(old) == len(current) <= 5, 'Selected count/order differs')
        require(len({v['InstanceId'] for v in old}) == len(old)
                and len({v['InstanceId'] for v in current}) == len(current), 'Duplicate selected UUID')
        for index, (a, b) in enumerate(zip(old, current)):
            require(set(a) == set(b) and {'InstanceId', 'CardId', 'Level', 'ElementOverride'} <= set(a),
                    'Selected semantic field set differs')
            first, second = a['InstanceId'], b['InstanceId']
            require(isinstance(first, str) and isinstance(second, str)
                    and str(uuid.UUID(first)) == first and str(uuid.UUID(second)) == second,
                    'Selected UUID is not canonical')
            left = {k: v for k, v in a.items() if k != 'InstanceId'}
            right = {k: v for k, v in b.items() if k != 'InstanceId'}
            exact(left, right, 'Selected[' + str(index) + ']')
            key_a, key_b = identity + (first,), identity + (second,)
            require(self.forward.get(key_a, key_b) == key_b
                    and self.reverse.get(key_b, key_a) == key_a, 'Selected UUID bijection changed')
            if key_a in self.semantic:
                exact(self.semantic[key_a], left, 'stable card semantics')
            self.forward[key_a], self.reverse[key_b] = key_b, key_a
            self.semantic[key_a] = left
            self.uses += 1


def compare_cast(old, current, mapping, identity):
    require(set(old) == set(current) and old['Passed'] is current['Passed'] is True,
            'Native cast failed or fields differ')
    mapping.selected(old['Selected'], current['Selected'], identity)
    exact({k: v for k, v in old.items() if k != 'Selected'},
          {k: v for k, v in current.items() if k != 'Selected'}, 'cast')


def rows(path, metadata):
    require(path.is_file() and not path.is_symlink()
            and path.stat().st_size == metadata['stored_bytes']
            and digest(path) == metadata['stored_sha256'], 'Stored original bytes/SHA differ')
    size = count = 0
    value = hashlib.sha256()
    with gzip.open(path, 'rb') as handle:
        for line in handle:
            require(len(line) <= 2 * 1024**2 and line.endswith(b'\n'), 'Unbounded/unterminated JSONL row')
            size += len(line)
            count += 1
            value.update(line)
            row = json.loads(line, parse_float=Decimal)
            require(isinstance(row, dict), 'JSONL row must be an object')
            yield row
    require(size == metadata['raw_bytes'] and value.hexdigest() == metadata['raw_sha256'],
            'Inner gzip CRC/raw bytes/SHA differ')
    require(count == metadata.get('events', metadata.get('rows')), 'Inner row denominator differs')


def metadata(directory, source, family):
    manifest, summary = read(directory / 'manifest.json'), read(directory / 'summary.json')
    require(manifest['schema'] == 'actual_tuning_recovery_experiment_v1'
            and manifest['source_sha'] == summary['source_sha'] == source, 'Actual native source/schema differs')
    require((manifest['hero'], manifest['group'], manifest['alternative']) == family
            and family in FAMILIES and manifest['block_index'] == 0
            and manifest['seed_start'] == 420001 and manifest['samples'] == 3, 'Frozen limited family differs')
    require(summary['passed'] is True and summary['errors'] == 0 and summary['rows'] == 6
            and summary['full_experiment'] is False and summary['required_cases_accepted'] is False
            and summary['main_acceptance_granted'] is False, 'Failed native set or scope inflation')
    names = [p['path'] for p in summary['event_parts']]
    require(names and names == [f'contract-events-{i:03}.jsonl.gz' for i in range(len(names))],
            'Event part order/path differs')
    require({p.name for p in directory.glob('*.jsonl.gz')} == set(names) | {'encounters.jsonl.gz'},
            'Unlisted or absent original gzip part')
    require(sum(p['events'] for p in summary['event_parts']) == summary['actual_casts']
            and sum(p['raw_bytes'] for p in summary['event_parts']) <= 2 * 1024**3,
            'Original collector count/raw ceiling differs')
    return manifest, summary


def events(directory, summary):
    for part in summary['event_parts']:
        yield from rows(directory / part['path'], part)


def controls(witness, multi):
    old, current = witness
    result = []
    def rejects(name, a, b, mapping=None, identity=None):
        try:
            compare_cast(a, b, mapping or CardBijection(), identity or (a['Seed'], a['Profile']))
        except (ValueError, KeyError):
            result.append({'name': name, 'rejected': True})
        else:
            raise ValueError('Corrupt equivalence accepted: ' + name)
    changed = copy.deepcopy(current)
    changed['Draft']['HealthCost'] += 1
    rejects('changed_hp_cost', old, changed)
    changed = copy.deepcopy(current)
    changed['Oracle']['ConflictHeal'] += 1
    rejects('changed_conflict_heal', old, changed)
    left, right = multi
    changed = copy.deepcopy(right)
    changed['Selected'] = list(reversed(changed['Selected']))
    mapping = CardBijection()
    identity = (left['Seed'], left['Profile'])
    mapping.selected(left['Selected'], right['Selected'], identity)
    rejects('permuted_selected_order', left, changed, mapping, identity)
    changed = copy.deepcopy(current)
    changed['Cast'] += 1
    rejects('permuted_cast_identity', old, changed)
    changed = copy.deepcopy(current)
    changed['Selected'][0]['InstanceId'] = 'ffffffff-ffff-4fff-8fff-ffffffffffff'
    mapping = CardBijection()
    identity = (old['Seed'], old['Profile'])
    mapping.selected(old['Selected'], current['Selected'], identity)
    rejects('unstable_selected_UUID', old, changed, mapping, identity)
    changed = copy.deepcopy(current)
    changed['Selected'][0]['CardId'] += '-corrupt'
    rejects('changed_selected_card_semantics', old, changed)
    return result


def compare(original, current, family, with_controls=False):
    m0, s0 = metadata(original, OLD, family)
    m1, s1 = metadata(current, CURRENT_RUNTIME, family)
    exact({k: v for k, v in m0.items() if k != 'source_sha'},
          {k: v for k, v in m1.items() if k != 'source_sha'}, 'manifest business/config')
    skip = STORAGE | {'source_sha', 'event_parts'}
    exact({k: v for k, v in s0.items() if k not in skip},
          {k: v for k, v in s1.items() if k not in skip}, 'summary business/denominators')
    exact([{k: v for k, v in p.items() if k not in STORAGE} for p in s0['event_parts']],
          [{k: v for k, v in p.items() if k not in STORAGE} for p in s1['event_parts']], 'part boundaries/counts')
    expected = {(seed, arm) for seed in range(420001, 420004) for arm in ARMS}
    encounters = {}
    sentinel = object()
    count = 0
    for a, b in zip_longest(rows(original / 'encounters.jsonl.gz', s0),
                          rows(current / 'encounters.jsonl.gz', s1), fillvalue=sentinel):
        require(a is not sentinel and b is not sentinel, 'Missing encounter row')
        identity = (a['Seed'], a['Profile'])
        require(identity in expected and identity not in encounters, 'Missing/duplicate encounter identity')
        exact(a, b, 'encounter')
        encounters[identity] = a
        count += 1
    require(set(encounters) == expected and count == 6, 'Paired encounter coverage differs')
    mapping, ledger = CardBijection(), Counter()
    first = multiple = None
    for a, b in zip_longest(events(original, s0), events(current, s1), fillvalue=sentinel):
        require(a is not sentinel and b is not sentinel, 'Missing/extra original cast')
        identity = (a['Seed'], a['Profile'])
        require(identity in expected and a['Cast'] == ledger[identity], 'Duplicate/reordered cast identity')
        compare_cast(a, b, mapping, identity)
        ledger[identity] += 1
        first = first or (a, b)
        if len(a['Selected']) > 1 and len({v['CardId'] for v in a['Selected']}) > 1:
            multiple = multiple or (a, b)
    require(sum(ledger.values()) == s0['actual_casts'] == s1['actual_casts']
            and all(ledger[key] == encounters[key]['Actions'] for key in expected), 'Complete cast/encounter join differs')
    require(first and (multiple or not with_controls), 'Meaningful multi-card control witness missing')
    return {'ok': True, 'family': list(family), 'old_native_source_sha': OLD,
            'current_native_source_sha': CURRENT_RUNTIME, 'encounters_per_source': 6,
            'unique_native_encounters': 12, 'paired_seeds_per_source': 3,
            'actual_casts_per_source': sum(ledger.values()),
            'outcomes_per_source': dict(Counter(v['Outcome'] for v in encounters.values())),
            'stable_semantic_UUID_bijections': len(mapping.forward), 'ordered_UUID_uses': mapping.uses,
            'old_manifest_sha256': digest(original / 'manifest.json'),
            'current_manifest_sha256': digest(current / 'manifest.json'),
            'old_summary_sha256': digest(original / 'summary.json'),
            'current_summary_sha256': digest(current / 'summary.json'),
            'negative_controls': controls(first, multiple) if with_controls else [],
            'every_numeric_value_exact': True, 'every_nonselected_UUID_exact': True,
            'original_216000_relabelled': False, 'whole_experiment_complete': False,
            'required_cases_accepted': False, 'main_acceptance_granted': False}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--original', required=True, type=Path)
    p.add_argument('--current', required=True, type=Path)
    p.add_argument('--hero', required=True)
    p.add_argument('--group', required=True)
    p.add_argument('--replacement', required=True)
    p.add_argument('--output', required=True, type=Path)
    p.add_argument('--controls', action='store_true')
    a = p.parse_args()
    require(os.name != 'nt' and sys.platform.startswith('linux')
            and os.environ.get('PR13_TUNING_EQ_CONTAINER') == '1', 'Tencent container only; no local business comparison')
    require(not a.output.exists(), 'Original comparison evidence cannot be overwritten')
    result = compare(a.original, a.current, (a.hero, a.group, a.replacement), a.controls)
    a.output.write_bytes((json.dumps(result, indent=2) + '\n').encode('utf-8'))
    print(json.dumps(result))


if __name__ == '__main__':
    main()
