"""Exact original/new PR13 collector pilot reconciliation, without combat.

Only selected card InstanceId may have a stable cross-run UUID bijection.
Its CardId, Level, shield, ordered position and every later use still match.
No global UUID removal, numeric tolerance or discarded outcome is allowed.
The original/default/16 GiB pilots all retain three paired seeds and every
cast, tick, encounter, scalar, equipment field and case denominator.
"""
import argparse
from collections import Counter, defaultdict
from decimal import Decimal
import gzip
import hashlib
import json
from pathlib import Path
import re
import uuid


BUSINESS = 'b0423bfe6fedc3f034ba12c8400df5ebb8713f32'
REVISION = 'cap-effective-raw-budget-v2'
DEFAULT_RAW = 2 * 1024**3
RAISED_RAW = 16 * 1024**3
BLOCK = 65536
PROVENANCE = {'schema', 'source_sha', 'business_source_sha', 'instrumentation_source_sha',
              'mixed_input_manifest_sha256', 'collector_revision', 'raw_unit_limit_bytes',
              'raw_unit_limit_explicit', 'event_raw_bytes', 'collection_complete'}
STORAGE = {'raw_sha256', 'stored_bytes', 'stored_sha256'}


def require(value, message):
    if not value:
        raise ValueError(message)


def read(path):
    require(path.is_file() and not path.is_symlink(), 'Missing or linked original metadata')
    return json.loads(path.read_text(encoding='utf-8'), parse_float=Decimal)


def sha(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(BLOCK), b''):
            digest.update(block)
    return digest.hexdigest()


def exact(left, right, path='value'):
    if isinstance(left, dict):
        require(isinstance(right, dict) and set(left) == set(right), 'Object keys differ at ' + path)
        for key in left:
            exact(left[key], right[key], path + '.' + key)
    elif isinstance(left, list):
        require(isinstance(right, list) and len(left) == len(right), 'Array size differs at ' + path)
        for index, (a, b) in enumerate(zip(left, right)):
            exact(a, b, path + '[' + str(index) + ']')
    else:
        require(type(left) is type(right) and left == right, 'Exact scalar differs at ' + path)


class CardBijection:
    def __init__(self):
        self.forward = {}
        self.reverse = {}
        self.semantic = {}
        self.uses = 0

    def selected(self, original, candidate, encounter):
        require(isinstance(original, list) and isinstance(candidate, list)
                and 1 <= len(original) == len(candidate) <= 5, 'Ordered selected card count differs')
        for index, (left, right) in enumerate(zip(original, candidate)):
            require(set(left) == set(right) and {'InstanceId', 'CardId', 'Level', 'shield'} <= set(left),
                    'Selected card field set differs')
            a, b = left['InstanceId'], right['InstanceId']
            require(isinstance(a, str) and isinstance(b, str)
                    and str(uuid.UUID(a)) == a and str(uuid.UUID(b)) == b, 'Noncanonical card UUID')
            semantic_left = {key: value for key, value in left.items() if key != 'InstanceId'}
            semantic_right = {key: value for key, value in right.items() if key != 'InstanceId'}
            exact(semantic_left, semantic_right, 'selected[' + str(index) + ']')
            key_a, key_b = encounter + (a,), encounter + (b,)
            require(self.forward.get(key_a, key_b) == key_b and self.reverse.get(key_b, key_a) == key_a,
                    'Card UUID mapping is not a stable bijection')
            require(self.semantic.get(key_a, semantic_left) == semantic_left,
                    'A card UUID changed its CardId, Level, shield or semantic fields')
            self.forward[key_a] = key_b
            self.reverse[key_b] = key_a
            self.semantic[key_a] = semantic_left
            self.uses += 1


