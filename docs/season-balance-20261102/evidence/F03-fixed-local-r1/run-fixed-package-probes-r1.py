from pathlib import Path
import hashlib, importlib.util, json, os, shutil, subprocess

b = Path(__file__).parent; repo = Path.cwd()
out = b / 'f03-fixed-probes-r1'
private = Path(r'G:\PR13Evidence\private\season-balance-20261102-f03-google-r1\fixed-probes-r1')
assert not out.exists() and not private.exists()
# One heavy validation process at a time: the complete ordinary run must be terminal before invoking this script.
ordinary = json.loads((b / 'f03-fixed-ordinary-r1/result.json').read_bytes())
assert ordinary['own_PG_stopped'] and ordinary['own_job_closed']
out.mkdir(); private.mkdir()
flags = subprocess.CREATE_NO_WINDOW | subprocess.BELOW_NORMAL_PRIORITY_CLASS
sid = subprocess.check_output(['powershell', '-NoProfile', '-Command', '[System.Security.Principal.WindowsIdentity]::GetCurrent().User.Value'], creationflags=flags).decode().strip()
acl = subprocess.run(['icacls', str(private), '/inheritance:r', '/grant:r', '*' + sid + ':(OI)(CI)F', '*S-1-5-18:(OI)(CI)F', '*S-1-5-32-544:(OI)(CI)F'], capture_output=True, creationflags=flags)
assert acl.returncode == 0
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
report = json.loads((b / 'f03-protected-build-r3/result.json').read_bytes())
assert report['source_commit'] == '1fe8e4b219714688c0bed061a3162628c5dd1cbe'
package = Path(report['output'])
original = Path(r'G:\PR13Evidence\private\season-balance-20261102-f03-protected-r3\publish')
for name, values in report['assemblies'].items():
    assert sha(package / name) == values['protected_sha256']
    assert sha(original / name) == values['original_sha256']
spec = importlib.util.spec_from_file_location('guard', repo / 'client/tests/fixture_runtime.py')
guard = importlib.util.module_from_spec(spec); spec.loader.exec_module(guard)
env = {key: value for key, value in os.environ.items() if not key.startswith('FANTASYCARD_')}
env.update(DOTNET_CLI_TELEMETRY_OPTOUT='1', DOTNET_NOLOGO='1', DOTNET_CLI_UI_LANGUAGE='en')
surface = b / 'f03-public-surface-r1/build/bin/PublicSurface/debug/PublicSurface.dll'
assert surface.is_file()
pins = {str(surface): sha(surface)}
for name in report['assemblies']:
    pins[str(package / name)] = sha(package / name)
    pins[str(original / name)] = sha(original / name)
for mode, directory in [('original', original), ('protected', package)]:
    run = guard.guarded_run(['dotnet', str(surface), str(directory), str(out / (mode + '-surface.original.json'))], env=env, timeout=60, wait_seconds=30)
    (out / (mode + '-surface.original.log')).write_text(run.stdout + run.stderr, encoding='utf-8')
    assert run.returncode == 0
before = json.loads((out / 'original-surface.original.json').read_bytes())
after = json.loads((out / 'protected-surface.original.json').read_bytes())
assert before['signatures'] == after['signatures'] and before['hash'] == after['hash']

inputs = b / 'f03-protected-snapshot-r4/inputs.original.json'
snapshot_rows = json.loads(inputs.read_bytes()); assert len(snapshot_rows) == 50
assert all(sha(Path(row['path'])) == row['sha256'] for row in snapshot_rows)
snapshot_pins = {r['path']: sha(Path(r['path'])) for r in snapshot_rows}
(out / 'snapshot-inputs.original.json').write_bytes(inputs.read_bytes())
results = {}
for mode, directory in [('original', original), ('protected', package)]:
    cached = Path(r'G:\PR13Evidence\private\season-balance-20261102-f03-google-r1\f03-snapshot-probe-r4') / mode / 'bin/Release/net10.0'
    target = private / mode; shutil.copytree(cached, target)
    for name in ['FantasyCard.Contracts.dll', 'FantasyCard.Domain.dll', 'Google.Protobuf.dll']:
        shutil.copyfile(directory / name, target / name)
        assert sha(target / name) == sha(directory / name)
    pins[str(target / 'Probe.dll')] = sha(target / 'Probe.dll')
    run = guard.guarded_run(['dotnet', str(target / 'Probe.dll'), str(out / 'snapshot-inputs.original.json'), str(out / (mode + '-snapshots.original.json'))], env=env, timeout=60, wait_seconds=30)
    (out / (mode + '-snapshots.original.log')).write_text(run.stdout + run.stderr, encoding='utf-8')
    proof = json.loads((out / (mode + '-snapshots.original.json')).read_bytes())
    assert run.returncode == 0 and proof['ok'] and proof['count'] == 50 and not proof['errors']
    for name in ['FantasyCard.Contracts.dll', 'FantasyCard.Domain.dll']:
        assert proof['assemblies'][name] == sha(directory / name)
    results[mode] = proof
left = {r['id']: r for r in results['original']['results']}
right = {r['id']: r for r in results['protected']['results']}
assert left.keys() == right.keys() and all(left[key]['canonical_sha256'] == right[key]['canonical_sha256'] for key in left)
assert all(sha(Path(name)) == expected for name, expected in pins.items())
assert all(sha(Path(name)) == expected for name, expected in snapshot_pins.items())
assert (package / 'CANDIDATE-NOT-YET-VALIDATED.txt').is_file()
summary = dict(source_commit=report['source_commit'], public_surface_equal=True, surface_signatures=len(before['signatures']), surface_hash=before['hash'],
    original_snapshot_semantic_passed=50, protected_snapshot_semantic_passed=50, snapshot_canonical_results_equal=True,
    snapshot_oracle='Only terminal bot timer normalization as previously source-verified; all other data deep-equal; no clock advance',
    exact_new_protected_DLLs_used=True, all_inputs_unchanged=True, new_gameplay_starts=0, PG_started=False, production_changed=False,
    candidate_marker_retained=True, full_certificate_written=False)
(out / 'result.json').write_text(json.dumps(summary, indent=2) + '\n')
print(json.dumps(summary))
