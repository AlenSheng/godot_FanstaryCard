from pathlib import Path
import collections, ctypes, datetime, gzip, hashlib, importlib.util, io, json, os
import shutil, socket, subprocess, threading, time, xml.etree.ElementTree as ET

b = Path(__file__).parent
repo = Path.cwd()
out = b / 'f03-protected-ordinary-r4'
private = Path(r'G:\PR13Evidence\private\season-balance-20261102-f03-google-r1\protected-ordinary-r4')
assert not out.exists() and not private.exists()
out.mkdir(); private.mkdir()
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
report = json.loads((b / 'f03-protected-build-r2/result.json').read_bytes())
package = Path(report['output'])
eligibility = json.loads(gzip.decompress((repo / 'docs/season-balance-20261102/evidence/F03-protected-test-inventory-r1/inventory/eligibility-review.derived.json.gz').read_bytes()))
prior = json.loads((b / 'f03-protected-safe-subset-r1/plan.original.json').read_bytes())
prior_names = {(r['type'], r['method']) for r in prior['selected_methods']}
ordinary = eligibility['groups']['no_attribute_gate'] + [r for r in eligibility['groups']['database_or_owned_fixture_gate'] if r['SkipUnless'] == 'HasTestDatabase']
assert len(ordinary) == 1138 and len(prior_names) == 80
selected = [r for r in ordinary if (r['type'], r['method']) not in prior_names and r['type'].startswith('FantasyCard.Server.Tests.')]
excluded = [r for values in eligibility['groups'].values() for r in values if (r['type'], r['method']) not in {(x['type'], x['method']) for x in ordinary}]
assert len(selected) == 631 and len(excluded) == 59
source = report['source_commit']
allowed_ext = {'.cs', '.csproj', '.props', '.targets', '.json', '.bytes', '.txt', '.yaml', '.yml', '.gd', '.xlsx', '.toml', '.proto'}
roots = ['server', 'config', 'protocol', 'client/network', 'client/data', 'client/tests', 'client/project.godot']
tree = subprocess.check_output(['git', 'ls-tree', '-r', '-l', source, '--', *roots]).decode().splitlines()
fixture = []
for line in tree:
    meta, name = line.split('\t'); p = Path(name)
    if any(n in p.parts for n in ['bin', 'obj', '.packages', '.artifacts', 'TestResults']):
        continue
    if p.suffix not in allowed_ext and not p.name.startswith(('Caddyfile', 'Dockerfile', 'project.godot')):
        continue
    fixture.append((name, meta.split()[2], int(meta.split()[3])))
payload = subprocess.run(['git', 'cat-file', '--batch'], input=b''.join((source + ':' + n + '\n').encode() for n, _, _ in fixture), capture_output=True, check=True).stdout
stream = io.BytesIO(payload); fixture_pins = []
workspace = private / 'workspace'; workspace.mkdir()
for name, oid, size in fixture:
    header = stream.readline().decode().split(); assert header == [oid, 'blob', str(size)]
    raw = stream.read(size); assert stream.read(1) == b'\n'
    assert hashlib.sha1(('blob ' + str(size) + '\0').encode() + raw).hexdigest() == oid
    target = workspace / name; target.parent.mkdir(parents=True, exist_ok=True); target.write_bytes(raw)
    fixture_pins.append(dict(path=name, git_blob=oid, sha256=sha(target), bytes=size))
assert not stream.read()
suites = []
input_pins = {}
for suite_path in report['test_assemblies']:
    original = Path(suite_path); destination = workspace / 'protected-tests' / original.stem
    shutil.copytree(original.parent, destination)
    suites.append(destination / original.name)
    for p in original.parent.iterdir():
        if p.is_file():
            assert sha(destination / p.name) == sha(p)
            input_pins[str(destination / p.name)] = sha(p)
    original_config = destination / 'xunit.runner.json'
    if original_config.exists():
        (out / (original.stem + '.runner-before.original.json')).write_bytes(original_config.read_bytes())
    original_config.write_text(json.dumps(dict(maxParallelThreads=1, parallelizeAssembly=False, parallelizeTestCollections=False), indent=2) + '\n')
    input_pins[str(original_config)] = sha(original_config)
    for name, hashes in report['assemblies'].items():
        assert sha(package / name) == hashes['protected_sha256']
        if (destination / name).exists():
            assert sha(destination / name) == hashes['protected_sha256']