def jsonl(path, metadata):
    require(path.is_file() and not path.is_symlink() and path.stat().st_size == metadata['stored_bytes']
            and sha(path) == metadata['stored_sha256'], 'Original compressed member bytes/SHA differ')
    digest = hashlib.sha256()
    size = count = 0
    with gzip.open(path, 'rb') as stream:
        while True:
            line = stream.readline(2 * 1024**2 + 1)
            if not line:
                break
            require(len(line) <= 2 * 1024**2 and line.endswith(b'\n'), 'Unexpected original JSONL line')
            digest.update(line)
            size += len(line)
            count += 1
            row = json.loads(line, parse_float=Decimal)
            require(isinstance(row, dict), 'Original JSONL row is not an object')
            yield row
    require(size == metadata['raw_bytes'] and digest.hexdigest() == metadata['raw_sha256'],
            'Original inner gzip CRC/raw SHA/bytes differ')
    expected = metadata['events'] if 'events' in metadata else metadata['rows']
    require(count == expected, 'Original inner gzip row count differs')


def metadata(directory, original, mixed, instrumentation, inputs_sha, raw_limit):
    manifest = read(directory / 'manifest.json')
    summary = read(directory / 'summary.json')
    require(manifest['samples'] == 3 and manifest['seed_start'] == 440001
            and manifest['block_index'] == 0 and manifest['hero'] == 'Mage'
            and manifest['group'] == 'E1' and manifest['element'] == 'Water'
            and manifest['equipment_level'] == manifest['weapon_level'] == 5,
            'Pilot must retain all three frozen Water L5 B0 paired seeds')
    require(summary['passed'] is True and summary['errors'] == 0 and summary['rows'] == 6
            and summary['full_unit'] is False and summary['full_experiment_complete'] is False
            and summary['required_cases_accepted'] is False and summary['main_acceptance_granted'] is False,
            'Pilot failure or incorrect formal scope')
    source = BUSINESS if original else mixed
    require(manifest['source_sha'] == summary['source_sha'] == source, 'Original/mixed native source mismatch')
    if original:
        require(manifest['schema'] == 'actual_cap_effective_experiment_v1'
                and not (set(manifest) & (PROVENANCE - {'source_sha', 'schema'})), 'Original collector provenance changed')
    else:
        require(manifest['schema'] == 'actual_cap_effective_experiment_v2', 'Instrumented collector schema differs')
        for data in (manifest, summary):
            require(data['business_source_sha'] == BUSINESS and data['instrumentation_source_sha'] == instrumentation
                    and data['mixed_input_manifest_sha256'] == inputs_sha and data['collector_revision'] == REVISION
                    and data['raw_unit_limit_bytes'] == raw_limit and data['collection_complete'] is True
                    and data['event_raw_bytes'] == sum(part['raw_bytes'] for part in summary['event_parts']),
                    'Exact instrumented provenance/raw accounting differs')
            require(data['raw_unit_limit_explicit'] is (raw_limit == RAISED_RAW),
                    'Pilot budget default/explicit selection differs')
    names = [part['path'] for part in summary['event_parts']]
    require(names and len(names) == len(set(names)) and names == [f'cap-events-{i:03}.jsonl.gz' for i in range(len(names))],
            'Original event part order/identity differs')
    require(sum(part['raw_bytes'] for part in summary['event_parts']) <= raw_limit,
            'Observed raw bytes exceed explicitly declared collector ceiling')
    require(sum(part['events'] for part in summary['event_parts']) == summary['actual_casts'] + summary['actual_ticks'],
            'Summary original event counts differ')
    expected_files = set(names) | {'encounters.jsonl.gz'}
    require({p.name for p in directory.glob('*.jsonl.gz')} == expected_files, 'Unexpected or missing original gzip part')
    return manifest, summary


def events(directory, summary):
    for part in summary['event_parts']:
        yield from jsonl(directory / part['path'], part)


