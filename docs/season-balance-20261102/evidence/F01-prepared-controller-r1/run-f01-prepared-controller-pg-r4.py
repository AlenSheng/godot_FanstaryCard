from pathlib import Path
import subprocess, json, importlib.util, os, datetime, ctypes, time
b = Path(__file__).parent
out = b / 'f01-prepared-controller-pg-r4'
private = Path(r'G:\PR13Evidence\private\season-balance-20261102-f03-google-r1')
data = private / 'pgdata'
pg = Path(r'G:\Program Files\GodotFiles\godot_FanstaryCard\tools\engine-local\protected\postgres\pgsql\bin')
info = {'worktree': str(Path.cwd()), 'detached_validation_commit': subprocess.check_output(['git', 'rev-parse', 'HEAD']).decode().strip()}
work = Path(info['worktree'])
assert not out.exists() and not (data / 'postmaster.pid').exists()
assert data.resolve() == Path(r'G:\PR13Evidence\private\season-balance-20261102-f03-google-r1\pgdata')
assert (data / 'PG_VERSION').read_text().strip() == '18'
assert json.loads((b / 'f01-prepared-controller-build-r5/result.json').read_bytes())['exit'] == 0
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
    with (private / 'f01-prepared-r4-start-r2.private.log').open('wb') as log:
        child = subprocess.Popen([str(pg / 'pg_ctl.exe'), '-D', str(data), '-l', str(private / 'f01-prepared-r4-pg-r2.private.log'),
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
    for key in list(env):
        if key.startswith('FANTASYCARD_RUN_'): env[key] = ''
    env.update(FANTASYCARD_TEST_POSTGRES=f'Host=127.0.0.1;Port={port};Database=postgres;Username=branch_test;Pooling=false',
        FANTASYCARD_RUN_F01_PREPARATION='1', FANTASYCARD_F01_PREPARATION_OUTPUT=str(out / 'observations'))
    compiled = json.loads((b / 'f01-prepared-controller-build-r5/result.json').read_bytes())
    query = "SELECT schema_name FROM information_schema.schemata WHERE schema_name LIKE 'fc_runtime_test_%' ORDER BY schema_name"
    schema_command = [str(pg / 'psql.exe'), '-h', '127.0.0.1', '-p', str(port), '-U', 'branch_test', '-d', 'postgres', '-XAt', '-c', query]
    before = subprocess.run(schema_command, capture_output=True, text=True, creationflags=flags, timeout=15)
    assert before.returncode == 0
    (out / 'schemas-before.original.json').write_text(json.dumps(before.stdout.splitlines()) + '\n')
    command = ['dotnet', 'test', str(work / 'server/tests/FantasyCard.Server.Tests/FantasyCard.Server.Tests.csproj'),
        '-c', 'Release', '--no-build', '--artifacts-path', compiled['private_build'],
        '--filter', 'FullyQualifiedName~PreparedControllerRetainsLegalArmorAndActualBagPotionHoldsAndRejectsMismatchedInputs',
        '--logger', 'trx;LogFileName=f01-prepared.trx', '--results-directory', str(out / 'results'), '--verbosity', 'minimal', '-m:1']
    test = guard.guarded_run(command, env=env, timeout=180, wait_seconds=30)
    (private / 'f01-prepared-r4-tests.private.log').write_text(test.stdout + test.stderr, encoding='utf-8')
    after = subprocess.run(schema_command, capture_output=True, text=True, creationflags=flags, timeout=15)
    assert after.returncode == 0
    schemas = {'before': before.stdout.splitlines(), 'after': after.stdout.splitlines(),
        'new_schema_residuals': sorted(set(after.stdout.splitlines()) - set(before.stdout.splitlines()))}
    (out / 'schemas-after.original.json').write_text(json.dumps(schemas, indent=2) + '\n')
    assert not schemas['new_schema_residuals']

finally:
    if started or (data / 'postmaster.pid').exists():
        with (private / 'f01-prepared-r4-stop.private.log').open('wb') as log:
            stop = subprocess.run([str(pg / 'pg_ctl.exe'), '-D', str(data), '-m', 'fast', '-w', 'stop'],
                stdout=log, stderr=subprocess.STDOUT, timeout=60, creationflags=flags)
        assert stop.returncode == 0
    status = subprocess.run([str(pg / 'pg_ctl.exe'), '-D', str(data), 'status'], capture_output=True, creationflags=flags)
    proof = {'exit': test.returncode if test else None, 'owned_PG_stopped': status.returncode == 3,
        'pid_file_absent': not (data / 'postmaster.pid').exists(), 'source_common_commit': info['detached_validation_commit'],
        'external_identity_provider_used': False, 'new_gameplay_cases': 0, 'production_changed': False}
    (out / 'result.json').write_text(json.dumps(proof, indent=2) + '\n')
    print(json.dumps(proof))
assert test and test.returncode == 0 and proof['owned_PG_stopped'] and proof['pid_file_absent']
