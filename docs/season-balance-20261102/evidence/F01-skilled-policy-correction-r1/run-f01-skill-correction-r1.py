from pathlib import Path
import subprocess, json, importlib.util, os, datetime, ctypes, time
b = Path(__file__).parent
out = b / 'f01-skill-correction-r1'
private = Path(r'G:\PR13Evidence\private\season-balance-20261102-f03-google-r1')
data = private / 'pgdata'
pg = Path(r'G:\Program Files\GodotFiles\godot_FanstaryCard\tools\engine-local\protected\postgres\pgsql\bin')
info = {'worktree': str(Path.cwd()), 'detached_validation_commit': subprocess.check_output(['git', 'rev-parse', 'HEAD']).decode().strip()}
work = Path(info['worktree'])
assert not out.exists() and not (data / 'postmaster.pid').exists()
assert data.resolve() == Path(r'G:\PR13Evidence\private\season-balance-20261102-f03-google-r1\pgdata')
assert (data / 'PG_VERSION').read_text().strip() == '18'
assert json.loads((b / 'f01-skill-preflight-r1/result.json').read_bytes())['exit'] == 0
budget_path = work / 'docs/season-balance-20261102/F01-BUDGET.json'
prior_budget = budget_path.read_bytes(); budget = json.loads(prior_budget)
case_id = 'original-skills-day15-three'
maximum_new = 3
calendar_output = b / 'f01-skill-correction/observations'
calendar_control = private / 'f01-skill-correction/control.private.json'
assert budget['approved'] and not budget['synthetic'] and budget['used'] == 297 and budget['current_handle'] is None
journal_path = Path(budget['journal']); prior_journal = journal_path.read_bytes(); assert prior_journal.endswith(b'\n')
prior_entries = [json.loads(line) for line in prior_journal.decode('utf-8').splitlines()]
prior_started = [row['payload']['caseId'] for row in prior_entries if row['payload']['kind'] == 'started']
assert len(prior_started) == budget['used'] and calendar_control.exists()
import hashlib
pin = json.loads((b/'f01-skill-preflight-r1/source-pin.original.json').read_bytes())
assert all(hashlib.sha256((work/n).read_bytes()).hexdigest()==h for n,h in pin.items())
for item, used in [('D03',308),('B05',330)]:
    other=json.loads((work/f'docs/season-balance-20261102/{item}-BUDGET.json').read_bytes());assert other['used']==used and other.get('current_handle') is None
for key in ['skill_correction_plan','skill_correction_policy']:
    assert hashlib.sha256(Path(budget[key]['source']).read_bytes()).hexdigest()==budget[key]['sha256']
