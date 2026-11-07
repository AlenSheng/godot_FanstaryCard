from pathlib import Path

b = Path(__file__).parent
target = b / 'run-f03-fixed-ordinary-r1.py'
assert not target.exists()
old = (b / 'run-protected-ordinary-r4.py').read_text('utf-8')
tail = old[old.index('class Memory(ctypes.Structure):'):]
tail = tail.replace("temp = private / 'temp'; temp.mkdir()", 'temp = short_temp')
tail = tail.replace("        if domain:\n            continue\n", '')
tail = tail.replace("selected_method_definitions=631, prior_completed_method_definitions=80", "selected_method_definitions=1139, prior_completed_method_definitions=0")
tail = tail.replace('excluded_method_definitions=59', 'excluded_method_definitions=79')
tail = tail.replace("    env = ", "    env = ")
needle = "            print(json.dumps(summary), flush=True)\n            if not ok:"
replacement = """            print(json.dumps(summary), flush=True)
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
                (target / 'generated-sample-manifest.json').write_text(json.dumps(sample_rows, indent=2) + '\\n')
            if not ok:"""
assert needle in tail
tail = tail.replace(needle, replacement)
top = r'''from pathlib import Path
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

'''
target.write_text(top + tail, encoding='utf-8')
print(target)
