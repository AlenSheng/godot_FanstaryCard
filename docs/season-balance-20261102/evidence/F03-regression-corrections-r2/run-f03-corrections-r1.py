from pathlib import Path
import ctypes, datetime, hashlib, importlib.util, json, os, socket, subprocess, threading, time, xml.etree.ElementTree as ET

b = Path(__file__).parent; repo = Path.cwd(); out = b / 'f03-corrections-r1'
private = Path(r'G:\PR13Evidence\private\season-balance-20261102-f03-google-r1\corrections-r1')
artifacts = repo / 'tools/engine-local/protected/f03-corrections-r1'
short_temp = Path(r'G:\PR13Evidence\private\f03t5')
assert not any(p.exists() for p in [out, private, artifacts, short_temp])
assert artifacts.resolve().is_relative_to((repo / 'tools/engine-local/protected').resolve())
assert subprocess.run(['git', 'check-ignore', '--quiet', str(artifacts / 'ownership.json')]).returncode == 0
for p in [out, private, artifacts, short_temp]: p.mkdir(parents=True)
flags = subprocess.CREATE_NO_WINDOW | subprocess.BELOW_NORMAL_PRIORITY_CLASS
sid = subprocess.check_output(['powershell', '-NoProfile', '-Command', '[System.Security.Principal.WindowsIdentity]::GetCurrent().User.Value'], creationflags=flags).decode().strip()
for p in [private, artifacts, short_temp]:
    r = subprocess.run(['icacls', str(p), '/inheritance:r', '/grant:r', '*' + sid + ':(OI)(CI)F', '*S-1-5-18:(OI)(CI)F', '*S-1-5-32-544:(OI)(CI)F'], capture_output=True, creationflags=flags)
    assert r.returncode == 0
    (p / 'ownership.json').write_text(json.dumps(dict(task='season-balance-20261102', purpose='private unprotected correction verification; do not publish binaries')) + '\n')
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
names = subprocess.check_output(['git', 'ls-files', '-z', '--', 'server/src', 'server/tests', 'server/config', 'server/deploy', 'config/FantasyCard_Config.xlsx', 'client/data']).decode().split('\0')
pins = {name: sha(repo / name) for name in names if name and (repo / name).is_file()}
failure_index = json.loads((b / 'f03-protected-ordinary-r4-failure-index.derived.json').read_bytes())
methods = sorted({r['name'].split('(')[0] for r in failure_index['rows']} | {'FantasyCard.Server.Tests.EndToEnd.RealNetworkEndToEndTests.Reforge_quote_authenticates_before_missing_or_malformed_query_validation'})
assert len(methods) == 23
(out / 'inputs.original.json').write_text(json.dumps(dict(scope='Unprotected current-source correction check; not a protected package certificate', base_head=subprocess.check_output(['git', 'rev-parse', 'HEAD']).decode().strip(), source_pins=pins, methods=methods, short_temp=str(short_temp), expected_minimum_cases=32, no_manual_numerical_optins=True), indent=2) + '\n')

class Memory(ctypes.Structure):
    _fields_ = [('length', ctypes.c_ulong), ('load', ctypes.c_ulong)] + [(n, ctypes.c_ulonglong) for n in ['total', 'available', 'p', 'ap', 'v', 'av', 'e']]

def available():
    value = Memory(); value.length = ctypes.sizeof(value)
    assert ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(value)); return value.available

class Basic(ctypes.Structure):
    _fields_ = [('p', ctypes.c_longlong), ('j', ctypes.c_longlong), ('flags', ctypes.c_ulong), ('min', ctypes.c_size_t), ('max', ctypes.c_size_t), ('active', ctypes.c_ulong), ('affinity', ctypes.c_size_t), ('priority', ctypes.c_ulong), ('schedule', ctypes.c_ulong)]

class Limits(ctypes.Structure):
    _fields_ = [('basic', Basic), ('io', ctypes.c_ulonglong * 6), ('pm', ctypes.c_size_t), ('jm', ctypes.c_size_t), ('pp', ctypes.c_size_t), ('pj', ctypes.c_size_t)]

