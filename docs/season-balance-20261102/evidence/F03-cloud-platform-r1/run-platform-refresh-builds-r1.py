from pathlib import Path
import datetime, hashlib, importlib.util, json, os, subprocess

b = Path(__file__).parent; repo = Path.cwd(); out = b / 'f03-platform-refresh-r1'
rows = json.loads((out / 'integration-audit.original.json').read_bytes())
private = Path(r'G:\PR13Evidence\private\season-balance-20261102-f03-google-r1\platform-refresh-r1')
assert not private.exists(); private.mkdir()
flags = subprocess.CREATE_NO_WINDOW | subprocess.BELOW_NORMAL_PRIORITY_CLASS
sid = subprocess.check_output(['powershell', '-NoProfile', '-Command', '[System.Security.Principal.WindowsIdentity]::GetCurrent().User.Value'], creationflags=flags).decode().strip()
result = subprocess.run(['icacls', str(private), '/inheritance:r', '/grant:r', '*' + sid + ':(OI)(CI)F', '*S-1-5-18:(OI)(CI)F', '*S-1-5-32-544:(OI)(CI)F'], capture_output=True, creationflags=flags)
assert result.returncode == 0
(private / 'ownership.json').write_text(json.dumps(dict(task='season-balance-20261102', scope='private current candidate builds, never publish unprotected DLLs')) + '\n')
spec = importlib.util.spec_from_file_location('guard', repo / 'client/tests/fixture_runtime.py')
guard = importlib.util.module_from_spec(spec); spec.loader.exec_module(guard)
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
env = {key: value for key, value in os.environ.items() if not key.startswith('FANTASYCARD_')}
env.update(DOTNET_CLI_TELEMETRY_OPTOUT='1', DOTNET_NOLOGO='1', DOTNET_CLI_UI_LANGUAGE='en')
results = []
for row in rows:
    name = row['platform']; wt = Path(row['worktree']); directory = out / name; directory.mkdir()
    git = lambda args: subprocess.check_output(['git', '-C', str(wt), *args])
    assert not git(['status', '--porcelain']) and git(['rev-parse', 'HEAD']).decode().strip() == row['candidate']
    names = git(['ls-files', '-z', '--', 'server', 'protocol', 'config/FantasyCard_Config.xlsx']).decode().split('\0')
    pins = {p: sha(wt / p) for p in names if p and (wt / p).is_file() and not any(part in ['bin','obj','.packages','.artifacts'] for part in Path(p).parts)}
    (directory / 'source-pin.original.json').write_text(json.dumps(pins, indent=2) + '\n')
    artifacts = private / name / 'build'
    os.chdir(wt / 'server')
    print(json.dumps(dict(platform=name, stage='full Release solution', started=True)), flush=True)
    try:
        run = guard.guarded_run(['dotnet', 'build', str(wt / 'server/FantasyCard.Server.slnx'), '-c', 'Release', '--artifacts-path', str(artifacts), '-m:1', '-p:UseSharedCompilation=false', '--verbosity', 'minimal'], env=env, timeout=300, wait_seconds=30)
        text = run.stdout + run.stderr
        (directory / 'build.original.log').write_text(text, encoding='utf-8')
        passed = run.returncode == 0 and '0 Warning(s)' in text and '0 Error(s)' in text
        proof = dict(platform=name, head=row['candidate'], returncode=run.returncode, zero_warnings_errors=passed,
                     source_unchanged=all(sha(wt / p)==value for p,value in pins.items()), worktree_clean=not git(['status','--porcelain']),
                     artifact_root=str(artifacts), new_D03_F01_B05_attempts=0, native_clients_started=0)
    except BaseException as error:
        proof = dict(platform=name, head=row['candidate'], error=type(error).__name__, message=str(error), zero_warnings_errors=False)
    (directory / 'result.json').write_text(json.dumps(proof, indent=2) + '\n');results.append(proof)
    print(json.dumps(proof), flush=True)
    if not proof['zero_warnings_errors']: break
summary = dict(ok=len(results)==3 and all(r['zero_warnings_errors'] and r['source_unchanged'] and r['worktree_clean'] for r in results),
               results=results, formal_branches_updated=False, candidate_pushes_pending=True, production_changed=False,
               completed_at_utc=datetime.datetime.now(datetime.timezone.utc).isoformat())
(out / 'builds.result.json').write_text(json.dumps(summary, indent=2) + '\n')
print(json.dumps(dict(ok=summary['ok'], completed=len(results), production_changed=False)))
assert summary['ok']
