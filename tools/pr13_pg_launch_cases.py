"""Export exact PR13 launch fault cases from actual native PostgreSQL receipts."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import xml.etree.ElementTree as ET

CONTRACTS = {
    'snapshot': ('Launch_failure_retries_without_duplicate_room_or_asset_reservation(fault: "snapshot")', ['PR13-A04.3-T01', 'LOAD-09.2-T01']),
    'registry': ('Launch_failure_retries_without_duplicate_room_or_asset_reservation(fault: "registry")', ['PR13-A04.3-T02']),
    'mark-running-response-loss': ('MarkRunning_commit_response_loss_retries_same_room_and_restart_restores_it', ['PR13-A04.3-T03']),
}


def export(receipts: Path, trx: Path, proof: dict, plan: dict):
    source = proof.get('source_sha', '')
    if not re.fullmatch('[0-9a-f]{40}', source):
        raise ValueError('Exact execution source SHA required')
    if proof.get('exit_code') != 0 or proof.get('owned_databases_removed') is not True:
        raise ValueError('Successful native run and owned database cleanup required')
    tree = ET.parse(trx)
    counts = tree.find('.//{*}Counters')
    if counts is None:
        raise ValueError('Actual TRX counters required')
    counters = {k: int(v) for k, v in counts.attrib.items()}
    if counters.get('total', 0) < 3 or counters.get('passed') != counters.get('total') or counters.get('executed') != counters.get('total') or counters.get('notExecuted', 0):
        raise ValueError('Failed, skipped or incomplete native matrix')
    results = list(tree.findall('.//{*}UnitTestResult'))
    data = {}
    for line in receipts.read_text('utf-8').splitlines():
        row = json.loads(line)
        fault = row.get('fault')
        if fault not in CONTRACTS or fault in data or row.get('sourceSha') != source or row.get('schemaVersion') != 1 or row.get('status') != 'Passed':
            raise ValueError('Unknown, duplicate or foreign-source native receipt')
        selector, _ = CONTRACTS[fault]
        matched = [r for r in results if r.get('testName', '').endswith('PostgresLifecycleRecoveryTests.' + selector)]
        if len(matched) != 1 or matched[0].get('outcome') != 'Passed':
            raise ValueError('Receipt must match one actually passed native assertion row')
        actual = row['actual']
        common = actual.get('durableStatus') == 'Running' and actual.get('roomCount') == 1 and actual.get('potionCount') == 0 and actual.get('startMovementCount') == 1
        if fault == 'mark-running-response-loss':
            valid = common and actual.get('faultObserved') is True and actual.get('restoredSameRoom') is True and actual.get('restoredSameMatch') is True
        else:
            valid = common and actual.get('failedStatus') == 'Launching' and actual.get('failedRoomPresent') is False and actual.get('sameRoom') is True and actual.get('sameMatch') is True
        if not valid:
            raise ValueError('Native observed launch/route/resource postcondition contradicts contract')
        data[fault] = (row, hashlib.sha256(line.encode('utf-8')).hexdigest(), matched[0].get('testName'))
    if set(data) != set(CONTRACTS):
        raise ValueError('All three fault points required')
    contracts = {c['id']: c for p in plan['packages'] for t in p['subtasks'] for c in t['test_cases']}
    output = []
    for fault, (_, ids) in CONTRACTS.items():
        row, digest, test_name = data[fault]
        for case_id in ids:
            contract = contracts[case_id]
            output.append({'case_id': case_id, 'executed': True, 'status': 'Passed', 'source_sha': source,
                'setup': contract['setup_and_injection'], 'expected': contract['expected'],
                'profiles_executed': ['OFFLINE', 'POSTGRES'], 'scope': row['scope'],
                'actual': {'fault': fault, 'native_test': test_name, 'observed': row['actual'], 'native_receipt_sha256': digest},
                'trx_sha256': hashlib.sha256(trx.read_bytes()).hexdigest()})
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ['receipts', 'trx', 'proof', 'plan', 'output']:
        parser.add_argument('--' + name, type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError('Immutable output already exists')
    proof = json.loads(args.proof.read_text('utf-8'))
    rows = export(args.receipts, args.trx, proof, json.loads(args.plan.read_text('utf-8')))
    args.output.mkdir(parents=True)
    def write(name, value):
        (args.output/name).write_bytes((json.dumps(value, ensure_ascii=False, indent=2) + '\n').encode('utf-8'))
    (args.output/'cases.jsonl').write_bytes(''.join(json.dumps(r, ensure_ascii=False) + '\n' for r in rows).encode('utf-8'))
    write('report.json', {'source_sha': proof['source_sha'], 'executed': len(rows), 'passed': len(rows),
        'profiles_executed': ['OFFLINE', 'POSTGRES'], 'accepted': False,
        'scope': 'Actual native three-point PostgreSQL launch fault matrix; full Program/player LIVE and EXPERIMENT gates remain separate'})
    write('artifact-index.json', {'files': [{'name': p.name, 'bytes': p.stat().st_size, 'sha256': hashlib.sha256(p.read_bytes()).hexdigest()} for p in [args.receipts, args.trx, args.proof, args.plan]]})
    write('manifest.json', {'files': [{'path': p.name, 'bytes': p.stat().st_size, 'sha256': hashlib.sha256(p.read_bytes()).hexdigest()} for p in sorted(args.output.iterdir()) if p.is_file()]})
    print(json.dumps({'executed': len(rows), 'passed': len(rows), 'source_sha': proof['source_sha']}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
