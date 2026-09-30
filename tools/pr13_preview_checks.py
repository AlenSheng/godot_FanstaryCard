"""Verify local Godot previews against 1800 actual authoritative preview/play pairs."""
import argparse
import hashlib
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
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ, FANTASYCARD_SERVER_URL='http://127.0.0.1:1',
               FANTASYCARD_PREVIEW_VECTORS=str(output/'input.json'),
               FANTASYCARD_PREVIEW_RESULT=str(output/'results.json'))
    commands = [
        ('server', ['dotnet', 'run', '--project', str(ROOT/'server/tools/FantasyCard.Numerics'),
                    '-c', 'Release', '--', '--preview-vectors', '--output', str(output/'input.json')], 300),
        ('client', [args.godot, '--headless', '--path', str(ROOT/'client'),
                    '--script', 'res://tests/run_preview_vectors.gd'], 90)]
    gates = []
    for name, command, timeout in commands:
        start = time.time()
        try:
            run = subprocess.run(command, cwd=ROOT, env=env, capture_output=True, text=True,
                encoding='utf8', errors='replace', timeout=timeout,
                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            log = run.stdout + run.stderr
            ok = run.returncode == 0 and not any(e in log for e in ('SCRIPT ERROR', 'Parse Error', 'Failed to load script'))
            code = run.returncode
        except subprocess.TimeoutExpired as error:
            log = ''.join(v.decode('utf8','replace') if isinstance(v,bytes) else v or '' for v in (error.stdout,error.stderr))+'\nTIMEOUT\n'
            code, ok = None, False
        (output/(name+'.log')).write_text(log, encoding='utf8')
        gates.append(dict(name=name, command=command, exit_code=code, ok=ok, elapsed=time.time()-start))
        print(log, flush=True)
        if not ok: break
    verdict = len(gates) == 2 and all(g['ok'] for g in gates)
    result = json.loads((output/'results.json').read_text(encoding='utf8')) if verdict else {}
    verdict = verdict and result.get('ok') is True and result.get('vectors',0) >= 1000
    source = subprocess.run(['git','rev-parse','HEAD'],cwd=ROOT,capture_output=True,text=True,check=True).stdout.strip()
    manifest = dict(ok=verdict, source_commit=source, source_tree_dirty=subprocess.run(['git','diff','--quiet'],cwd=ROOT).returncode != 0,
        gates=gates, vector_count=result.get('vectors'), failure_count=len(result.get('failures',[])),
        input_sha256=hashlib.sha256((output/'input.json').read_bytes()).hexdigest() if (output/'input.json').exists() else None,
        domain_assembly_sha256=hashlib.sha256((ROOT/'server/tools/FantasyCard.Numerics/bin/Release/net10.0/FantasyCard.Domain.dll').read_bytes()).hexdigest(),
        simulator_assembly_sha256=hashlib.sha256((ROOT/'server/tools/FantasyCard.Numerics/bin/Release/net10.0/FantasyCard.Numerics.dll').read_bytes()).hexdigest())
    (output/'manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf8')
    print(json.dumps(dict(ok=verdict, vectors=result.get('vectors'), failures=len(result.get('failures',[])))),flush=True)
    return 0 if verdict else 1


if __name__ == '__main__': raise SystemExit(main())
