"""Export B02.3 coverage from clean native PostgreSQL and Godot wire evidence."""
import argparse
import base64
import json
from pathlib import Path
import re
import xml.etree.ElementTree as ET


def read(path):
    return json.loads(path.read_text(encoding='utf8'))


def validate(directory):
    result = read(directory / 'result.json')
    if (result.get('ok') is not True or result.get('inputs_unchanged') is not True
            or result.get('remaining_schemas') != '0'
            or len(result.get('cleanup', {})) != 3
            or any(value is not True for value in result['cleanup'].values())):
        raise ValueError('Actual clean native execution and owned database cleanup required')
    for phase in ['server', 'client']:
        if result[phase]['exit_code'] != 0 or result[phase]['oom_killed']:
            raise ValueError('Failed or OOM native phase cannot discharge a profile')
    root = ET.parse(directory / 'preview.trx').getroot()
    counters = root.find('.//{*}Counters')
    rows = root.findall('.//{*}UnitTestResult')
    if (counters is None or int(counters.get('total', 0)) != 6
            or int(counters.get('executed', 0)) != 6 or int(counters.get('passed', 0)) != 6
            or int(counters.get('notExecuted', 1)) != 0
            or len(rows) != 6 or any(row.get('outcome') != 'Passed' for row in rows)):
        raise ValueError('All six actual TRX rows must be executed and Passed')
    receipts = [read(path) for path in sorted((directory / 'receipts').glob('*.json'))]
    groups = {f'PR13-B02.3-T0{i}': [] for i in (1, 2, 3)}
    for row in receipts:
        if row.get('caseId') not in groups or row.get('status') != 'Passed':
            raise ValueError('Unknown or failed native receipt')
        groups[row['caseId']].append(row)
    pure = groups['PR13-B02.3-T01']
    if {row['variant'] for row in pure} != {'Mage-default', 'Priest-default', 'Guardian-default', 'Guardian-fractional'} or len(pure) != 4:
        raise ValueError('Every hero and fractional guardian fixture required')
    for row in pure:
        actual = row['actual']
        for before, after in [('stateBeforeHash', 'stateAfterPreviewHash'), ('databaseBeforeHash', 'databaseAfterPreviewHash'),
                              ('randomBeforeHash', 'randomAfterHash'), ('deckBeforeHash', 'deckAfterHash')]:
            if not re.fullmatch('[0-9a-f]{64}', actual.get(before, '')) or actual[before] != actual[after]:
                raise ValueError('Preview mutated actual state or database hash')
        preview = dict(actual['preview']); committed = dict(actual['actual'])
        preview.pop('RoomRevision'); committed.pop('RoomRevision')
        if (preview != committed or actual['repeatedPreviews'] != 10 or actual['restoredAfterCommit'] is not True
                or actual['guardianRemainderBefore'] != actual['guardianRemainderAfterPreview']):
            raise ValueError('Preview, commit or remainder contract differs')
    ordered = groups['PR13-B02.3-T02']
    stale = groups['PR13-B02.3-T03']
    if len(ordered) != 1 or len(stale) != 1:
        raise ValueError('Exactly one native protocol and stale-revision receipt required')
    vectors = ordered[0]['actual']['rows']
    if (len(vectors) != 2 or vectors[0]['order'] != list(reversed(vectors[1]['order']))
            or [row['CoreElement'] for row in vectors] != ['Earth', 'Water']
            or ordered[0]['actual']['databaseUnchanged'] is not True):
        raise ValueError('Actual order-dependent authority vectors required')
    for row in vectors:
        for field in ['commandWire', 'responseWire']:
            if not base64.b64decode(row[field], validate=True):
                raise ValueError('Actual native Protobuf wire required')
    actual = stale[0]['actual']
    if (actual['currentRevision'] <= actual['oldRevision'] or actual['Type'] != 'error.command_rejected'
            or actual['beforeHash'] != actual['afterHash'] or actual['durableBeforeHash'] != actual['durableAfterHash']):
        raise ValueError('Stale preview overwrote current authority or durable state')
    client = read(directory / 'client-result.json')
    if client.get('ok') is not True or len(client.get('checks', [])) != 8 or any(row.get('passed') is not True for row in client['checks']):
        raise ValueError('Actual Godot wire and current/stale preview checks required')
    if sum(row.get('case_id') == 'PR13-B02.3-T02' for row in client['checks']) != 4 or sum(row.get('case_id') == 'PR13-B02.3-T03' for row in client['checks']) != 2:
        raise ValueError('Missing client protocol or stale revision observations')
    return result, groups, client


def export(directory, source_sha, evidence_prefix):
    if not re.fullmatch('[0-9a-f]{40}', source_sha):
        raise ValueError('Exact implementation SHA required')
    result, groups, client = validate(directory)
    return [{'case_id': cid, 'executed': True, 'status': 'Passed', 'source_sha': source_sha,
             'profiles_executed': ['OFFLINE', 'POSTGRES'],
             'actual': {'native_postgres_receipts': rows, 'client_checks': [row for row in client['checks'] if row.get('case_id') == cid],
                        'execution_source_base_sha': result['source_base_sha'], 'native_trx_rows': 6, 'skipped': 0},
             'evidence': [evidence_prefix + '/native-result.json', evidence_prefix + '/source-hashes.json',
                          evidence_prefix + '/preview.trx', evidence_prefix + '/client-result.json']}
            for cid, rows in sorted(groups.items())]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--native', type=Path, required=True)
    parser.add_argument('--source-sha', required=True)
    parser.add_argument('--evidence-prefix', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    records = export(args.native, args.source_sha, args.evidence_prefix)
    if args.output.exists():
        raise ValueError('Immutable case output already exists')
    args.output.write_text(''.join(json.dumps(row, ensure_ascii=False) + '\n' for row in records), encoding='utf8')
    print(json.dumps({'executed': len(records), 'passed': len(records), 'skipped': 0}))


if __name__ == '__main__':
    main()
