from pathlib import Path
import subprocess, json, importlib.util, os, datetime, ctypes, time
b = Path(__file__).parent
out = b / 'f03-steam-local-pg-r2'
private = Path(r'G:\PR13Evidence\private\season-balance-20261102-f03-google-r1')
data = private / 'pgdata'
pg = Path(r'G:\Program Files\GodotFiles\godot_FanstaryCard\tools\engine-local\protected\postgres\pgsql\bin')
info = json.loads((b / 'f03-steam-integration-r1/source.original.json').read_bytes())
work = Path(info['worktree'])
assert not out.exists() and not (data / 'postmaster.pid').exists()
assert data.resolve() == Path(r'G:\PR13Evidence\private\season-balance-20261102-f03-google-r1\pgdata')
assert (data / 'PG_VERSION').read_text().strip() == '18'
assert json.loads((b / 'f03-steam-ui-r3/terminal.original.json').read_bytes())['native_exit'] == 0
out.mkdir()
spec = importlib.util.spec_from_file_location('guard', work / 'client/tests/fixture_runtime.py')
guard = importlib.util.module_from_spec(spec)
spec.loader.exec_module(guard)
flags = subprocess.CREATE_NO_WINDOW | subprocess.BELOW_NORMAL_PRIORITY_CLASS
env = dict(os.environ, DOTNET_CLI_TELEMETRY_OPTOUT='1', DOTNET_NOLOGO='1', DOTNET_CLI_UI_LANGUAGE='en')
test = None
started = False
try:
    class MemoryStatus(ctypes.Structure):
        _fields_ = [("length", ctypes.c_ulong), ("load", ctypes.c_ulong)] + [(n, ctypes.c_ulonglong) for n in ("total", "available", "total_page", "available_page", "total_virtual", "available_virtual", "extended")]
    def available():
        status = MemoryStatus(); status.length = ctypes.sizeof(status)
        assert ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status))
        return status.available
    samples = []
    for _ in range(3):
        samples.append(available()); time.sleep(1)
    (out / 'startup-admission.original.json').write_text(json.dumps({'available_bytes': samples, 'reserve_GiB': 2, 'startup_GiB': 1}) + '\n')
    assert min(samples) >= 3 * 1024**3
    with (private / 'steam-start-r2.private.log').open('wb') as log:
        child = subprocess.Popen([str(pg / 'pg_ctl.exe'), '-D', str(data), '-l', str(private / 'steam-pg-r2.private.log'),
            '-o', '-h 127.0.0.1 -p 8295 -c shared_buffers=64MB -c max_connections=20', '-w', 'start'],
            env=env, stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT, creationflags=flags)
        began = time.monotonic()
        while child.poll() is None:
            if available() < 2 * 1024**3 or time.monotonic() - began > 60:
                child.kill(); child.wait(timeout=10)
                raise RuntimeError('Owned PG startup reached memory/time guard; finally stops only this cluster')
            time.sleep(.25)
    assert child.returncode == 0
    started = True
    lines = (data / 'postmaster.pid').read_text().splitlines()
    pid, port = int(lines[0]), int(lines[3])
    assert port == 8295
    (out / 'handle.original.json').write_text(json.dumps({'pid': pid, 'port': port, 'data': str(data),
        'at_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(), 'only_task_owned_test_cluster_reused': True,
        'no_production_connection': True, 'all_startup_standard_streams_redirected_to_private_files': True, 'prior_pipe_timeout_original_retained': True}, indent=2) + '\n')
    env.update(FANTASYCARD_TEST_POSTGRES=f'Host=127.0.0.1;Port={port};Database=postgres;Username=branch_test;Pooling=false',
        FANTASYCARD_E2E_SERVER_DLL=str(b / 'f03-steam-integration-r1/build/bin/FantasyCard.Server/release/FantasyCard.Server.dll'),
        FANTASYCARD_BRANCH_TEST_EVIDENCE=str(private / 'steam-process-evidence'))
    command = ['dotnet', 'test', str(work / 'server/tests/FantasyCard.Server.Tests/FantasyCard.Server.Tests.csproj'),
        '-c', 'Release', '--no-build', '--artifacts-path', str(b / 'f03-steam-integration-r1/build'),
        '--filter', 'FullyQualifiedName~PostgresSteamDisplayNameTests|FullyQualifiedName~PostgresSteamPersonaHttpTests',
        '--logger', 'trx;LogFileName=steam-pg.trx', '--results-directory', str(out / 'results'), '--verbosity', 'minimal', '-m:1']
    test = guard.guarded_run(command, env=env, timeout=180, wait_seconds=30)
    (private / 'steam-tests.private.log').write_text(test.stdout + test.stderr, encoding='utf-8')
finally:
    if started or (data / 'postmaster.pid').exists():
        with (private / 'steam-stop.private.log').open('wb') as log:
            stop = subprocess.run([str(pg / 'pg_ctl.exe'), '-D', str(data), '-m', 'fast', '-w', 'stop'],
                stdout=log, stderr=subprocess.STDOUT, timeout=60, creationflags=flags)
        assert stop.returncode == 0
    status = subprocess.run([str(pg / 'pg_ctl.exe'), '-D', str(data), 'status'], capture_output=True, creationflags=flags)
    proof = {'exit': test.returncode if test else None, 'owned_PG_stopped': status.returncode == 3,
        'pid_file_absent': not (data / 'postmaster.pid').exists(), 'input_merge_candidate': info['detached_validation_commit'],
        'real_external_Steam_provider_used': False, 'new_gameplay_cases': 0, 'production_changed': False}
    (out / 'result.json').write_text(json.dumps(proof, indent=2) + '\n')
    print(json.dumps(proof))
assert test and test.returncode == 0 and proof['owned_PG_stopped'] and proof['pid_file_absent']
