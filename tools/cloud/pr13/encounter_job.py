"""Run an owned native job in temporary memory and retain lossless raw evidence."""
import argparse
import gzip
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--scratch', type=Path, required=True)
    parser.add_argument('--source-sha', required=True)
    parser.add_argument('--weapon-level', type=int, required=True)
    parser.add_argument('--seed-start', type=int, required=True)
    parser.add_argument('--timeout', type=int, default=400)
    args = parser.parse_args()
    if args.output.exists() or args.scratch.exists(): raise ValueError('Immutable owned job paths already exist')
    args.output.mkdir(parents=True); args.scratch.mkdir(parents=True)
    command = ['dotnet', str(args.runtime), '--combat-experience', '--candidate', 'class-passives', '--heroes', 'Guardian',
               '--weapon-level', str(args.weapon_level), '--samples', '1000', '--seed-start', str(args.seed_start),
               '--source-sha', args.source_sha, '--cutoff-seconds', '600', '--output', str(args.scratch)]
    started = time.monotonic(); result = {'ok': False, 'command': command, 'source_sha': args.source_sha}
    with (args.output / 'native.log').open('wb') as log:
        process = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
        try: result['exit_code'] = process.wait(timeout=args.timeout)
        except subprocess.TimeoutExpired:
            result['timeout'] = True
            os.killpg(process.pid, signal.SIGTERM)
            try: process.wait(timeout=5)
            except subprocess.TimeoutExpired: os.killpg(process.pid, signal.SIGKILL); process.wait(timeout=5)
            result['exit_code'] = process.returncode
    try:
        sys.path.insert(0, '/work/tools')
        from pr13_raw_storage import compress_raw, raw_input
        if result['exit_code'] != 0: raise ValueError('Actual native job did not complete')
        manifest = json.loads((args.scratch / 'manifest.json').read_text())
        summary = json.loads((args.scratch / 'summary.json').read_text())
        if (manifest['SourceSha'] != args.source_sha or manifest['SamplesPerStratum'] != 1000
                or manifest['WeaponLevel'] != args.weapon_level or manifest['SeedStart'] != args.seed_start
                or summary['ErrorCount'] != 0 or summary['CandidateActivation'] is not False):
            raise ValueError('Actual native frozen job differs or has errors')
        storage = compress_raw(args.scratch)
        for path in args.scratch.iterdir():
            if not path.is_file(): raise ValueError('Unexpected native nested artifact')
            target = args.output / path.name
            with path.open('rb') as source, target.open('xb') as output:
                for block in iter(lambda: source.read(4 * 1024 * 1024), b''): output.write(block)
        raw_input(args.output, json.loads((args.output / 'summary.json').read_text()))
        result.update(ok=True, raw_storage=storage, native_rows=summary['Total'], error_count=summary['ErrorCount'])
    except Exception as error:
        result.update(error=type(error).__name__, detail=str(error))
        # A failed or timed-out native process may have emitted partial rows.
        # Preserve them explicitly, without inventing a completed summary.
        raw = args.scratch / 'encounters.jsonl'
        if raw.is_file():
            with raw.open('rb') as source, gzip.open(args.output / 'partial-encounters.jsonl.gz', 'wb', compresslevel=1) as output:
                for block in iter(lambda: source.read(4 * 1024 * 1024), b''): output.write(block)
        for name in ['manifest.json', 'summary.json']:
            path = args.scratch / name
            if path.is_file() and not (args.output / name).exists(): (args.output / name).write_bytes(path.read_bytes())
    result['elapsed_seconds'] = time.monotonic() - started
    (args.output / 'job-result.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result)); return 0 if result['ok'] else 1


if __name__ == '__main__': raise SystemExit(main())
