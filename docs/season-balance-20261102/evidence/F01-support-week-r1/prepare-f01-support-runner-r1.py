from pathlib import Path

b=Path(__file__).parent;source=(b/'run-f01-calendar-batch2-r3.py').read_text('utf-8')
changes=[
    ('f01-calendar-batch2-r3','f01-support-week-batch1-r1'),
    ('f01-calendar-build-r7','f01-support-week-preflight-r2'),
    ("case_id = 'calendar-batch2-remaining234'","case_id = 'support-week-first42'"),
    ('maximum_new = 45','maximum_new = 42'),
    ("calendar_output = b / 'f01-calendar-r1/observations'","calendar_output = b / 'f01-support-week-r1/observations'"),
    ("calendar_control = private / 'f01-calendar-r1/control.private.json'","calendar_control = private / 'f01-support-week-r1/control.private.json'"),
    ("budget['used'] == 210","budget['used'] == 255"),
    ('and calendar_control.exists()','and not calendar_control.exists()'),
    ("key.startswith('FANTASYCARD_RUN_')","key.startswith('FANTASYCARD_')"),
    ("FANTASYCARD_RUN_F01_CALENDAR='1'","FANTASYCARD_RUN_F01_SUPPORT_WEEK='1'"),
]
for old,new in changes:
    assert old in source,old;source=source.replace(old,new)
old="""    command = ['dotnet', 'test', str(work / 'server/tests/FantasyCard.Server.Tests/FantasyCard.Server.Tests.csproj'),
        '-c', 'Release', '--no-build', '--artifacts-path', compiled['private_build'],
        '--filter', 'FullyQualifiedName~PostgresFirstFortnightCalendarTests',
        '--logger', 'trx;LogFileName=f01-calendar.trx', '--results-directory', str(out / 'results'), '--verbosity', 'minimal', '-m:1']"""
new="""    (out / 'results').mkdir()
    binary = Path(compiled['private_build']) / 'bin/FantasyCard.Server.Tests/release'
    command = ['dotnet', str(binary/'FantasyCard.Server.Tests.dll'), '-noLogo', '-noColor', '-noAutoReporters', '-failSkips', '-parallel', 'none', '-reporter', 'verbose',
        '-method', 'FantasyCard.Server.Tests.Persistence.PostgresFirstFortnightCalendarTests.ThreeFreshNovicesReorganizeOwnedCardsDuringFirstWeek',
        '-trx', str(out/'results/support-week.trx'), '-xml', str(out/'results/support-week.xml')]"""
assert old in source;source=source.replace(old,new)
old="allowed_cases = set(budget['smoke_case_ids']) | {row['id'] for row in json.loads(Path(budget['initial_plan']['source']).read_bytes())['attempts']}"
new=old+" | {row['id'] for row in json.loads(Path(budget['support_week_plan']['source']).read_bytes())['attempts']}"
assert old in source;source=source.replace(old,new)
old='out.mkdir()'
new="""import hashlib
pin = json.loads((b/'f01-support-week-preflight-r2/source-pin.original.json').read_bytes())
assert all(hashlib.sha256((work/n).read_bytes()).hexdigest()==h for n,h in pin.items())
for item, used in [('D03',299),('B05',330)]:
    other=json.loads((work/f'docs/season-balance-20261102/{item}-BUDGET.json').read_bytes());assert other['used']==used and other.get('current_handle') is None
for key in ['support_week_plan','support_week_policy']:
    assert hashlib.sha256(Path(budget[key]['source']).read_bytes()).hexdigest()==budget[key]['sha256']
out.mkdir()"""
assert source.count(old)==1;source=source.replace(old,new)
old="proof.update(actual_started=len(starts)-len(prior_started), new_gameplay_cases=len(starts)-len(prior_started), F01_used=budget['used'], F01_remaining=budget['remaining'])"
new=old+"\n    proof.update(source_unchanged=all(hashlib.sha256((work/n).read_bytes()).hexdigest()==h for n,h in pin.items()), original_main_accounts_and_incomes_not_imported=True, D03_new=0, B05_new=0, support_week_only=True)"
assert old in source;source=source.replace(old,new)
target=b/'run-f01-support-week-batch1-r1.py';assert not target.exists();compile(source,str(target),'exec');target.write_text(source,encoding='utf-8');print(str(target))