k = ctypes.WinDLL('kernel32', use_last_error=True); k.CreateJobObjectW.restype = ctypes.c_void_p
k.SetInformationJobObject.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p, ctypes.c_ulong]
k.AssignProcessToJobObject.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
k.TerminateJobObject.argtypes = [ctypes.c_void_p, ctypes.c_uint]; k.CloseHandle.argtypes = [ctypes.c_void_p]
job = k.CreateJobObjectW(None, None); assert job
limits = Limits(); limits.basic.flags = 0x2000 | 0x20; limits.basic.priority = 0x4000
assert k.SetInformationJobObject(job, 9, ctypes.byref(limits), ctypes.sizeof(limits))
popen = subprocess.Popen; admissions = []

def own(*args, **kwargs):
    child = popen(*args, **kwargs)
    if not k.AssignProcessToJobObject(job, int(child._handle)):
        error = ctypes.get_last_error(); child.kill(); child.wait(timeout=10); raise ctypes.WinError(error)
    admissions.append(dict(pid=child.pid, at_utc=datetime.datetime.now(datetime.timezone.utc).isoformat())); return child

subprocess.Popen = own
stop = threading.Event(); breach = threading.Event(); samples = []

def watch():
    while not stop.wait(.25):
        value = available(); samples.append(dict(at_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(), available_bytes=value))
        if value < 2 * 1024 ** 3: breach.set(); k.TerminateJobObject(job, 91); return

thread = threading.Thread(target=watch, daemon=True); thread.start()
spec = importlib.util.spec_from_file_location('guard', repo / 'client/tests/fixture_runtime.py')
guard = importlib.util.module_from_spec(spec); spec.loader.exec_module(guard)
env = {key: value for key, value in os.environ.items() if not key.startswith('FANTASYCARD_')}
env.update(DOTNET_CLI_TELEMETRY_OPTOUT='1', DOTNET_NOLOGO='1', DOTNET_CLI_UI_LANGUAGE='en', TEMP=str(short_temp), TMP=str(short_temp))
pgbin = Path(r'G:\Program Files\GodotFiles\godot_FanstaryCard\tools\engine-local\protected\postgres\pgsql\bin')
data = private / 'pgdata'; started = False; error = None; totals = None; runtime_pins = {}

def run_file(command, name, admission=True):
    if admission:
        values = []
        for _ in range(3): values.append(available()); time.sleep(1)
        assert min(values) >= 3 * 1024 ** 3
    with (private / (name + '.log')).open('wb') as log:
        child = subprocess.Popen(command, env=env, stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT, creationflags=flags)
        assert child.wait(timeout=60) == 0