def compare(original, candidate, mixed, instrumentation, inputs_sha, raw_limit):
    m0, s0 = metadata(original, True, mixed, instrumentation, inputs_sha, DEFAULT_RAW)
    m1, s1 = metadata(candidate, False, mixed, instrumentation, inputs_sha, raw_limit)
    exact({k: v for k, v in m0.items() if k not in PROVENANCE},
          {k: v for k, v in m1.items() if k not in PROVENANCE}, 'manifest.business')
    require(set(m1) - set(m0) <= PROVENANCE, 'Unexplained added collector manifest field')
    exact({k: v for k, v in s0.items() if k not in PROVENANCE | STORAGE | {'event_parts'}},
          {k: v for k, v in s1.items() if k not in PROVENANCE | STORAGE | {'event_parts'}}, 'summary.business')
    require(set(s1) - set(s0) <= PROVENANCE, 'Unexplained added collector summary field')
    exact([{k: v for k, v in p.items() if k not in STORAGE} for p in s0['event_parts']],
          [{k: v for k, v in p.items() if k not in STORAGE} for p in s1['event_parts']], 'event_parts.boundaries_counts')
    encounter0 = {(row['Seed'], row['Profile']): row for row in jsonl(original / 'encounters.jsonl.gz', s0)}
    encounter1 = {(row['Seed'], row['Profile']): row for row in jsonl(candidate / 'encounters.jsonl.gz', s1)}
    keys = {(seed, arm) for seed in range(440001, 440004) for arm in ('BaselinePurple', 'SingleOrangeHead')}
    require(set(encounter0) == set(encounter1) == keys and len(encounter0) == len(encounter1) == 6,
            'Paired encounter identity is missing or duplicated')
    for key in keys:
        exact(encounter0[key], encounter1[key], 'encounter.' + repr(key))
    ledger = defaultdict(Counter)
    bijection = CardBijection()
    sentinel = object()
    total = 0
    first_cast = None
    from itertools import zip_longest
    for left, right in zip_longest(events(original, s0), events(candidate, s1), fillvalue=sentinel):
        require(left is not sentinel and right is not sentinel, 'Missing/extra actual event')
        identity = (left['Seed'], left['Profile'])
        require(identity in keys and left['kind'] in ('cast', 'tick'), 'Unexpected original event identity')
        kind = left['kind']
        field = 'action' if kind == 'cast' else 'step'
        key = identity + (kind, left[field])
        require((right['Seed'], right['Profile'], right['kind'], right[field]) == key
                and left[field] == ledger[identity][kind], 'Missing/duplicate/reordered actual cast or tick key')
        require(left['passed'] is True and right['passed'] is True, 'Native event contract failed')
        if kind == 'cast':
            bijection.selected(left['selected'], right['selected'], identity)
            exact({k: v for k, v in left.items() if k != 'selected'},
                  {k: v for k, v in right.items() if k != 'selected'}, 'cast.' + repr(key))
            first_cast = first_cast or (left, right)
        else:
            exact(left, right, 'tick.' + repr(key))
        ledger[identity][kind] += 1
        total += 1
    require(total == s0['actual_casts'] + s0['actual_ticks'] == s1['actual_casts'] + s1['actual_ticks'],
            'Complete one-to-one actual event count differs')
    require(sum(v['cast'] for v in ledger.values()) == s0['actual_casts']
            and sum(v['tick'] for v in ledger.values()) == s0['actual_ticks'], 'Complete per-kind event coverage differs')
    require(all(ledger[key]['cast'] == encounter0[key]['Actions'] for key in keys),
            'Encounter action ledger differs from joined raw casts')
    outcomes = Counter(row['Outcome'] for row in encounter0.values())
    require(sum(outcomes.values()) == 6, 'An original outcome was discarded')
    return {'ok': True, 'candidate_raw_unit_limit_bytes': raw_limit,
            'encounters_exactly_joined': 6, 'paired_seeds_exactly_joined': 3,
            'actual_casts_exactly_joined': s0['actual_casts'], 'actual_ticks_exactly_joined': s0['actual_ticks'],
            'actual_events_exactly_joined': total, 'all_outcomes_retained': dict(outcomes),
            'stable_semantic_card_UUID_bijections': len(bijection.forward), 'ordered_card_UUID_uses_verified': bijection.uses,
            'all_nonselected_UUID_fields_exact': True, 'numeric_tolerance_used': False,
            'original_summary_sha256': sha(original / 'summary.json'),
            'candidate_summary_sha256': sha(candidate / 'summary.json'),
            'original_directory': str(original), 'candidate_directory': str(candidate)}, first_cast


