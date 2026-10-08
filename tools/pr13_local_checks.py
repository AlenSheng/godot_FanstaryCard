"""Bounded, offline Godot gates with retained logs and explicit failure status."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import time

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--godot', required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--import-project', action='store_true')
    parser.add_argument('--only', choices=('load-parse','client-regression','lobby-race','numerical','localization'))
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    gates = []
    if args.import_project:
        gates.append(('import', ['--editor', '--import', '--quit'], 600, None))
    gates.extend([
        ('load-parse', ['--script', 'res://tests/run_gameplay_load_parse.gd'], 30, 'Gameplay load client parses'),
        ('client-regression', ['--script', 'res://tests/run_play_retry.gd'], 90, 'test_client_hot_paths'),
        ('lobby-race', ['--script', 'res://tests/run_lobby_race.gd'], 30, '"ok":true'),
        ('numerical', ['res://tests/numerical_integration.tscn'], 60, '"ok":true'),
        ('localization', ['--script', 'res://tests/run_localization.gd'], 90, '"ok":true'),
    ])
    if args.only: gates = [gate for gate in gates if gate[0] == args.only]
    env = dict(os.environ, FANTASYCARD_SERVER_URL='http://127.0.0.1:1')
    results = []
    for name, arguments, timeout, marker in gates:
        command = [args.godot, '--headless', '--path', str(ROOT/'client')] + arguments
        start = time.time()
        try:
            run = subprocess.run(command, env=env, capture_output=True, text=True,
                encoding='utf-8', errors='replace', timeout=timeout,
                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            log = run.stdout + run.stderr
            ok = run.returncode == 0 and not any(error in log for error in ('SCRIPT ERROR', 'Parse Error', 'Failed to load script'))
            if marker is not None: ok = ok and marker in log
            code = run.returncode
        except subprocess.TimeoutExpired as error:
            log = ''.join(value.decode('utf8', 'replace') if isinstance(value, bytes) else value or ''
                          for value in (error.stdout, error.stderr)) + '\nGATE TIMEOUT\n'
            code, ok = None, False
        (output/(name+'.log')).write_text(log, encoding='utf8')
        result = dict(name=name, command=command, started=start, elapsed=time.time()-start, exit_code=code, ok=ok)
        results.append(result)
        print(json.dumps(result), flush=True)
    (output/'results.json').write_text(json.dumps(dict(ok=all(row['ok'] for row in results), gates=results), indent=2), encoding='utf8')
    return 0 if all(row['ok'] for row in results) else 1


if __name__ == '__main__': raise SystemExit(main())
