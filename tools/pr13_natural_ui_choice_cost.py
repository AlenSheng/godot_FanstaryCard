"""Describe every frozen natural UI choice observation on Tencent, with full denominators."""
import argparse
from collections import Counter, defaultdict
import hashlib
import itertools
import json
import os
from pathlib import Path
import platform

NATIVE = '0d56ceccf526f6ae8973f57da152d67faf93a5d5'
READER = '8c6bb777e2d3aea333b6917dcce8f339c2f494c3'
METRIC = 'choice_input_usec_includes_render_and_synthetic_pointer_frames'


def require(value, message):
    if not value:
        raise ValueError(message)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path):
    return json.loads(Path(path).read_bytes())


def timing(row):
    value = row.get(METRIC)
    require(type(value) is int and 0 < value <= 900_000_000, 'Missing, invalid or out-of-budget measured choice time')
    require(row.get('human_decision_time_claimed') is False, 'Synthetic input cannot claim human decision time')
    require(row.get('source_sha') == NATIVE and row.get('reader_source_sha') == READER, 'Exact native and UI reader source required')
    require(row.get('passed') is True, 'Failed UI observation cannot be omitted or described as passing')
    require(bool(row.get('screenshot')) == (row.get('frame_cap') == 30 and row.get('controlled_delay_ms') == 0), 'Capture condition differs')
    return value


def describe(values):
    require(values, 'Empty denominator')
    ordered = sorted(values)

    def quantile(q):
        position = (len(ordered) - 1) * q
        low = int(position)
        high = min(low + 1, len(ordered) - 1)
        return (ordered[low] + (ordered[high] - ordered[low]) * (position - low)) / 1000

    # Rendering repeats are observations, not independent route or player samples.
    return {'N_render_observations': len(values), 'mean_ms': sum(values) / len(values) / 1000,
            'minimum_ms': ordered[0] / 1000, 'median_ms': quantile(.5), 'maximum_ms': ordered[-1] / 1000,
            'P95_ms': quantile(.95) if len(values) >= 100 else None,
            'P99_ms': quantile(.99) if len(values) >= 100 else None,
            'tail_sample_gate': 'N>=100; smaller strata retain null P95/P99',
            'independent_players_or_routes_claimed': False}


def controls():
    valid = {METRIC: 1, 'human_decision_time_claimed': False, 'source_sha': NATIVE,
             'reader_source_sha': READER, 'passed': True, 'frame_cap': 30,
             'controlled_delay_ms': 0, 'screenshot': 'original.png'}
    for mutation in ({METRIC: None}, {METRIC: True}, {METRIC: -1},
                     {'human_decision_time_claimed': True}, {'passed': False}, {'screenshot': ''}):
        try:
            timing(valid | mutation)
        except ValueError:
            continue
        raise ValueError('Invalid evidence negative control was accepted')
    require(describe([1])['P99_ms'] is None, 'A one-observation tail cannot pass the sample gate')
    return {'ok': True, 'rejected_invalid_evidence_controls': 6, 'small_N_tail_control': True,
            'controls_are_not_native_business_samples': True}