out.mkdir()
(out / 'prior-budget.original.json').write_bytes(prior_budget)
(out / 'prior-journal.original.jsonl').write_bytes(prior_journal)
budget.update(current_handle={'parent_pid': os.getpid(), 'case_id': case_id, 'output': str(out), 'no_duplicate_launch': True}, reserved_current=maximum_new)
budget_path.write_text(json.dumps(budget, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
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
    with (private / 'f01-skill-correction-r1-start-r2.private.log').open('wb') as log:
        child = subprocess.Popen([str(pg / 'pg_ctl.exe'), '-D', str(data), '-l', str(private / 'f01-skill-correction-r1-pg-r2.private.log'),
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
        if key.startswith('FANTASYCARD_'): env[key] = ''
    env.update(FANTASYCARD_TEST_POSTGRES=f'Host=127.0.0.1;Port={port};Database=postgres;Username=branch_test;Pooling=false',
        FANTASYCARD_RUN_F01_SKILL_CORRECTION='1', FANTASYCARD_F01_CALENDAR_OUTPUT=str(calendar_output),
        FANTASYCARD_F01_CALENDAR_CONTROL=str(calendar_control), FANTASYCARD_F01_CALENDAR_MAX_NEW=str(maximum_new),
        FANTASYCARD_F01_BUDGET=str(budget_path))
    compiled = json.loads((b / 'f01-skill-preflight-r1/result.json').read_bytes())
    query = "SELECT schema_name FROM information_schema.schemata WHERE schema_name LIKE 'fc_runtime_test_%' ORDER BY schema_name"
    schema_command = [str(pg / 'psql.exe'), '-h', '127.0.0.1', '-p', str(port), '-U', 'branch_test', '-d', 'postgres', '-XAt', '-c', query]
    before = subprocess.run(schema_command, capture_output=True, text=True, creationflags=flags, timeout=15)
    assert before.returncode == 0
    (out / 'schemas-before.original.json').write_text(json.dumps(before.stdout.splitlines()) + '\n')
    (out / 'results').mkdir()
    binary = Path(compiled['private_build']) / 'bin/FantasyCard.Server.Tests/release'
    command = ['dotnet', str(binary/'FantasyCard.Server.Tests.dll'), '-noLogo', '-noColor', '-noAutoReporters', '-failSkips', '-parallel', 'none', '-reporter', 'verbose',
        '-method', 'FantasyCard.Server.Tests.Persistence.PostgresFirstFortnightCalendarTests.OriginalSkilledAccountsContinueWithUsefulStarterEquipmentPolicy',
        '-trx', str(out/'results/support-week.trx'), '-xml', str(out/'results/support-week.xml')]
    test = guard.guarded_run(command, env=env, timeout=1800, wait_seconds=30)
    (private / 'f01-skill-correction-r1-tests.private.log').write_text(test.stdout + test.stderr, encoding='utf-8')
    after = subprocess.run(schema_command, capture_output=True, text=True, creationflags=flags, timeout=15)
    assert after.returncode == 0
    schemas = {'before': before.stdout.splitlines(), 'after': after.stdout.splitlines(),
        'new_schema_residuals': sorted(set(after.stdout.splitlines()) - set(before.stdout.splitlines()))}
    (out / 'schemas-after.original.json').write_text(json.dumps(schemas, indent=2) + '\n')
    assert not schemas['new_schema_residuals']

finally:
    if started or (data / 'postmaster.pid').exists():
        with (private / 'f01-skill-correction-r1-stop.private.log').open('wb') as log:
            stop = subprocess.run([str(pg / 'pg_ctl.exe'), '-D', str(data), '-m', 'fast', '-w', 'stop'],
                stdout=log, stderr=subprocess.STDOUT, timeout=60, creationflags=flags)
        assert stop.returncode == 0
    status = subprocess.run([str(pg / 'pg_ctl.exe'), '-D', str(data), 'status'], capture_output=True, creationflags=flags)
    proof = {'exit': test.returncode if test else None, 'owned_PG_stopped': status.returncode == 3,
        'pid_file_absent': not (data / 'postmaster.pid').exists(), 'source_common_commit': info['detached_validation_commit'],
        'external_identity_provider_used': False, 'preflight_only': False, 'production_changed': False}
    (out / 'result.json').write_text(json.dumps(proof, indent=2) + '\n')
    starts = []
    if journal_path.exists():
        raw = journal_path.read_bytes(); assert raw.endswith(b'\n'), 'Keep original incomplete journal and handle; no retry'
        entries = [json.loads(line) for line in raw.decode('utf-8').splitlines()]
        starts = [row['payload']['caseId'] for row in entries if row['payload']['kind'] == 'started']
        allowed_cases = set(budget['smoke_case_ids']) | {row['id'] for row in json.loads(Path(budget['initial_plan']['source']).read_bytes())['attempts']} | {row['id'] for row in json.loads(Path(budget['support_week_plan']['source']).read_bytes())['attempts']} | {row['id'] for row in json.loads(Path(budget['skill_correction_plan']['source']).read_bytes())['attempts']}
        assert len(starts) == len(set(starts)) and set(starts).issubset(allowed_cases)
    assert len(prior_started) <= len(starts) <= len(prior_started) + maximum_new
    assert starts[:len(prior_started)] == prior_started
    (out / 'after-journal.original.jsonl').write_bytes(journal_path.read_bytes())
    budget.update(used=len(starts), remaining=budget['maximum']-len(starts), current_handle=None, reserved_current=0,
        last_result=str(out/'result.json'), last_case=case_id, last_case_driver_exit=proof['exit'])
    budget_path.write_text(json.dumps(budget,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    proof.update(actual_started=len(starts)-len(prior_started), new_gameplay_cases=len(starts)-len(prior_started), F01_used=budget['used'], F01_remaining=budget['remaining'])
    proof.update(source_unchanged=all(hashlib.sha256((work/n).read_bytes()).hexdigest()==h for n,h in pin.items()), original_accounts_continued_without_reset=True, D03_new=0, B05_new=0, skill_correction_only=True)
    if calendar_control.exists():
        c = json.loads(calendar_control.read_bytes())
        proof.update(calendar_schema=c['Schema'], calendar_status=c['Status'], next_index=c['NextIndex'], current_case=c['CurrentCase'], finished_count=len(c['Finished']), skipped_count=len(c['Skipped']), schema_intentionally_retained=True)
    (out/'result.json').write_text(json.dumps(proof,indent=2)+'\n')
    print(json.dumps(proof))
assert test and test.returncode == 0 and proof['owned_PG_stopped'] and proof['pid_file_absent']
