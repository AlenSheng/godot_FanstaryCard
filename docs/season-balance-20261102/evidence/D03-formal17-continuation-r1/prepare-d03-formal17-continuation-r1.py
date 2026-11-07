from pathlib import Path
import json, hashlib, datetime, subprocess, importlib.util, os

b = Path(__file__).parent
repo = Path.cwd()
out = b / 'd03-formal17-continuation-preflight-r1'
assert not out.exists()
out.mkdir()
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
pin_path = b / 'f03-protected-build-r2/source-pin.json'
pin = json.loads(pin_path.read_bytes())
assert all(sha(repo / p) == digest for p, digest in pin.items())
continuation = json.loads((b / 'current-journey-client-continuation-20261105.json').read_bytes())
budget = json.loads((repo / 'docs/season-balance-20261102/D03-BUDGET.json').read_bytes())
assert budget['used'] == 284 and budget['remaining'] == 16 and budget['current_handle'] is None
assert not continuation['pending_test_handles']
rows = []
for index, entry in enumerate(continuation['D03_latest_banks'], 1):
    source = Path(entry['source'])
    assert sha(source) == entry['sha256']
    bank = json.loads(source.read_bytes())
    assert bank['StopReason'] is None and bank['SelectionPolicy'] == 'effect-aware-maintenance-v1'
    rows.append({'id': bank['Id'], 'source': str(source), 'sha256': sha(source), 'source_case': bank['Id'],
        'next_seed': 3200001 + index * 100, 'steps': 1, 'checkpoint': 'post-maintenance-original-capital',
        'loadout': 'support-guard' if bank['Cohort'] == 'novice' else 'current'})
roster = {'at_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(), 'prior_used': 284,
    'config_version': 'season-v1-config-17', 'tracks': rows,
    'policy': {'name': 'effect-aware-maintenance-v1', 'maximum_new': 9,
        'reason': 'Current formal17 continuation of all nine existing real-capital model banks after Mage card/policy update.',
        'capital': 'Exact original banks, no gifts, resets, new initial kit, development income or fabricated calendar.',
        'limits': 'Same cohort risk/loot/reaction/route and original warehouse model; no claim of paired class-efficiency from unequal banks.',
        'remaining_7': 'Reserved for evidence-based follow-up; no automatic exhaustion or retries.'}}
plan = b / 'd03-formal17-continuation-roster-r1.original.json'
assert not plan.exists()
plan.write_text(json.dumps(roster, indent=2) + '\n')
(out / 'source-pin.original.json').write_bytes(pin_path.read_bytes())
(out / 'roster.original.json').write_bytes(plan.read_bytes())
binary = Path(r'G:\PR13Evidence\private\season-balance-20261102-f03-protected-r2\build\bin\FantasyCard.Server.Tests\release')
build = json.loads((b / 'f03-protected-build-r2/result.json').read_bytes())
for name in ['FantasyCard.Contracts.dll', 'FantasyCard.Domain.dll', 'FantasyCard.Server.dll']:
    assert sha(binary / name) == build['assemblies'][name]['original_sha256']
manifest = {p.relative_to(binary).as_posix(): sha(p) for p in binary.rglob('*') if p.is_file()}
(out / 'binary-manifest.original.json').write_text(json.dumps(manifest, indent=2) + '\n')
spec = importlib.util.spec_from_file_location('guard', repo / 'client/tests/fixture_runtime.py')
guard = importlib.util.module_from_spec(spec)
spec.loader.exec_module(guard)
command = ['dotnet', str(binary / 'FantasyCard.Server.Tests.dll'), '-noLogo', '-noColor', '-noAutoReporters',
    '-failSkips', '-parallel', 'none', '-reporter', 'verbose', '-method',
    'FantasyCard.Server.Tests.Config.SeasonCohortTrajectoryTests.ObservedBanksPreserveLossesAndDoNotRecreateStartingGear',
    '-trx', str(out / 'preflight.trx'), '-xml', str(out / 'preflight.xml')]
env = dict(os.environ, DOTNET_CLI_UI_LANGUAGE='en', DOTNET_CLI_TELEMETRY_OPTOUT='1', DOTNET_NOLOGO='1',
    FANTASYCARD_RUN_D03_TRAJECTORIES='1', FANTASYCARD_D03_TRAJECTORY_PLAN=str(plan),
    FANTASYCARD_D03_TRAJECTORY_PREFLIGHT_OUTPUT=str(out / 'bank-legality.original.json'), FANTASYCARD_TEST_POSTGRES='')
for key in list(env):
    if key.startswith('FANTASYCARD_RUN_') and key != 'FANTASYCARD_RUN_D03_TRAJECTORIES': env[key] = ''
result = guard.guarded_run(command, env=env, timeout=180, wait_seconds=30)
(out / 'preflight.original.log').write_text(result.stdout + result.stderr, encoding='utf-8')
proof = {'exit': result.returncode, 'new_gameplay_cases': 0, 'source_commit': subprocess.check_output(['git', 'rev-parse', 'HEAD']).decode().strip(),
    'common_original_assemblies_exact': True, 'source_pin_entries': len(pin),
    'source_unchanged': all(sha(repo / p) == digest for p, digest in pin.items()), 'roster_tracks': 9,
    'planned_next_attempts': 9, 'binary_directory_private_not_to_be_published': str(binary), 'production_changed': False}
(out / 'result.json').write_text(json.dumps(proof, indent=2) + '\n')
print((result.stdout + result.stderr)[-1000:])
print(json.dumps(proof))
assert result.returncode == 0 and proof['source_unchanged']