plan = dict(source_commit=source, selected_method_definitions=len(selected), prior_completed_method_definitions=80,
            combined_ordinary_method_definitions=1138, selected_methods=selected, excluded_method_definitions=59,
            excluded_methods=excluded, fixture_files=fixture_pins, protected_test_input_hashes=input_pins,
            no_manual_optins=True, no_native_clients=True, no_sealed_numerical_queues=True,
            no_old_normal_cycle_matrix=True, full_certificate=False,
            budgets=dict(D03_used=308, D03_max=308, F01_used=300, F01_max=300, B05_used=330, B05_max=330))
(out / 'plan.original.json').write_text(json.dumps(plan, indent=2) + '\n')

class Memory(ctypes.Structure):
    _fields_ = [('length', ctypes.c_ulong), ('load', ctypes.c_ulong)] + [(n, ctypes.c_ulonglong) for n in ['total', 'available', 'p', 'ap', 'v', 'av', 'e']]

def available():
    m = Memory(); m.length = ctypes.sizeof(m)
    assert ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m))
    return m.available

class BasicLimit(ctypes.Structure):
    _fields_ = [('process_time', ctypes.c_longlong), ('job_time', ctypes.c_longlong), ('flags', ctypes.c_ulong),
                ('min_ws', ctypes.c_size_t), ('max_ws', ctypes.c_size_t), ('active', ctypes.c_ulong),
                ('affinity', ctypes.c_size_t), ('priority', ctypes.c_ulong), ('scheduling', ctypes.c_ulong)]

class ExtendedLimit(ctypes.Structure):
    _fields_ = [('basic', BasicLimit), ('io', ctypes.c_ulonglong * 6), ('process_memory', ctypes.c_size_t),
                ('job_memory', ctypes.c_size_t), ('peak_process', ctypes.c_size_t), ('peak_job', ctypes.c_size_t)]

kernel = ctypes.WinDLL('kernel32', use_last_error=True)
kernel.CreateJobObjectW.restype = ctypes.c_void_p
kernel.SetInformationJobObject.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p, ctypes.c_ulong]
kernel.AssignProcessToJobObject.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
kernel.TerminateJobObject.argtypes = [ctypes.c_void_p, ctypes.c_uint]
kernel.CloseHandle.argtypes = [ctypes.c_void_p]
job = kernel.CreateJobObjectW(None, None); assert job
limits = ExtendedLimit(); limits.basic.flags = 0x2000 | 0x20; limits.basic.priority = 0x4000
assert kernel.SetInformationJobObject(job, 9, ctypes.byref(limits), ctypes.sizeof(limits))
jobs = [job]
active_job = [job]
original_popen = subprocess.Popen
handles = []

def owned_popen(*args, **kwargs):
    child = original_popen(*args, **kwargs)
    if not kernel.AssignProcessToJobObject(active_job[0], int(child._handle)):
        error = ctypes.get_last_error(); child.kill(); child.wait(timeout=10); raise ctypes.WinError(error)
    handles.append(dict(pid=child.pid, at_utc=datetime.datetime.now(datetime.timezone.utc).isoformat()))
    return child

subprocess.Popen = owned_popen
spec = importlib.util.spec_from_file_location('guard', repo / 'client/tests/fixture_runtime.py')
guard = importlib.util.module_from_spec(spec); spec.loader.exec_module(guard)
samples = []; stop_monitor = threading.Event(); breached = threading.Event()

def monitor():
    while not stop_monitor.wait(.25):
        value = available(); samples.append(dict(at_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(), available_bytes=value))
        if value < 2 * 1024 ** 3:
            breached.set()
            for handle in list(jobs): kernel.TerminateJobObject(handle, 91)
            return