def negative_controls(witness):
    import copy
    left, right = witness
    controls = []
    def rejects(name, function):
        try:
            function()
        except (ValueError, KeyError):
            controls.append({'name': name, 'rejected': True})
        else:
            raise ValueError('Equivalence negative control accepted: ' + name)
    altered = copy.deepcopy(right)
    altered['before']['Shield'] += 1
    rejects('changed_scalar_state', lambda: exact(left['before'], altered['before']))
    altered = copy.deepcopy(right)
    altered['equipment']['BulwarkShieldBonus'] += Decimal('0.01')
    rejects('changed_equipment_attribute', lambda: exact(left['equipment'], altered['equipment']))
    mapping = CardBijection()
    identity = (left['Seed'], left['Profile'])
    mapping.selected(left['selected'], right['selected'], identity)
    altered = copy.deepcopy(right['selected'])
    altered[0]['InstanceId'] = str(uuid.UUID('ffffffff-ffff-4fff-8fff-ffffffffffff'))
    rejects('unstable_card_UUID_mapping', lambda: mapping.selected(left['selected'], altered, identity))
    altered = copy.deepcopy(right['selected'])
    altered[0]['CardId'] += '-changed'
    rejects('changed_card_semantics', lambda: CardBijection().selected(left['selected'], altered, identity))
    return controls


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--original', type=Path, required=True)
    parser.add_argument('--candidate-default', type=Path, required=True)
    parser.add_argument('--candidate-16g', type=Path, required=True)
    parser.add_argument('--mixed-source-sha', required=True)
    parser.add_argument('--instrumentation-source-sha', required=True)
    parser.add_argument('--mixed-input-manifest-sha256', required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--controls', action='store_true')
    args = parser.parse_args()
    require(re.fullmatch('[0-9a-f]{40}', args.mixed_source_sha)
            and re.fullmatch('[0-9a-f]{40}', args.instrumentation_source_sha)
            and args.mixed_source_sha != BUSINESS
            and re.fullmatch('[0-9a-f]{64}', args.mixed_input_manifest_sha256), 'Exact source/inputs anchors required')
    require(not args.output.exists(), 'Existing equivalence result cannot be overwritten')
    compared = []
    witnesses = []
    for directory, budget in ((args.candidate_default, DEFAULT_RAW), (args.candidate_16g, RAISED_RAW)):
        result, witness = compare(args.original, directory, args.mixed_source_sha,
                                  args.instrumentation_source_sha, args.mixed_input_manifest_sha256, budget)
        compared.append(result)
        witnesses.append(witness)
    controls = negative_controls(witnesses[0]) if args.controls else []
    result = {'ok': True, 'business_source_sha': BUSINESS, 'source_sha': args.mixed_source_sha,
              'instrumentation_source_sha': args.instrumentation_source_sha,
              'mixed_input_manifest_sha256': args.mixed_input_manifest_sha256,
              'collector_revision': REVISION, 'comparisons': compared, 'negative_controls': controls,
              'three_complete_original_pilot_sets_retained': True,
              'same_business_values_equipment_state_outcomes_and_order': True,
              'GUID_exception_only_stable_selected_card_semantic_bijection': True,
              'storage_provenance_whitelist_only': sorted(PROVENANCE | STORAGE),
              'whole_experiment_complete': False, 'main_acceptance_granted': False,
              'full_270_unit_dispatch_authorized_by_this_tool': False}
    args.output.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8', newline='\n')
    print(json.dumps(result), flush=True)


if __name__ == '__main__':
    main()
