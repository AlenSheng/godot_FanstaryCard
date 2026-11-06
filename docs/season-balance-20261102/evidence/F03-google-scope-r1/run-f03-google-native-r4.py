from pathlib import Path
import json, importlib.util, datetime

b = Path(__file__).parent
info = json.loads((b / 'f03-google-integration-r1/source.original.json').read_bytes())
work = Path(info['worktree'])
out = b / 'f03-google-native-r4'
assert not out.exists()
out.mkdir()
spec = importlib.util.spec_from_file_location('guard', work / 'client/tests/fixture_runtime.py')
guard = importlib.util.module_from_spec(spec)
spec.loader.exec_module(guard)
env = guard.isolated_environment(out, FANTASYCARD_SERVER_URL='http://127.0.0.1:9',
                                 FANTASYCARD_BRANCH_SYNC_RESULT=str(out / 'native.original.json'))
command = [r'G:\Program Files\Godot_v4.7.2-stable_win64.exe\Godot_v4.7.2-stable_win64.exe',
           '--headless', '--verbose', '--path', str(work / 'client'), '--audio-driver', 'Dummy',
           'res://tests/branch_sync_compatibility.tscn']
(out / 'started.original.json').write_text(json.dumps({'at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
    'command': command, 'source_candidate': info['detached_validation_commit'], 'reserve_GiB': 2,
    'startup_GiB': 1, 'three_sample_admission_GiB': 3, 'no_window': True, 'new_gameplay_cases': 0}, indent=2) + '\n')
try:
    result = guard.guarded_run(command, env=env, timeout=120, wait_seconds=30)
    (out / 'stdout.original.log').write_text(result.stdout, encoding='utf-8')
    (out / 'stderr.original.log').write_text(result.stderr, encoding='utf-8')
    proof = json.loads((out / 'native.original.json').read_bytes())
    errors = [line for line in (result.stdout + result.stderr).splitlines() if 'ERROR:' in line]
    summary = {'exit': result.returncode, 'ok': proof['ok'], 'checks': len(proof['checks']),
               'failed': [k for k, v in proof['checks'].items() if not v], 'errors': errors,
               'source_candidate': info['detached_validation_commit'], 'new_gameplay_cases': 0,
               'real_external_Google_provider_used': False, 'production_changed': False}
    (out / 'result.json').write_text(json.dumps(summary, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(summary))
    assert result.returncode == 0 and proof['ok'] and not errors
except BaseException as exc:
    (out / 'exception.original.json').write_text(json.dumps({'type': type(exc).__name__, 'message': str(exc)}) + '\n')
    raise