try:
    project = repo / 'server/tests/FantasyCard.Server.Tests/FantasyCard.Server.Tests.csproj'
    build = guard.guarded_run(['dotnet', 'build', str(project), '-c', 'Release', '--artifacts-path', str(artifacts), '-m:1', '-p:UseSharedCompilation=false', '--verbosity', 'minimal'], env=env, timeout=300, wait_seconds=30)
    (out / 'build.original.log').write_text(build.stdout + build.stderr, encoding='utf-8')
    assert build.returncode == 0, (build.stdout + build.stderr)[-1600:]
    suite_dir = artifacts / 'bin/FantasyCard.Server.Tests/release'
    (suite_dir / 'xunit.runner.json').write_text(json.dumps(dict(maxParallelThreads=1, parallelizeAssembly=False, parallelizeTestCollections=False)) + '\n')
    runtime_pins = {str(p): sha(p) for p in suite_dir.glob('FantasyCard.*.dll')}
    run_file([str(pgbin / 'initdb.exe'), '-D', str(data), '-U', 'correction_test', '-A', 'trust', '--no-locale', '-E', 'UTF8'], 'initdb')
    with socket.socket() as listener: listener.bind(('127.0.0.1', 0)); port = listener.getsockname()[1]
    run_file([str(pgbin / 'pg_ctl.exe'), '-D', str(data), '-w', '-l', str(private / 'postgres.log'), '-o', f'-h 127.0.0.1 -p {port} -F -c shared_buffers=32MB -c max_connections=40 -c max_wal_size=128MB -c min_wal_size=80MB', 'start'], 'pg-start')
    started = True
    env['FANTASYCARD_TEST_POSTGRES'] = f'Host=127.0.0.1;Port={port};Database=postgres;Username=correction_test;Pooling=false'
    env['FANTASYCARD_E2E_SERVER_DLL'] = str(suite_dir / 'FantasyCard.Server.dll')
    env['FANTASYCARD_E2E_PROCESS_LOG_DIR'] = str(private / 'process-logs')
    settings = out / 'corrections.runsettings'; root = ET.Element('RunSettings'); config = ET.SubElement(root, 'RunConfiguration')
    ET.SubElement(config, 'MaxCpuCount').text = '1'; ET.SubElement(config, 'TestCaseFilter').text = '|'.join('FullyQualifiedName=' + name for name in methods)
    ET.ElementTree(root).write(settings, encoding='utf-8', xml_declaration=True)
    command = ['dotnet', 'test', str(project), '--no-build', '--no-restore', '-c', 'Release', '--artifacts-path', str(artifacts), '--settings', str(settings), '--logger', 'trx', '--results-directory', str(out)]
    run = guard.guarded_run(command, env=env, timeout=600, wait_seconds=30)
    (out / 'run.original.log').write_text(run.stdout + run.stderr, encoding='utf-8')
    trxs = list(out.glob('*.trx')); assert trxs
    totals = {key: 0 for key in ['total', 'passed', 'failed', 'notExecuted']}; actual = set()
    for trx in trxs:
        document = ET.parse(trx); counters = document.find('.//{*}Counters'); assert counters is not None
        for key in totals: totals[key] += int(counters.get(key, '0'))
        for unit in document.findall('.//{*}UnitTest'):
            method = unit.find('{*}TestMethod'); actual.add(method.get('className', '').split(',')[0] + '.' + method.get('name', ''))
    assert actual == set(methods), ('Unexpected/missing methods', actual ^ set(methods))
    assert run.returncode == 0 and totals['total'] >= 32 and totals['passed'] == totals['total'] and not totals['notExecuted'], totals
    assert all(sha(repo / name) == expected for name, expected in pins.items())
    assert all(sha(Path(name)) == expected for name, expected in runtime_pins.items())
except BaseException as exc:
    error = dict(type=type(exc).__name__, message=str(exc))
    if isinstance(exc, subprocess.TimeoutExpired):
        def text(value): return value.decode('utf-8', errors='replace') if isinstance(value, bytes) else value or ''
        (out / 'timeout-output.original.log').write_text(text(exc.output) + text(exc.stderr), encoding='utf-8')
finally:
    try:
        if started and (data / 'postmaster.pid').exists() and not breach.is_set(): run_file([str(pgbin / 'pg_ctl.exe'), '-D', str(data), '-m', 'fast', '-w', 'stop'], 'pg-stop', admission=False)
    except BaseException as exc: error = error or dict(type=type(exc).__name__, message=str(exc))
    k.TerminateJobObject(job, 92); k.CloseHandle(job); subprocess.Popen = popen; stop.set(); thread.join(timeout=5)
    (out / 'resources.original.json').write_text(json.dumps(dict(samples=samples, breach=breach.is_set(), own_process_admissions=admissions, reserve_bytes=2 * 1024 ** 3, startup_bytes=1024 ** 3), indent=2) + '\n')
    result = dict(ok=error is None, error=error, tests=totals, source_corrected_unprotected_runtime=True,
                  runtime_input_hashes=runtime_pins, own_job_closed=True, own_PG_stopped=not (data / 'postmaster.pid').exists(),
                  new_D03_F01_B05_attempts=0, native_clients_started=0, production_changed=False, protected_certificate=False)
    (out / 'result.json').write_text(json.dumps(result, indent=2) + '\n'); print(json.dumps(result))
assert result['ok'], result['error']
