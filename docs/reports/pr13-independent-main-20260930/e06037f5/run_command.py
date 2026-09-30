"""Independent review command recorder; never modifies loaded source."""
import argparse, datetime, hashlib, json, os, pathlib, platform, subprocess, sys, time
p = argparse.ArgumentParser()
p.add_argument('--id', required=True)
p.add_argument('--cwd', required=True)
p.add_argument('argv', nargs=argparse.REMAINDER)
a = p.parse_args()
argv = a.argv[1:] if a.argv[:1] == ['--'] else a.argv
root = pathlib.Path(__file__).resolve().parent
log = root / (a.id + '.log')
env = dict(os.environ, PYTHONDONTWRITEBYTECODE='1', PR13_SOURCE_ROOT=a.cwd)
started = datetime.datetime.now(datetime.timezone.utc).isoformat()
t = time.monotonic()
sha = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=a.cwd, text=True).strip()
with log.open('w') as f:
    result = subprocess.run(argv, cwd=a.cwd, env=env, stdout=f, stderr=subprocess.STDOUT, timeout=120)
record = dict(id=a.id, argv=argv, cwd=a.cwd, source_sha=sha,
              environment={k:env[k] for k in ('PYTHONDONTWRITEBYTECODE','PR13_SOURCE_ROOT')},
              started_at_utc=started, elapsed_seconds=time.monotonic()-t, exit_code=result.returncode,
              python=sys.version, executable=sys.executable, platform=platform.platform(),
              log=log.name, log_sha256=hashlib.sha256(log.read_bytes()).hexdigest())
(root/(a.id+'.command.json')).write_text(json.dumps(record, indent=2))
print(json.dumps(record))
print(log.read_text()[-2500:])
raise SystemExit(result.returncode)
