"""Read-only, deterministic PR13 raw-file validation and three-cutoff replay."""
import argparse
import hashlib
import json
from pathlib import Path

try:
    from pr13_runtime_evidence import reconcile_cycles, finite
    from cloud_load_test import aggregate_recent
except ModuleNotFoundError:
    from tools.pr13_runtime_evidence import reconcile_cycles, finite
    from tools.cloud_load_test import aggregate_recent

ALGORITHM = 'pr13-audit-replay-v1'
REDLINES = {'http_p95_ms': 1500, 'command_p95_ms': 2000, 'cpu_percent': 85,
            'memory_available_percent': 15, 'disk_available_percent': 15, 'actor_wait_p95_ms': 100,
            'consecutive_windows': 3}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def check_files(root, manifest):
    """Classify each declared source; never repair, rename or overwrite raw."""
    records = manifest.get('files') if isinstance(manifest, dict) else None
    if not isinstance(records, list) or not 1 <= len(records) <= 1000:
        raise ValueError('Nonempty source-file manifest required')
    result = []
    seen = set()
    total_bytes = 0
    for item in records:
        name = item.get('path') if isinstance(item, dict) else None
        if not isinstance(name, str) or not name or name in seen:
            raise ValueError('Invalid or duplicate source path')
        seen.add(name)
        path = (root / name).resolve()
        if not path.is_relative_to(root.resolve()):
            raise ValueError('Source path escapes the authorized run')
        size, expected = item.get('bytes'), item.get('sha256')
        if type(size) is not int or size < 0 or not isinstance(expected, str) or len(expected) != 64:
            raise ValueError('Exact source byte count and SHA-256 required')
        if not path.is_file():
            result.append(dict(path=name, state='Missing', bytes=None, sha256=None)); continue
        actual_size = path.stat().st_size
        total_bytes += actual_size
        if total_bytes > 256 * 1024 ** 2:
            raise ValueError('Source file exceeds bounded audit size')
        digest = sha(path)
        result.append(dict(path=name, state='Matching' if actual_size == size and digest == expected
                           else 'HashMismatchQuarantined', bytes=actual_size, sha256=digest))
    return result


def replay(root, manifest, *, stop_ms, final_ms, checks=None, claimed_totals=None,
           algorithm='current', max_events=1000000):
    if any(not finite(v) or v < 0 for v in (stop_ms, final_ms)) or final_ms < stop_ms:
        raise ValueError('Finite ordered cutoff times required')
    if algorithm not in ('current', 'legacy-accounting'): raise ValueError('Unknown replay algorithm')
    if type(max_events) is not int or not 1 <= max_events <= 1000000: raise ValueError('Bounded event count required')
    validation = check_files(root, manifest)
    if any(row['state'] != 'Matching' for row in validation):
        return dict(algorithm=ALGORITHM, status='Blocked', raw_read=False, files=validation,
                    derived=None, reason='Missing or mismatched original source; no counts reconstructed.')
    events = []
    raw_errors = []
    for row in validation:
        if not row['path'].endswith('.jsonl'): continue
        with (root / row['path']).open(encoding='utf8') as stream:
            for number, line in enumerate(stream, 1):
                if len(line) > 65536: raise ValueError('Audit line exceeds bounded size')
                if len(events) >= max_events: raise ValueError('Audit event budget exceeded')
                try: events.append(json.loads(line))
                except ValueError:
                    events.append(None)
                    raw_errors.append(dict(path=row['path'], line=number, error='InvalidJson'))
    derived = reconcile_cycles(events, stop_ms, final_ms)
    legacy = None
    if algorithm == 'legacy-accounting':
        status = {'operations': [e for e in events if isinstance(e, dict) and e.get('type') == 'http'],
                  'telemetry': [e for e in events if isinstance(e, dict) and e.get('type') in ('realtime', 'rtt')]}
        legacy = aggregate_recent([status], int(final_ms) + 1, now_ms=int(final_ms))
    errors = list(derived['evidence_errors'])
    if claimed_totals is not None:
        for cutoff, fields in claimed_totals.items():
            if cutoff not in ('running', 'drain', 'final') or not isinstance(fields, dict):
                raise ValueError('Declared comparison must use the same explicit cutoff')
            for field, value in fields.items():
                if field not in ('acknowledgements', 'completed_cycles'): raise ValueError('Unknown comparison metric')
                if type(value) is not int or value < 0: raise ValueError('Nonnegative declared count required')
                if value != derived[cutoff][field]: errors.append('same_cutoff_claim_conflict:' + cutoff + ':' + field)
    failed_checks = []
    for row in checks or []:
        if not isinstance(row, dict) or not isinstance(row.get('client_id'), str) or not row['client_id'] or type(row.get('passed')) is not bool:
            raise ValueError('Invalid check denominator schema')
        if not row['passed']: failed_checks.append(row)
    unique = {}
    for event in events:
        if not isinstance(event, dict): continue
        identity = tuple(event.get(key) for key in ('run_id', 'client_id', 'process_epoch', 'event_seq'))
        if any(type(v) is not str or not v for v in identity[:3]) or type(identity[3]) is not int: continue
        unique.setdefault(identity, event)
    differences = [dict(client_id=e.get('client_id'), cycle_id=e.get('cycle_id'), event_seq=e.get('event_seq'),
                        event_type=e.get('event_type'), at_unix_ms=e.get('at_unix_ms'),
                        cutoff='drain' if e.get('at_unix_ms', final_ms + 1) > stop_ms else 'running')
                   for e in unique.values() if e.get('event_type') in ('settlement.acknowledged', 'cycle.completed')
                   and type(e.get('at_unix_ms')) in (int, float) and 0 <= e['at_unix_ms'] <= final_ms]
    # Stable derivation contains no current clock, output path or mutable HEAD.
    return dict(algorithm=ALGORITHM if algorithm == 'current' else 'legacy-accounting-explicit-cutoffs-v1',
                status='InvalidEvidence' if errors or raw_errors else 'Derived', raw_read=True, files=validation,
                raw_errors=raw_errors,
                derived=derived, evidence_errors=sorted(set(errors)), event_differences=differences,
                check_denominators={'failed_clients': len({r['client_id'] for r in failed_checks}),
                                    'failed_checks': len(failed_checks)},
                legacy_redlines=REDLINES if algorithm == 'legacy-accounting' else None,
                legacy_request_statistics=legacy,
                current_acceptance=False, historical_recovery=False)


def validate_derived(candidate, expected):
    if candidate != expected:
        raise ValueError('Derived report differs from the same raw and algorithm; do not edit one total independently')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, required=True)
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--stop-ms', type=int, required=True)
    parser.add_argument('--final-ms', type=int, required=True)
    parser.add_argument('--algorithm', choices=('current', 'legacy-accounting'), default='current')
    args = parser.parse_args()
    if args.output.exists(): raise ValueError('Refusing to overwrite an archived derivation')
    result = replay(args.input.resolve(), json.loads(args.manifest.read_text(encoding='utf8')),
                    stop_ms=args.stop_ms, final_ms=args.final_ms, algorithm=args.algorithm)
    args.output.mkdir(parents=True)
    data = (json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + '\n').encode()
    (args.output / 'derived.json').write_bytes(data)
    print(json.dumps({'status': result['status'], 'output': str(args.output)}))
    return 0 if result['status'] == 'Derived' else 3


if __name__ == '__main__': raise SystemExit(main())
