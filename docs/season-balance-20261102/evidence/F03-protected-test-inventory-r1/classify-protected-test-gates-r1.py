from pathlib import Path
import collections,hashlib,json,re

b=Path(__file__).parent;repo=Path.cwd();out=b/'f03-protected-test-inventory-r1';inventory=json.loads((out/'inventory.original.json').read_bytes());rows=inventory['rows']
protected=json.loads((b/'f03-protected-build-r2/result.json').read_bytes());expected={Path(p).name:hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in protected['test_assemblies']}
assert all(expected[r['assembly']]==r['assembly_sha256'] and r['error'] is None for r in rows)
manual_properties={'Enabled','MatrixEnabled','FinalNineEnabled','CandidateEnabled','ReuseEnabled'}
groups=collections.defaultdict(list)
for row in rows:
    gate=row['named'].get('SkipUnless')
    group='explicit_manual_or_budget_gate' if gate in manual_properties else 'database_or_owned_fixture_gate' if gate else 'no_attribute_gate'
    groups[group].append(dict(assembly=row['assembly'],type=row['type'],method=row['method'],SkipUnless=gate,Skip=row['named'].get('Skip')))
source_map=[]
for p in (repo/'server/tests').rglob('*.cs'):
    if any(x in p.parts for x in ['obj','bin']):continue
    data=p.read_text('utf-8-sig');names=re.findall(r'Environment\.GetEnvironmentVariable\("(FANTASYCARD_[A-Z0-9_]+)"\)',data)
    if names:source_map.append(dict(path=p.relative_to(repo).as_posix(),sha256=hashlib.sha256(p.read_bytes()).hexdigest(),environment_names=sorted(set(names))))
report=dict(scope='Metadata/read-only release verification eligibility, not test execution',method_definitions=len(rows),
    counts={k:len(v) for k,v in groups.items()},groups=groups,current_source_environment_map=source_map,
    current_source_is_newer_than_exported_test_suites=True,export_compiled_source=protected['source_commit'],product_sources_unchanged_since_export=True,
    old_validator_sets=['FANTASYCARD_TEST_POSTGRES','FANTASYCARD_E2E_SERVER_DLL'],
    default_full_validator_ready=False,
    reason='Existing full validator enables an isolated DB but does not authorize/enable the36 manual properties, therefore an all-existing/no-skip certificate cannot honestly be produced from its default environment. Do not enable sealed queues or suppress skipped results to make it green.',
    no_validator_or_release_gate_weakened=True,no_candidate_marker_removed=True,no_verification_certificate_written=True,
    required_before_promotion=['Resolve explicit owner-bounded selection/reuse policy versus full/no-skip gate.','Use tests corresponding to the final fixed export, rather than pretending075 test definitions include later fixtures.','Run the selected permitted protected tests and record all exclusions/actual skipped tests honestly.'],
    test_methods_invoked=0,attribute_instances_created=0,new_gameplay_starts=0,PG_started=False,production_changed=False)
(out/'eligibility-review.derived.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps({k:report[k] for k in ['method_definitions','counts','default_full_validator_ready','no_validator_or_release_gate_weakened','test_methods_invoked','new_gameplay_starts']}))
