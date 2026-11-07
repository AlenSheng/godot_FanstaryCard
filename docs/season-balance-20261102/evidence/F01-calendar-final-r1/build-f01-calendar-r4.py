from pathlib import Path
import json, hashlib, importlib.util, os, subprocess, datetime

b = Path(__file__).parent
repo = Path.cwd()
out = b / 'f01-calendar-build-r4'
private = Path(r'G:\PR13Evidence\private\season-balance-20261102-f03-google-r1\f01-calendar-build-r4')
assert not out.exists() and not private.exists()
out.mkdir()
private.mkdir()
names = subprocess.check_output(['git', 'ls-files', '--cached', '--others', '--exclude-standard', '-z', '--',
    'server', 'protocol', 'config/FantasyCard_Config.xlsx', 'client/tests/fixture_runtime.py']).decode().split('\0')
pin = {name: hashlib.sha256((repo / name).read_bytes()).hexdigest() for name in names if name and (repo / name).is_file()}
(out / 'source-pin.original.json').write_text(json.dumps(pin, indent=2) + '\n')
command = ['dotnet', 'build', str(repo / 'server/tests/FantasyCard.Server.Tests/FantasyCard.Server.Tests.csproj'),
    '-c', 'Release', '--artifacts-path', str(private), '-m:1', '-p:UseSharedCompilation=false', '--verbosity', 'minimal']
(out / 'started.original.json').write_text(json.dumps({'parent_pid': os.getpid(), 'at_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
    'command': command, 'reserve_GiB': 2, 'startup_GiB': 1, 'new_gameplay_cases': 0}, indent=2) + '\n')
spec = importlib.util.spec_from_file_location('guard', repo / 'client/tests/fixture_runtime.py')
guard = importlib.util.module_from_spec(spec)
spec.loader.exec_module(guard)
result = guard.guarded_run(command, env=dict(os.environ, DOTNET_CLI_UI_LANGUAGE='en', DOTNET_CLI_TELEMETRY_OPTOUT='1', DOTNET_NOLOGO='1'), timeout=240, wait_seconds=30)
(out / 'build.original.log').write_text(result.stdout + result.stderr, encoding='utf-8')
proof = {'exit': result.returncode, 'source_unchanged': all(hashlib.sha256((repo / name).read_bytes()).hexdigest() == digest for name, digest in pin.items()),
    'source_entries': len(pin), 'private_build': str(private), 'new_gameplay_cases': 0, 'production_changed': False}
(out / 'result.json').write_text(json.dumps(proof, indent=2) + '\n')
print((result.stdout + result.stderr)[-1800:])
print(json.dumps(proof))
assert result.returncode == 0 and proof['source_unchanged']
