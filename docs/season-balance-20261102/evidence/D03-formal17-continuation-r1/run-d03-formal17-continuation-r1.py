from pathlib import Path
import hashlib, importlib.util, json, os, sys, time, datetime

sys.stdout.reconfigure(encoding='utf-8')
b = Path(__file__).parent
repo = Path.cwd()
preflight = b / 'd03-formal17-continuation-preflight-r1'
info = json.loads((preflight / 'result.json').read_bytes())
assert info['exit'] == 0
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
pin = json.loads((preflight / 'source-pin.original.json').read_bytes())
assert all(sha(repo / p) == digest for p, digest in pin.items())
binary = Path(info['binary_directory_private_not_to_be_published'])
binaries = json.loads((preflight / 'binary-manifest.original.json').read_bytes())
assert all(sha(binary / p) == digest for p, digest in binaries.items())
plan = b / 'd03-formal17-continuation-roster-r1.original.json'
roster = json.loads(plan.read_bytes())
rows = roster['tracks']
planned = sum(row['steps'] for row in rows)
assert planned == 9 and roster['prior_used'] == 284
budget_path = repo / 'docs/season-balance-20261102/D03-BUDGET.json'
prior = budget_path.read_bytes()
budget = json.loads(prior)
assert budget['used'] == 284 and budget['current_handle'] is None and planned <= budget['remaining']
for item, used in [('B05', 330), ('C16', 298), ('D01', 297), ('D02', 112)]:
    assert json.loads((repo / 'docs/season-balance-20261102' / (item + '-BUDGET.json')).read_bytes())['used'] == used
for row in rows:
    assert sha(Path(row['source'])) == row['sha256']
out = b / 'd03-formal17-continuation-r1'
assert not out.exists()
out.mkdir()
(out / 'prior-budget.original.json').write_bytes(prior)
(out / 'roster.original.json').write_bytes(plan.read_bytes())
(out / 'binary-manifest.original.json').write_bytes((preflight / 'binary-manifest.original.json').read_bytes())
results = out / 'results'
results.mkdir()
observations = out / 'observations'
command = ['dotnet', str(binary / 'FantasyCard.Server.Tests.dll'), '-noLogo', '-noColor', '-noAutoReporters',
    '-failSkips', '-parallel', 'none', '-reporter', 'verbose', '-method',
    'FantasyCard.Server.Tests.Config.SeasonCohortTrajectoryTests.DeclaredTrajectoriesCarryOnlyRealItemsAndPayActualLobbyCosts',
    '-trx', str(results / 'cases.trx'), '-xml', str(results / 'cases.xml')]
started = {'parent_pid': os.getpid(), 'started_at_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
    'command': command, 'prior_used': 284, 'planned': planned, 'reserve_GiB': 2, 'startup_GiB': 1,
    'source_plan_sha256': sha(plan), 'test_timeout_seconds': 300}
(out / 'started.original.json').write_text(json.dumps(started, indent=2) + '\n')
budget_path.write_text(json.dumps({'item': 'D03', 'used': 284, 'remaining': 16, 'maximum': 300,
    'reserved_current': planned, 'current_handle': started}, indent=2) + '\n')
spec = importlib.util.spec_from_file_location('guard', repo / 'client/tests/fixture_runtime.py')
guard = importlib.util.module_from_spec(spec)
spec.loader.exec_module(guard)
env = dict(os.environ, DOTNET_CLI_UI_LANGUAGE='en', DOTNET_CLI_TELEMETRY_OPTOUT='1', DOTNET_NOLOGO='1',
    FANTASYCARD_RUN_D03_TRAJECTORIES='1', FANTASYCARD_D03_TRAJECTORY_PLAN=str(out / 'roster.original.json'),
    FANTASYCARD_D03_TRAJECTORY_OUTPUT=str(observations), FANTASYCARD_TEST_POSTGRES='')
for key in list(env):
    if key.startswith('FANTASYCARD_RUN_') and key != 'FANTASYCARD_RUN_D03_TRAJECTORIES': env[key] = ''
result = None
error = None
began = time.monotonic()
try:
    result = guard.guarded_run(command, env=env, timeout=300, wait_seconds=30)
    (out / 'run.original.log').write_text(result.stdout + result.stderr, encoding='utf-8')
except BaseException as exc:
    error = {'type': type(exc).__name__, 'error': str(exc), 'output': str(getattr(exc, 'output', ''))}
    (out / 'interrupted.original.json').write_text(json.dumps(error, indent=2) + '\n')
finally:
    attempts_path = observations / 'attempts.original.jsonl'
    attempts = [json.loads(x) for x in attempts_path.read_text(encoding='utf-8').splitlines()] if attempts_path.exists() else []
    assert len(attempts) <= planned
    used = 284 + len(attempts)
    proof = {'exit': result.returncode if result else None, 'error': error, 'actual_started': len(attempts), 'planned': planned,
        'total_D03_used': used, 'remaining': 300 - used, 'seconds': round(time.monotonic() - began, 2),
        'source_unchanged': all(sha(repo / p) == digest for p, digest in pin.items()),
        'binary_unchanged': all(sha(binary / p) == digest for p, digest in binaries.items()),
        'all_original_bank_sources_unchanged': all(sha(Path(row['source'])) == row['sha256'] for row in rows),
        'config_version': 'season-v1-config-17', 'new_B05': 0, 'new_C16': 0, 'new_D01': 0, 'new_D02': 0,
        'cloud_modified': False, 'production_modified': False}
    (out / 'result.json').write_text(json.dumps(proof, indent=2) + '\n')
    budget_path.write_text(json.dumps({'item': 'D03', 'used': used, 'remaining': 300 - used, 'maximum': 300,
        'current_handle': None, 'last_result': str(out / 'result.json'), 'prior_budget': str(out / 'prior-budget.original.json')}, indent=2) + '\n')
print(json.dumps(proof))
if result: print((result.stdout + result.stderr)[-900:])
assert result and result.returncode == 0 and len(attempts) == planned
assert proof['source_unchanged'] and proof['binary_unchanged'] and proof['all_original_bank_sources_unchanged']
