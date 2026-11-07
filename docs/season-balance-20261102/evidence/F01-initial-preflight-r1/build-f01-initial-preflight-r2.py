from pathlib import Path
import importlib.util, json, os, hashlib
b = Path(__file__).parent
source = b / 'f01-initial-preflight-source-r1'
out = b / 'f01-initial-preflight-build-r2'
private = Path(r'G:\PR13Evidence\private\season-balance-20261102-f03-google-r1\f01-preflight-build-r2')
assert not out.exists() and not private.exists()
out.mkdir()
private.mkdir()
pin = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in source.iterdir() if p.is_file()}
(out / 'source-pin.original.json').write_text(json.dumps(pin, indent=2) + '\n')
spec = importlib.util.spec_from_file_location('guard', Path.cwd() / 'client/tests/fixture_runtime.py')
guard = importlib.util.module_from_spec(spec)
spec.loader.exec_module(guard)
command = ['dotnet', 'build', str(source / 'F01InitialPreflight.csproj'), '-c', 'Release', '-o', str(private),
           '-m:1', '-p:UseSharedCompilation=false', '--verbosity', 'minimal']
result = guard.guarded_run(command, env=dict(os.environ, DOTNET_CLI_TELEMETRY_OPTOUT='1',
    DOTNET_NOLOGO='1', DOTNET_CLI_UI_LANGUAGE='en'), timeout=180, wait_seconds=30)
(out / 'build.original.log').write_text(result.stdout + result.stderr, encoding='utf-8')
proof = {'exit': result.returncode, 'private_binary_directory': str(private), 'new_gameplay_cases': 0,
    'source_unchanged': all(hashlib.sha256((source / name).read_bytes()).hexdigest() == digest for name, digest in pin.items()),
    'production_changed': False}
(out / 'result.json').write_text(json.dumps(proof, indent=2) + '\n')
print((result.stdout + result.stderr)[-1800:])
print(json.dumps(proof))
assert result.returncode == 0 and proof['source_unchanged']
