from pathlib import Path
import hashlib, importlib.util, json, os, shutil, subprocess, xml.etree.ElementTree as ET

b = Path(__file__).parent; repo = Path.cwd()
out = b / 'f03-catalog-baseline-fix-r1'
private = Path(r'G:\PR13Evidence\private\season-balance-20261102-f03-google-r1\catalog-baseline-fix-r1')
assert not out.exists() and not private.exists()
out.mkdir(); private.mkdir()
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
package = Path(json.loads((b / 'f03-protected-build-r2/result.json').read_bytes())['output'])
source = repo / 'server/tests/FantasyCard.Domain.Tests/Configuration/GameConfigCatalogTests.cs'
assert 'Assert.Equal("season-v1-config-17", catalog.Version);' in source.read_text('utf-8')
shutil.copyfile(source, private / source.name)
(out / 'GameConfigCatalogTests.cs').write_bytes(source.read_bytes())
fixture_names = ['server/config/generated/fantasycard.config.version.txt',
                 'server/config/generated/fantasycard.config.bytes',
                 'client/data/generated/fantasycard.config.version.txt',
                 'client/data/generated/fantasycard.config.bytes', 'client/data/catalog.json']
fixture_pins = []
for name in fixture_names:
    p = repo / name; assert p.is_file(), name
    q = private / name; q.parent.mkdir(parents=True, exist_ok=True); shutil.copyfile(p, q)
    fixture_pins.append(dict(path=name, sha256=sha(p)))
project = ET.Element('Project', Sdk='Microsoft.NET.Sdk')
properties = ET.SubElement(project, 'PropertyGroup')
for name, value in dict(TargetFramework='net10.0', IsTestProject='true', ImplicitUsings='enable', Nullable='enable', UseAppHost='false', TreatWarningsAsErrors='true').items():
    ET.SubElement(properties, name).text = value
items = ET.SubElement(project, 'ItemGroup')
ET.SubElement(items, 'Using', Include='Xunit')
for name, version in [('Microsoft.NET.Test.Sdk', '17.14.1'), ('xunit.v3', '3.1.0'), ('xunit.runner.visualstudio', '3.1.0')]:
    ET.SubElement(items, 'PackageReference', Include=name, Version=version)
product_pins = {}
for name in ['FantasyCard.Domain', 'FantasyCard.Contracts', 'Google.Protobuf']:
    p = package / (name + '.dll'); product_pins[str(p)] = sha(p)
    reference = ET.SubElement(items, 'Reference', Include=name)
    ET.SubElement(reference, 'HintPath').text = str(p)
    ET.SubElement(reference, 'Private').text = 'true'
ET.SubElement(items, 'None', Update='xunit.runner.json', CopyToOutputDirectory='PreserveNewest')
ET.ElementTree(project).write(private / 'CatalogBaseline.csproj', encoding='utf-8', xml_declaration=True)
(private / 'xunit.runner.json').write_text(json.dumps(dict(maxParallelThreads=1, parallelizeAssembly=False, parallelizeTestCollections=False)) + '\n')
(out / 'inputs.original.json').write_text(json.dumps(dict(source_sha256=sha(source), protected_runtime_inputs=product_pins, fixture_pins=fixture_pins, scope='Current original catalog test source against unchanged protected runtime DLLs; no new gameplay'), indent=2) + '\n')
spec = importlib.util.spec_from_file_location('guard', repo / 'client/tests/fixture_runtime.py')
guard = importlib.util.module_from_spec(spec); spec.loader.exec_module(guard)
env = {k: v for k, v in os.environ.items() if not k.startswith('FANTASYCARD_')}
env.update(DOTNET_CLI_TELEMETRY_OPTOUT='1', DOTNET_NOLOGO='1', DOTNET_CLI_UI_LANGUAGE='en')
build = guard.guarded_run(['dotnet', 'build', str(private / 'CatalogBaseline.csproj'), '-c', 'Release', '-m:1', '-p:UseSharedCompilation=false', '--verbosity', 'minimal'], env=env, timeout=180, wait_seconds=30)
(out / 'build.original.log').write_text(build.stdout + build.stderr, encoding='utf-8')
assert build.returncode == 0, (build.stdout + build.stderr)[-2000:]
assembly = private / 'bin/Release/net10.0/CatalogBaseline.dll'
for path, expected in product_pins.items():
    assert sha(assembly.parent / Path(path).name) == expected
run = guard.guarded_run(['dotnet', 'vstest', str(assembly), '--Logger:trx', '--ResultsDirectory:' + str(out)], env=env, timeout=60, wait_seconds=30)
(out / 'run.original.log').write_text(run.stdout + run.stderr, encoding='utf-8')
trx = next(out.glob('*.trx')); counters = ET.parse(trx).find('.//{*}Counters')
totals = {key: int(counters.get(key, '0')) for key in ['total', 'passed', 'failed', 'notExecuted']}
assert run.returncode == 0 and totals == dict(total=4, passed=4, failed=0, notExecuted=0), totals
assert sha(source) == sha(private / source.name)
assert all(sha(Path(path)) == value for path, value in product_pins.items())
assert all(sha(private / x['path']) == x['sha256'] for x in fixture_pins)
result = dict(ok=True, tests=totals, change='Stale literal expected config16 corrected to already-published config17; no product change',
              source_sha256=sha(source), protected_runtime_hashes_unchanged=True, original_failure_retained=True,
              new_gameplay_starts=0, PG_started=False, production_changed=False, full_suite_certificate=False)
(out / 'result.json').write_text(json.dumps(result, indent=2) + '\n'); print(json.dumps(result))
