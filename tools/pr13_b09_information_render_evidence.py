"""Validate controlled B09.4 GUI evidence without admitting injected experiment frames."""
import argparse
from collections import Counter
import hashlib
import itertools
import json
from pathlib import Path

NATIVE = 'feeb8ac2ee517945f235d8f5571f79cb713948f5'


def require(condition, message):
    if not condition:
        raise ValueError(message)


def read(path):
    return json.loads(Path(path).read_bytes())


def original_frame_eligible(original, candidate):
    require(original and candidate == original, 'Controlled injected frame is not an original native experiment frame')
    return True


def varint(raw, cursor):
    value = 0
    for shift in range(0, 70, 7):
        require(cursor < len(raw), 'Truncated Protobuf varint')
        byte = raw[cursor]
        cursor += 1
        value |= (byte & 127) << shift
        if not byte & 128:
            return value, cursor
    raise ValueError('Invalid Protobuf varint')


def fields(raw):
    cursor = 0
    result = []
    while cursor < len(raw):
        start = cursor
        tag, cursor = varint(raw, cursor)
        number, wire = tag >> 3, tag & 7
        require(number > 0, 'Zero Protobuf field')
        if wire == 0:
            value, cursor = varint(raw, cursor)
        elif wire in (1, 5):
            size = 8 if wire == 1 else 4
            value = raw[cursor:cursor + size]
            cursor += size
        elif wire == 2:
            size, cursor = varint(raw, cursor)
            value = raw[cursor:cursor + size]
            require(len(value) == size, 'Truncated length-delimited value')
            cursor += size
        else:
            raise ValueError('Unsupported Protobuf wire type')
        require(cursor <= len(raw), 'Truncated Protobuf field')
        result.append((number, wire, value, raw[start:cursor]))
    return result


def injected_frame_control(original, injected, ids):
    import base64
    before, after = fields(original), fields(injected)
    require([(n, t, v) for n, t, v, _ in before if n != 4] ==
            [(n, t, v) for n, t, v, _ in after if n != 4], 'Original envelope metadata changed')
    before_payload = [v for n, t, v, _ in before if n == 4 and t == 2]
    after_payload = [v for n, t, v, _ in after if n == 4 and t == 2]
    require(len(before_payload) == len(after_payload) == 1, 'Exactly one actual server-envelope payload required')
    require(after_payload[0].startswith(before_payload[0]), 'Original snapshot payload was changed')
    extensions = fields(after_payload[0][len(before_payload[0]):])
    require(len(extensions) == 1 and extensions[0][0:2] == (60000, 2), 'Only the declared hidden-order extension is permitted')
    require(json.loads(extensions[0][2]) == {'hidden_library_order': ids}, 'Actual native hidden-order IDs differ')
    try:
        original_frame_eligible(original, injected)
    except ValueError:
        return {'injected_original_frame_rejected': True,
                'original_metadata_preserved': True,
                'original_payload_preserved_with_only_declared_extension': True,
                'injected_wire_sha256': hashlib.sha256(injected).hexdigest()}
    raise ValueError('Injected bytes were accepted as a native experiment frame')


def validate(corpus_path, native_path, probe=False):
    import base64
    corpus, result = read(corpus_path), read(native_path)
    require(corpus['kind'] == 'declared_native_snapshot_RENDER_controls' and corpus['native_source_sha'] == NATIVE,
            'Declared native source corpus required')
    rows = corpus['rows']
    require(len(rows) == 18 and len({(r['hero'], r['seed'], r['optional']) for r in rows}) == 18,
            'All eighteen distinct original snapshots required')
    require(result['ok'] and result['development_smoke'] is probe and result['native_source_sha'] == NATIVE
            and result['no_new_natural_experiment_samples'] and not result['default_rule_changed'],
            'Actual clean controlled GUI result required')
    require(result['locale'] in ('zh-CN', 'en'), 'Actual frozen locale required')
    resolutions = [(960, 540)] if probe else [(1920, 1080), (1280, 720), (960, 540)]
    fps = [30] if probe else [30, 60, 144]
    delays = [0] if probe else [0, 250, 1000]
    expected = set(itertools.product(range(18), resolutions, fps, delays))
    seen = set()
    images = set()
    counts = Counter()
    for observation in result['observations']:
        key = (observation['index'], tuple(observation['resolution']), observation['frame_cap'], observation['controlled_delay_ms'])
        require(key in expected and key not in seen, 'Duplicate or undeclared observation')
        seen.add(key)
        row = rows[observation['index']]
        require((observation['case_id'], observation['hero'], observation['seed'], observation['locale']) ==
                (row['case_id'], row['hero'], row['seed'], result['locale']), 'Case or native row identity changed')
        original = base64.b64decode(row['original_response_wire'], validate=True)
        require(observation['original_response_wire'] == row['original_response_wire']
                and original_frame_eligible(original, original)
                and hashlib.sha256(original).hexdigest() == row['original_response_sha256'], 'Original native bytes changed')
        for flag in ('passed', 'original_snapshot_applied_without_projection',
                     'no_state_change_while_controlled_snapshot_waiting', 'unsupported_hidden_order_action_denied',
                     'unsupported_hidden_order_schema_denied', 'no_hidden_order_packet_or_pending_command',
                     'actual_hidden_library_fields_and_ids_absent_from_public_state',
                     'public_state_and_popup_labels_unchanged_by_extension', 'controlled_injection_only'):
            require(observation[flag] is True, 'Missing actual control: ' + flag)
        require(observation['injected_frame_eligible_as_original_native_experiment'] is False
                and observation['natural_experiment_samples_added'] == 0
                and observation['human_experience_claimed'] is False, 'Injected controls cannot add experimental samples')
        if row['optional']:
            require(observation['unknown_extension_field'] == 60000 and observation['original_popup_opened'], 'Hidden-order GUI injection absent')
            injected_frame_control(original, base64.b64decode(observation['injected_response_wire'], validate=True),
                                   row['actual_hidden_library_instance_ids'])
            require(observation['visible_labels'] and all(x['inside'] and x['all_lines_visible'] for x in observation['visible_labels']),
                    'Actual popup labels clipped')
        else:
            require(observation['default_optional_pool_entry_and_choice_absent'] is True
                    and not observation['injected_response_wire'] and observation['unknown_extension_field'] == 0,
                    'Official default-off control changed')
        require(observation['full_formal_default_rule_changed'] is False, 'Formal default changed')
        images.update(observation['captures'])
        counts[row['case_id']] += 1
    require(seen == expected and len(images) == (9 if probe else 27), 'Missing full matrix or original capture denominator')
    require(counts == {'PR13-B09.4-T02': 9 if probe else 243, 'PR13-B09.4-T03': 9 if probe else 243},
            'Case observation denominators changed')
    return {'ok': True, 'source_sha': result['source_sha'], 'native_source_sha': NATIVE,
            'locale': result['locale'], 'actual_observations': len(seen), 'actual_case_counts': dict(counts),
            'original_PNGs': len(images), 'injected_frames_rejected_from_experiment': counts['PR13-B09.4-T02'],
            'development_smoke': probe, 'native_experiment_observations_added': 0, 'MAIN_accepted': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--corpus', required=True)
    parser.add_argument('--result', required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--development-smoke', action='store_true')
    args = parser.parse_args()
    proof = validate(args.corpus, args.result, args.development_smoke)
    with Path(args.output).open('x', encoding='utf-8') as f:
        json.dump(proof, f, indent=2)
        f.write('\n')
    print(json.dumps(proof))


if __name__ == '__main__':
    main()
