"""Capture complete private evidence before deleting an owned cloud fixture."""
import argparse
import json
from pathlib import Path
import sys

if __package__:
    from . import isolated_runtime
    from ...pr13_financial_snapshot import from_psql, query
else:
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
    from tools.cloud.pr13 import isolated_runtime
    from tools.pr13_financial_snapshot import from_psql, query


def capture(record, destination, phase):
    destination = Path(destination).resolve()
    root = (isolated_runtime.BASE / 'live-evidence').resolve()
    if not destination.is_relative_to(root) or destination.exists():
        raise ValueError('New private output inside owned runtime evidence required')
    isolated_runtime.owned(record, 'postgres')
    process = isolated_runtime.docker(
        'exec', record['containers']['postgres'], 'psql', '-X', '-U', 'fantasycard',
        '-d', record['database_name'], '-At', '-v', 'ON_ERROR_STOP=1', '-c', query())
    snapshot = from_psql(process.stdout, scope=record['database_name'], phase=phase)
    snapshot['execution_host'] = 'Tencent cloud'
    isolated_runtime.save(destination, snapshot)
    return snapshot


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime-record', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--phase', choices=['before', 'after'], required=True)
    args = parser.parse_args()
    snapshot = capture(json.loads(args.runtime_record.read_text('utf-8')), args.output, args.phase)
    print(json.dumps({'phase': args.phase, 'ledger_rows': snapshot['validation']['ledger_rows'],
                      'chain_mismatches': snapshot['validation']['verified_chain_mismatches'],
                      'read_only': True, 'financial_acceptance': False}))


if __name__ == '__main__':
    main()
