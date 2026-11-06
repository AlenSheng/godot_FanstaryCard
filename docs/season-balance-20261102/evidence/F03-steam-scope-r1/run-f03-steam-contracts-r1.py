from pathlib import Path
import json, os, importlib.util, subprocess
b = Path(__file__).parent
info = json.loads((b / 'f03-steam-integration-r1/source.original.json').read_bytes())
w = Path(info['worktree'])
out = b / 'f03-steam-contracts-r1'
assert not out.exists()
out.mkdir()
spec = importlib.util.spec_from_file_location('guard', w / 'client/tests/fixture_runtime.py')
guard = importlib.util.module_from_spec(spec)
spec.loader.exec_module(guard)
r = subprocess.run(['python', str(w / 'tools/generate_network_protocol.py'), '--check'], cwd=w,
                   capture_output=True, text=True, encoding='utf-8')
(out / 'protocol-check.original.log').write_text(r.stdout + r.stderr, encoding='utf-8')
assert r.returncode == 0
dll = b / 'f03-steam-integration-r1/build/bin/FantasyCard.Server.Tests/release/FantasyCard.Server.Tests.dll'
command = ['dotnet', 'vstest', str(dll),
    '--TestCaseFilter:FullyQualifiedName~SteamTicketVerifierTests|FullyQualifiedName~SteamDisplayNameGeneratorTests',
    '--Logger:trx;LogFileName=steam-contracts.trx', '--ResultsDirectory:' + str(out / 'results')]
result = guard.guarded_run(command, env=dict(os.environ, FANTASYCARD_TEST_POSTGRES='',
    DOTNET_CLI_TELEMETRY_OPTOUT='1', DOTNET_NOLOGO='1'), timeout=120, wait_seconds=30)
(out / 'server.original.log').write_text(result.stdout + result.stderr, encoding='utf-8')
(out / 'server-result.json').write_text(json.dumps({'exit': result.returncode, 'new_gameplay_cases': 0,
    'real_external_Steam_provider_used': False, 'production_changed': False}, indent=2) + '\n')
print((result.stdout + result.stderr)[-800:])
assert result.returncode == 0
assert json.loads((b / 'f03-steam-import-r1/result.json').read_bytes())['exit'] == 0
engine = r'G:\Program Files\Godot_v4.7.2-stable_win64.exe\Godot_v4.7.2-stable_win64.exe'
for scene, variable in [('steam_entry_contract', 'FANTASYCARD_STEAM_RESULT'), ('branch_sync_compatibility', 'FANTASYCARD_BRANCH_SYNC_RESULT')]:
    folder = out / scene
    folder.mkdir()
    env = guard.isolated_environment(folder, FANTASYCARD_SERVER_URL='http://127.0.0.1:9', **{variable: str(folder / 'native.original.json')})
    result = guard.guarded_run([engine, '--headless', '--path', str(w / 'client'), '--audio-driver', 'Dummy',
        'res://tests/' + scene + '.tscn'], env=env, timeout=120, wait_seconds=30)
    (folder / 'stdout.original.log').write_text(result.stdout, encoding='utf-8')
    (folder / 'stderr.original.log').write_text(result.stderr, encoding='utf-8')
    native = json.loads((folder / 'native.original.json').read_bytes())
    errors = [l for l in (result.stdout + result.stderr).splitlines() if 'ERROR:' in l]
    proof = {'exit': result.returncode, 'ok': native['ok'], 'checks': len(native['checks']),
             'failed': [k for k,v in native['checks'].items() if not v], 'errors': errors,
             'new_gameplay_cases': 0, 'real_external_Steam_provider_used': False}
    (folder / 'result.json').write_text(json.dumps(proof, indent=2) + '\n')
    print(json.dumps({'scene': scene, **proof}))
    assert result.returncode == 0 and native['ok'] and not errors
