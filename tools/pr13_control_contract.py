"""Validate actual native control ledgers without treating overlap as added time."""
import argparse
import copy
import gzip
import hashlib
import json
from pathlib import Path
import re

CASE_TAGS = {
    'PR13-B08.1-T01': ['first', 'second', 'third'],
    'PR13-B08.1-T02': ['window-start', 'at-7999ms', 'at-8000ms'],
    'PR13-B08.1-T03': ['target-a-first', 'target-b-first', 'pvp-new-window'],
}


def require(value, message):
    if not value:
        raise ValueError(message)


def validate_row(row):
    require(row['passed'] is True and row['error'] is None, 'Native row failed')
    require(row['hero'] in ('Mage', 'Priest', 'Guardian') and type(row['weapon_level']) is int and 0 <= row['weapon_level'] <= 5, 'Unknown stratum')
    require(type(row['seed']) is int and row['seed'] > 0, 'Invalid seed')
    events = row['events']
    require(len(events) == 9, 'Nine authoritative events required')
    require([(e['CaseId'], e['Tag']) for e in events] == [(cid, tag) for cid, tags in CASE_TAGS.items() for tag in tags], 'Original case/order differs')
    for e in events:
        for key in ('RequestedTicks', 'ConvertedTicks', 'AdmittedTicks', 'BeforeRemainingTicks', 'AfterRemainingTicks', 'AddedUnionTicks', 'WindowRemainingTicks'):
            require(type(e[key]) is int and e[key] >= 0, 'Nonnegative native ticks required')
        require(e['RequestedTicks'] > 0 and e['ConvertedTicks'] > 0, 'Actual positive control request required')
        require(e['AfterRemainingTicks'] == max(e['BeforeRemainingTicks'], e['AdmittedTicks']), 'Actual target timer differs')
        require(e['AddedUnionTicks'] == e['AfterRemainingTicks'] - e['BeforeRemainingTicks'], 'Overlap counted as added control')
        require(re.fullmatch('[0-9a-f]{64}', e['RoomStateSha256']) is not None, 'Native state identity missing')
    first, half, zero = events[:3]
    require(first['AdmittedTicks'] == first['ConvertedTicks'] and half['AdmittedTicks'] == first['AdmittedTicks'] // 2 and zero['AdmittedTicks'] == 0, 'Full/half/zero differs')
    require(first['AddedUnionTicks'] == first['AdmittedTicks'] and half['AddedUnionTicks'] == zero['AddedUnionTicks'] == 0, 'Same-instant union differs')
    start, before, after = events[3:6]
    require(start['AdmittedTicks'] == start['ConvertedTicks'] and before['AdmittedTicks'] == start['AdmittedTicks'] // 2 and after['AdmittedTicks'] == start['AdmittedTicks'], 'Eight-second boundary differs')
    require(before['WindowRemainingTicks'] == 10000 and after['WindowRemainingTicks'] == 80000000, 'Window deadline differs')
    a, b, pvp = events[6:]
    require(a['TargetId'] != b['TargetId'] and a['AdmittedTicks'] == b['AdmittedTicks'] == a['ConvertedTicks'] and pvp['AdmittedTicks'] == pvp['ConvertedTicks'] and pvp['WindowRemainingTicks'] == 80000000, 'Target or PVP independence differs')
    assertions = row['assertions']
    require(len(assertions) == 3 and [a['case_id'] for a in assertions] == list(CASE_TAGS) and all(a['passed'] is True for a in assertions), 'Required native assertions missing')
    restore = assertions[-1]
    require(restore['frozen_player_sha256'] == restore['returned_player_sha256'] and restore['frozen_pve_sha256'] == restore['returned_pve_sha256'] and restore['separate_pvp_target_window'] is True, 'Frozen return differs')
    require(assertions[1]['window_removed_at_8000'] is True and assertions[1]['old_window_remaining_at_7999_ticks'] == 10000, 'Native expiry assertion differs')


def inspect_directory(directory):
    summary = json.loads((directory / 'summary.json').read_text())
    raw = directory / 'controls.jsonl.gz'
    require(summary['passed'] is True and summary['errors'] == 0, 'Native summary failed')
    require(raw.stat().st_size == summary['stored_bytes'] and hashlib.sha256(raw.read_bytes()).hexdigest() == summary['stored_sha256'], 'Stored hash/bytes differ')
    seen = set(); digest = hashlib.sha256(); count = 0; byte_count = 0; sample = []
    with gzip.open(raw, 'rb') as stream:
        for text in stream:
            digest.update(text); byte_count += len(text)
            require(byte_count <= 512 * 1024**2, 'Raw bound exceeded')
            row = json.loads(text); validate_row(row)
            identity = (row['seed'], row['hero'], row['weapon_level'])
            require(identity not in seen, 'Duplicate native identity'); seen.add(identity); count += 1
            if row['seed'] == summary['seed_start']: sample.append(row)
    expected = {(seed, hero, level) for seed in range(summary['seed_start'], summary['seed_start'] + summary['samples']) for hero in ('Mage', 'Priest', 'Guardian') for level in range(6)}
    require(seen == expected and count == summary['rows'] and count == summary['samples'] * 18, 'Missing seed/hero/level')
    require(byte_count == summary['raw_bytes'] and digest.hexdigest() == summary['raw_sha256'], 'Original hash/bytes differ')
    vectors = json.loads((directory / 'render-vectors.json').read_text())
    require(vectors['source_sha'] == summary['source_sha'] and len(vectors['vectors']) == 18, 'Native display vectors incomplete')
    by_identity = {(r['hero'], r['weapon_level']): r for r in sample}
    for vector in vectors['vectors']:
        row = by_identity[(vector['hero'], vector['weapon_level'])]
        require(vector['events'] == row['events'] and vector['assertions'] == row['assertions'], 'Vector metrics differ from original native rows')
        for sha, text in vector['states'].items():
            require(hashlib.sha256(text.encode()).hexdigest() == sha, 'Original native state text differs')
        require(all(e['RoomStateSha256'] in vector['states'] for e in vector['events']), 'Event native state text missing')
    return summary, sample


def guards(directory):
    _, rows = inspect_directory(directory); original = rows[0]; results = []
    mutations = {
        'missing-event': lambda r: r['events'].pop(),
        'same-instant-overlap': lambda r: r['events'][1].update(AddedUnionTicks=r['events'][1]['AdmittedTicks']),
        'eight-second-boundary': lambda r: r['events'][5].update(AdmittedTicks=0),
        'target-independence': lambda r: r['events'][7].update(TargetId=r['events'][6]['TargetId']),
        'frozen-pve-return': lambda r: r['assertions'][2].update(returned_pve_sha256='0' * 64),
    }
    for name, mutate in mutations.items():
        row = copy.deepcopy(original); mutate(row)
        try: validate_row(row)
        except ValueError: results.append({'control': name, 'passed': True})
        else: raise AssertionError('Invalid native ledger accepted: ' + name)
    raw = bytearray((directory / 'controls.jsonl.gz').read_bytes()); raw[-8] ^= 1
    try: gzip.decompress(raw)
    except (OSError, EOFError): results.append({'control': 'gzip-crc', 'passed': True})
    else: raise AssertionError('Corrupt CRC accepted')
    return {'ok': True, 'native_corruption_controls': results}


def main():
    p = argparse.ArgumentParser(); p.add_argument('--input', action='append', type=Path, required=True); p.add_argument('--output', type=Path, required=True); p.add_argument('--guards', action='store_true'); args = p.parse_args()
    require(not args.output.exists(), 'New output required')
    if args.guards:
        require(len(args.input) == 1, 'One actual native pilot required'); result = guards(args.input[0])
    else:
        summaries = []; rows = []
        for d in args.input:
            summary, sample = inspect_directory(d); summaries.append(summary); rows.extend(sample)
        require(len({s['source_sha'] for s in summaries}) == 1, 'Mixed native sources')
        require(len({s['seed_start'] for s in summaries}) == len(summaries), 'Duplicate native parts')
        full = len(summaries) == 3 and {s['seed_start'] for s in summaries} == {300001, 301001, 302001} and all(s['samples'] == 1000 for s in summaries)
        result = {'ok': True, 'native_source_sha': summaries[0]['source_sha'], 'full_experiment': full, 'rows': sum(s['rows'] for s in summaries), 'actual_events': sum(s['rows'] for s in summaries) * 9,
                  'summaries': summaries, 'canonical_cases': [{'case_id': cid, 'executed': True, 'status': 'Passed', 'profiles_executed': ['OFFLINE', 'EXPERIMENT'] if full else ['OFFLINE'],
                    'actual': {'native_rows': sum(s['rows'] for s in summaries), 'events_per_row': 3, 'heroes': ['Mage', 'Priest', 'Guardian'], 'weapon_levels': list(range(6)),
                      'sample_native_rows': [{**r, 'events': [e for e in r['events'] if e['CaseId'] == cid], 'assertions': [a for a in r['assertions'] if a['case_id'] == cid]} for r in rows]},
                    'scope': 'Native room boundary fixtures with legal injected hands; no LIVE, human, full-expedition or RENDER claim.'} for cid in CASE_TAGS]}
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n'); print(json.dumps({k: v for k, v in result.items() if k not in ('canonical_cases', 'summaries')}))


if __name__ == '__main__':
    main()
