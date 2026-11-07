from pathlib import Path
import collections, ctypes, datetime, gzip, hashlib, importlib.util, io, json, os
import shutil, socket, subprocess, threading, time, xml.etree.ElementTree as ET

b = Path(__file__).parent; repo = Path.cwd()
out = b / 'f03-fixed-ordinary-r1'
private = Path(r'G:\PR13Evidence\private\season-balance-20261102-f03-google-r1\fixed-ordinary-r1')
artifacts = repo / 'tools/engine-local/protected/f03-fixed-ordinary-r1'
short_temp = Path(r'G:\PR13Evidence\private\f03t8')
assert not any(p.exists() for p in [out, private, artifacts, short_temp])
assert artifacts.resolve().is_relative_to((repo/'tools/engine-local/protected').resolve())
assert subprocess.run(['git','check-ignore','--quiet',str(artifacts/'ownership.json')]).returncode==0
assert subprocess.check_output(['git','rev-parse','HEAD']).decode().strip()=='1fe8e4b219714688c0bed061a3162628c5dd1cbe'
assert not subprocess.check_output(['git','status','--porcelain'])
for p in [out,private,artifacts,short_temp]:p.mkdir(parents=True)
flags=subprocess.CREATE_NO_WINDOW|subprocess.BELOW_NORMAL_PRIORITY_CLASS
sid=subprocess.check_output(['powershell','-NoProfile','-Command','[System.Security.Principal.WindowsIdentity]::GetCurrent().User.Value'],creationflags=flags).decode().strip()
for p in [private,artifacts,short_temp]:
 r=subprocess.run(['icacls',str(p),'/inheritance:r','/grant:r','*'+sid+':(OI)(CI)F','*S-1-5-18:(OI)(CI)F','*S-1-5-32-544:(OI)(CI)F'],capture_output=True,creationflags=flags);assert r.returncode==0
 (p/'ownership.json').write_text(json.dumps(dict(task='season-balance-20261102',scope='fixed1fe8 protected ordinary regression; never publish private DLLs'))+'\n')
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
report=json.loads((b/'f03-protected-build-r3/result.json').read_bytes());package=Path(report['output'])
eligibility=json.loads((b/'f03-fixed-inventory-r1/eligibility.derived.json').read_bytes())
assert eligibility['source_commit']==report['source_commit']=='1fe8e4b219714688c0bed061a3162628c5dd1cbe'
selected=eligibility['selected'];excluded=eligibility['excluded'];assert len(selected)==1139 and len(excluded)==79
source_pins=json.loads((b/'f03-protected-build-r3/source-pin.json').read_bytes())
for name in subprocess.check_output(['git','ls-files','-z','--','client/data','client/tests/fixture_runtime.py']).decode().split('\0'):
 if name and (repo/name).is_file():source_pins[name]=sha(repo/name)
assert all(sha(repo/name)==expected for name,expected in source_pins.items())
fixture_pins=[dict(path=name,sha256=value) for name,value in source_pins.items()];workspace=repo
input_pins={};suites=[];original_suites=[]
for source_path in report['test_assemblies']:
 original=Path(source_path);destination=artifacts/original.stem;shutil.copytree(original.parent,destination)
 suites.append(destination/original.name);original_suites.append(original)
 for p in original.parent.iterdir():
  if p.is_file():assert sha(destination/p.name)==sha(p);input_pins[str(destination/p.name)]=sha(p)
 input_pins[str(original)]=sha(original)
 runner=destination/'xunit.runner.json'
 if runner.exists():(out/(original.stem+'.runner-before.original.json')).write_bytes(runner.read_bytes())
 runner.write_text(json.dumps(dict(maxParallelThreads=1,parallelizeAssembly=False,parallelizeTestCollections=False),indent=2)+'\n');input_pins[str(runner)]=sha(runner)
 for name,hashes in report['assemblies'].items():
  assert sha(package/name)==hashes['protected_sha256']
  if (destination/name).exists():assert sha(destination/name)==hashes['protected_sha256']
assert (package/'CANDIDATE-NOT-YET-VALIDATED.txt').is_file()
# The existing benchmark uses a fixed ignored output folder. Preserve its present bytes before this run can replace them.
prior_samples=repo/'server/.artifacts/qa-migration/samples';preserved=private/'preexisting-generated-samples';preserved.mkdir();prior_manifest=[]
for p in sorted(prior_samples.glob('*')):
 if p.is_file():
  q=preserved/p.name;shutil.copyfile(p,q);assert sha(p)==sha(q);prior_manifest.append(dict(name=p.name,sha256=sha(q),bytes=q.stat().st_size,source_mtime=p.stat().st_mtime))
(out/'preexisting-samples-manifest.json').write_text(json.dumps(prior_manifest,indent=2)+'\n')
plan=dict(source_commit=report['source_commit'],selected_method_definitions=1139,excluded_method_definitions=79,selected_methods=selected,excluded_methods=excluded,
 protected_runtime_hashes=report['assemblies'],all_input_pins=input_pins,source_pins=source_pins,short_temp=str(short_temp),
 exact_package_required=True,full_suite_certificate=False,no_manual_optins=True,no_native_clients=True,no_sealed_numerical_queues=True,
 no_old_normal_cycle_matrix=True,budgets=dict(D03_used=308,D03_max=308,F01_used=300,F01_max=300,B05_used=330,B05_max=330))
(out/'plan.original.json').write_text(json.dumps(plan,indent=2)+'\n')

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
temp = short_temp
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
            if any(r['method'] == 'Migration_default_binary_routes_ticket_security_and_real_sample_benchmark' for r in batch_rows):
                samples_dir = repo / 'server/.artifacts/qa-migration/samples'
                destination = private / ('generated-migration-' + suite.stem + '-b' + str(offset // 60 + 1))
                destination.mkdir()
                sample_rows = []
                for source_file in sorted(samples_dir.glob('*')):
                    if not source_file.is_file(): continue
                    q = destination / source_file.name
                    shutil.copyfile(source_file, q); assert sha(q) == sha(source_file)
                    sample_rows.append(dict(name=source_file.name, sha256=sha(q), bytes=q.stat().st_size, source_mtime=source_file.stat().st_mtime))
                (target / 'generated-sample-manifest.json').write_text(json.dumps(sample_rows, indent=2) + '\n')
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
    result = dict(ok=error is None, error=error, runs=runs, selected_method_definitions=1139, prior_completed_method_definitions=0,
                  excluded_method_definitions=79, new_D03_F01_B05_attempts=0, native_clients_started=0,
                  full_suite_certificate_written=False, candidate_marker_retained=True, production_changed=False,
                  own_PG_stopped=not (data / 'postmaster.pid').exists(), own_job_closed=True,
                  minimum_available_bytes=min((r['available_bytes'] for r in samples), default=available()),
                  progress='33/35', completed_at_utc=datetime.datetime.now(datetime.timezone.utc).isoformat())
    (out / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result))
assert result['ok'], result['error']