def analyze(root):
    require(platform.system() == 'Linux' and os.environ.get('PR13_UI_COST_CLOUD') == 'tencent-descriptive-v1',
            'Statistical computation must run on Tencent in the bounded container')
    root = Path(root)
    index = read(root / 'index.json')
    plan = read(root / 'matrix-plan.json')
    require(index['native_source_sha'] == NATIVE and index['reader_source_sha'] == READER,
            'Frozen source identity differs')
    require(len(index['segments']) == 18 and len({s['slug'] for s in index['segments']}) == 18,
            'All eighteen unique segments are required')
    files = index['files']
    require(len({x['path'] for x in files}) == len(files), 'Duplicate original input path')
    for member in files:
        path = Path(member['path'])
        require(not path.is_absolute() and '..' not in path.parts and '\\' not in member['path'], 'Unsafe input path')
        require((root / path).is_file() and not (root / path).is_symlink()
                and (root / path).stat().st_size == member['bytes'] and sha(root / path) == member['sha256'],
                'An original input member changed')
    groups = defaultdict(list)
    all_times = []
    seen_segments = set()
    vector_identities = set()
    selection_counts = Counter()
    for segment in index['segments']:
        slug = segment['slug']
        native = read(root / segment['native_result'])
        vectors = [json.loads(line) for line in (root / segment['vectors']).read_text().splitlines()]
        require(native['ok'] and not native['development_smoke'] and not native['failures'], 'Original formal UI result failed')
        require(len(vectors) == segment['original_vectors'] == native['original_vectors'], 'Original vector count differs')
        require(native['reader_source_sha'] == READER and native['original_native_source_sha'] == NATIVE, 'Original result source differs')
        rows = native['observations']
        expected = set(itertools.product(range(len(vectors)), map(tuple, plan['resolutions']),
                                         plan['frame_caps'], plan['controlled_response_delay_ms']))
        keys = [(x['index'], tuple(x['resolution']), x['frame_cap'], x['controlled_delay_ms']) for x in rows]
        require(len(rows) == len(set(keys)) == len(expected) == segment['expected_rows'] and set(keys) == expected,
                'Missing, duplicate or unexpected Cartesian UI observation')
        for row in rows:
            vector = vectors[row['index']]
            require(vector['source'] == NATIVE and vector['hero'] == row['hero'] == segment['hero']
                    and vector['seed'] == row['seed'] == segment['seed_start']
                    and vector['capacity'] == row['capacity'] and vector['candidateId'] == row['candidate_id']
                    and row['locale'] == segment['locale'], 'Original natural vector identity differs')
            require(row['actual_full_command_wire'] == vector['commandWire'], 'Original outgoing command bytes differ')
            require(all(row.get(k) is True for k in ('original_command_headers_and_payload_exact',
                    'product_pending_command_registered', 'product_pending_command_cleared',
                    'no_state_change_before_authority', 'original_after_native_snapshot_received',
                    'after_revision_exact', 'popup_closed')), 'Product pending or authority evidence is incomplete')
            action = 'replace' if vector.get('replacement') else 'accept' if vector['accept'] else 'skip'
            value = timing(row)
            capture = bool(row['screenshot'])
            key = (row['hero'], row['capacity'], row['locale'], tuple(row['resolution']),
                   row['frame_cap'], row['controlled_delay_ms'], action, capture)
            groups[key].append(value)
            all_times.append(value)
            vector_identities.add((row['hero'], row['seed'], row['index']))
            selection_counts[action] += 1
        seen_segments.add(slug)
    require(len(seen_segments) == 18 and len(all_times) == 3078 and len(vector_identities) == 57,
            'Full original natural UI denominator differs')
    summaries = []
    for key, values in sorted(groups.items()):
        hero, capacity, locale, size, fps, delay, action, capture = key
        summaries.append({'hero': hero, 'capacity': capacity, 'locale': locale, 'resolution': list(size),
                          'frame_cap': fps, 'controlled_response_delay_ms': delay, 'selection': action,
                          'capture_save_within_measured_interval': capture, **describe(values)})
    result = {'ok': True, 'native_source_sha': NATIVE, 'reader_source_sha': READER,
              'input_index_sha256': sha(root / 'index.json'), 'input_member_count': len(files),
              'all_segments': 18, 'original_native_vectors': 57, 'original_render_observations': 3078,
              'selection_observation_counts': dict(selection_counts), 'all_observations': describe(all_times),
              'strata': summaries, 'negative_controls': controls(), 'analysis_kind': 'descriptive_only',
              'metric': METRIC, 'controlled_response_delay_is_after_this_timer': True,
              'capture_save_overhead_is_included_in_capture_strata': True,
              'all_missing_or_failed_observations_reject_analysis': True,
              'claims': {'human_decision_time': False, 'WAN_latency': False, 'hardware_FPS': False,
                         'causal_capacity_benefit': False, 'independent_render_repeats': False},
              'native_command_wall_CPU_and_economy_remain_separate_in_original_formal_analysis': True,
              'MAIN_accepted': False, 'whole_task_accepted': False}
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--input', required=True)
    p.add_argument('--output', required=True)
    args = p.parse_args()
    result = analyze(args.input)
    with Path(args.output).open('x', encoding='utf-8') as f:
        json.dump(result, f, indent=2, allow_nan=False)
        f.write('\n')
    print(json.dumps({'ok': True, 'segments': 18, 'original_observations': 3078,
                      'MAIN_accepted': False}))


if __name__ == '__main__':
    main()
