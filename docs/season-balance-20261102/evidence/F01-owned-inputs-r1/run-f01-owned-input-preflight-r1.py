from pathlib import Path
import json, hashlib, subprocess, importlib.util, os, datetime

b = Path(__file__).parent
repo = Path.cwd()
out = b / 'f01-owned-input-preflight-r1'
private = Path(r'G:\PR13Evidence\private\season-balance-20261102-f03-google-r1\f01-owned-input-build-r1')
assert not out.exists() and not private.exists()
assert not json.loads((b / 'current-journey-client-continuation-20261105.json').read_bytes())['pending_test_handles']
out.mkdir()
private.mkdir()
names = subprocess.check_output(['git', 'ls-files', '--cached', '--others', '--exclude-standard', '-z', '--',
    'server', 'protocol', 'config/FantasyCard_Config.xlsx', 'client/tests/fixture_runtime.py']).decode().split('\0')
pin = {name: hashlib.sha256((repo / name).read_bytes()).hexdigest() for name in names if name and (repo / name).is_file()}
(out / 'source-pin.original.json').write_text(json.dumps(pin, indent=2) + '\n')
command = ['dotnet', 'test', str(repo / 'server/tests/FantasyCard.Server.Tests/FantasyCard.Server.Tests.csproj'),
    '-c', 'Release', '--artifacts-path', str(private), '--filter', 'FullyQualifiedName~SeasonFirstFortnightInputsTests',
    '--logger', 'trx;LogFileName=f01-inputs.trx', '--results-directory', str(out / 'results'),
    '-m:1', '-p:UseSharedCompilation=false', '--verbosity', 'minimal']
env = dict(os.environ, DOTNET_CLI_UI_LANGUAGE='en', DOTNET_CLI_TELEMETRY_OPTOUT='1', DOTNET_NOLOGO='1',
    FANTASYCARD_RUN_F01_INPUTS='1', FANTASYCARD_F01_INPUT_OUTPUT=str(out / 'observations'), FANTASYCARD_TEST_POSTGRES='')
for key in list(env):
    if key.startswith('FANTASYCARD_RUN_') and key != 'FANTASYCARD_RUN_F01_INPUTS': env[key] = ''
spec = importlib.util.spec_from_file_location('guard', repo / 'client/tests/fixture_runtime.py')
guard = importlib.util.module_from_spec(spec)
spec.loader.exec_module(guard)
(out / 'started.original.json').write_text(json.dumps({'parent_pid': os.getpid(), 'at_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
    'command': command, 'reserve_GiB': 2, 'startup_GiB': 1, 'zero_gameplay_preflight_only': True}, indent=2) + '\n')
result = guard.guarded_run(command, env=env, timeout=240, wait_seconds=30)
(out / 'run.original.log').write_text(result.stdout + result.stderr, encoding='utf-8')
proof = {'exit': result.returncode, 'source_unchanged': all(hashlib.sha256((repo / name).read_bytes()).hexdigest() == digest for name, digest in pin.items()),
    'current_source_entries': len(pin), 'new_gameplay_cases': 0, 'B05_used': 330, 'D03_used': 293,
    'F01_252_started': False, 'production_changed': False, 'private_build': str(private)}
(out / 'result.json').write_text(json.dumps(proof, indent=2) + '\n')
print((result.stdout + result.stderr)[-2100:])
print(json.dumps(proof))
assert result.returncode == 0 and proof['source_unchanged']