thread = threading.Thread(target=monitor, daemon=True); thread.start()
env = {k: v for k, v in os.environ.items() if not k.startswith('FANTASYCARD_')}
temp = private / 'temp'; temp.mkdir()
env.update(DOTNET_CLI_TELEMETRY_OPTOUT='1', DOTNET_NOLOGO='1', DOTNET_CLI_UI_LANGUAGE='en', TEMP=str(temp), TMP=str(temp))
pgbin = Path(r'G:\Program Files\GodotFiles\godot_FanstaryCard\tools\engine-local\protected\postgres\pgsql\bin')
data = private / 'pgdata'
port = None; pg_started = False; runs = []; error = None

def run_file(command, name, timeout=60, admission=True):
    if admission:
        values = []
        for _ in range(3):
            values.append(available()); time.sleep(1)
        assert min(values) >= 3 * 1024 ** 3, 'No startup admission'
    with (private / (name + '.log')).open('wb') as log:
        child = subprocess.Popen(command, env=env, stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT,
                                 creationflags=subprocess.CREATE_NO_WINDOW | subprocess.BELOW_NORMAL_PRIORITY_CLASS)
        code = child.wait(timeout=timeout)
    assert not breached.is_set() and code == 0, (name, code)

try:
    for suite in suites:
        domain = 'Domain' in suite.name
        if domain:
            continue
        rows = [r for r in selected if r['type'].startswith('FantasyCard.Domain.Tests.' if domain else 'FantasyCard.Server.Tests.')]
        if not domain:
            run_file([str(pgbin / 'initdb.exe'), '-D', str(data), '-U', 'protection_test', '-A', 'trust', '--no-locale', '-E', 'UTF8'], 'initdb')
            with socket.socket() as sock:
                sock.bind(('127.0.0.1', 0)); port = sock.getsockname()[1]
            run_file([str(pgbin / 'pg_ctl.exe'), '-D', str(data), '-w', '-l', str(private / 'postgres.log'), '-o',
                      f'-h 127.0.0.1 -p {port} -F -c shared_buffers=32MB -c max_connections=40 -c max_wal_size=128MB -c min_wal_size=80MB', 'start'], 'pg-start')
            pg_started = True
            env['FANTASYCARD_TEST_POSTGRES'] = f'Host=127.0.0.1;Port={port};Database=postgres;Username=protection_test;Pooling=false'
            env['FANTASYCARD_E2E_SERVER_DLL'] = str(package / 'FantasyCard.Server.dll')
            env['FANTASYCARD_E2E_PROCESS_LOG_DIR'] = str(private / 'process-logs')
        failed_batches = []
        for offset in range(0, len(rows), 60):
            batch_rows = rows[offset:offset + 60]
            target = out / (suite.stem + '-b' + str(offset // 60 + 1).zfill(2)); target.mkdir()
            settings = target / 'ordinary.runsettings'
            root = ET.Element('RunSettings'); config = ET.SubElement(root, 'RunConfiguration')
            ET.SubElement(config, 'MaxCpuCount').text = '1'
            ET.SubElement(config, 'TestCaseFilter').text = '|'.join('FullyQualifiedName=' + r['type'] + '.' + r['method'] for r in batch_rows)
            ET.ElementTree(root).write(settings, encoding='utf-8', xml_declaration=True)
            test_job = kernel.CreateJobObjectW(None, None); assert test_job
            assert kernel.SetInformationJobObject(test_job, 9, ctypes.byref(limits), ctypes.sizeof(limits))
            jobs.append(test_job); active_job[0] = test_job
            print(json.dumps(dict(batch=offset // 60 + 1, methods=len(batch_rows), started=True)), flush=True)
            batch_error = None; run = None
            try:
                run = guard.guarded_run(['dotnet', 'vstest', str(suite), '--Settings:' + str(settings), '--Logger:trx', '--ResultsDirectory:' + str(target)], env=env, timeout=600, wait_seconds=30)
                (target / 'run.original.log').write_text(run.stdout + run.stderr, encoding='utf-8')
            except subprocess.TimeoutExpired as exc:
                def as_text(value):
                    return value.decode('utf-8', errors='replace') if isinstance(value, bytes) else value or ''
                (target / 'run.original.log').write_text(as_text(exc.output) + as_text(exc.stderr), encoding='utf-8')
                batch_error = dict(type='TimeoutExpired', seconds=600)
            finally:
                active_job[0] = job
                kernel.TerminateJobObject(test_job, 93)
                jobs.remove(test_job); kernel.CloseHandle(test_job)
            assert not breached.is_set(), 'Memory reserve breached'
            totals = {k: 0 for k in ('total', 'passed', 'failed', 'notExecuted')}
            trxs = list(target.glob('*.trx')); actual = []
            declared = {(r['type'], r['method']) for r in batch_rows}
            for trx in trxs:
                document = ET.parse(trx); counters = document.find('.//{*}Counters'); assert counters is not None
                for key in totals: totals[key] += int(counters.get(key, '0'))
                for definition in document.findall('.//{*}UnitTest'):
                    method = definition.find('{*}TestMethod'); assert method is not None
                    pair = (method.get('className', '').split(',')[0], method.get('name', ''))
                    assert pair in declared, ('Unexpected test definition', pair)
                    actual.append(pair)
            ok = bool(run is not None and run.returncode == 0 and trxs and totals['total'] > 0 and totals['passed'] == totals['total'] and totals['notExecuted'] == 0 and set(actual) == declared)
            summary = dict(batch=offset // 60 + 1, assembly=suite.name, returncode=run.returncode if run else None,
                           selected_method_definitions=len(batch_rows), actual_method_definitions=len(set(actual)),
                           tests=totals, ok=ok, error=batch_error, own_test_job_closed=True)
            runs.append(summary)
            (target / 'result.json').write_text(json.dumps(summary, indent=2) + '\n')
            (out / 'runs.checkpoint.json').write_text(json.dumps(runs, indent=2) + '\n')
            print(json.dumps(summary), flush=True)
            if not ok: failed_batches.append(summary['batch'])
        assert not failed_batches, ('Failed/incomplete batches', failed_batches)
    assert all(sha(Path(p)) == h for p, h in input_pins.items())
    assert all(sha(workspace / r['path']) == r['sha256'] for r in fixture_pins)
    assert (package / 'CANDIDATE-NOT-YET-VALIDATED.txt').is_file()
except BaseException as exc:
    error = dict(type=type(exc).__name__, message=str(exc))
finally:
    try:
        if pg_started and (data / 'postmaster.pid').exists() and not breached.is_set():
            run_file([str(pgbin / 'pg_ctl.exe'), '-D', str(data), '-m', 'fast', '-w', 'stop'], 'pg-stop', admission=False)
    except BaseException as cleanup:
        error = error or dict(type=type(cleanup).__name__, message=str(cleanup))
    kernel.TerminateJobObject(job, 92)
    kernel.CloseHandle(job)
    subprocess.Popen = original_popen
    stop_monitor.set(); thread.join(timeout=5)
    (out / 'resources.original.json').write_text(json.dumps(dict(reserve_bytes=2 * 1024 ** 3, startup_bytes=1024 ** 3, samples=samples, breach=breached.is_set(), owned_process_admissions=handles), indent=2) + '\n')
    result = dict(ok=error is None, error=error, runs=runs, selected_method_definitions=631, prior_completed_method_definitions=80,
                  excluded_method_definitions=59, new_D03_F01_B05_attempts=0, native_clients_started=0,
                  full_suite_certificate_written=False, candidate_marker_retained=True, production_changed=False,
                  own_PG_stopped=not (data / 'postmaster.pid').exists(), own_job_closed=True,
                  minimum_available_bytes=min((r['available_bytes'] for r in samples), default=available()),
                  progress='33/35', completed_at_utc=datetime.datetime.now(datetime.timezone.utc).isoformat())
    (out / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result))
assert result['ok'], result['error']
