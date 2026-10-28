import gzip
import hashlib
import json
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path

B = Path(__file__).parent
R = B.parents[1]
OUT = B/'A07-gate-faults-PG-r1-independent-G-check'
assert not OUT.exists()

def sha(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for data in iter(lambda:stream.read(1024**2),b''):
            h.update(data)
    return h.hexdigest()

def read(path):
    return json.loads(path.read_bytes())

def git(*args):
    return subprocess.check_output(['git','-c','core.longpaths=true',*args],cwd=R)

receipt = read(B/'A07-gate-faults-PG-r1-complete-original-G-backup/complete-original-G-receipt.original.json')
G = Path(receipt['local_directory'])
archive = Path(receipt['local_archive'])
assert receipt['ok'] and receipt['all_original_members_SHA_verified'] and receipt['archive_gzip_CRC_verified']
assert archive.stat().st_size==receipt['archive_bytes'] and sha(archive)==receipt['archive_sha256']
with gzip.open(archive,'rb') as stream:
    while stream.read(1024**2):
        pass
assert sha(G/'complete-original-manifest.json')==receipt['manifest_sha256']
manifest = read(G/'complete-original-manifest.json')
assert len(manifest['files'])==receipt['original_members'] and receipt['original_members']>=600
for row in manifest['files']:
    p = G/row['path']
    assert p.stat().st_size==row['bytes'] and sha(p)==row['sha256']
plan = read(G/'work/control/plan.original.json')
head = git('rev-parse','HEAD').decode().strip()
for row in plan['source_files']:
    raw = git('show',head+':'+row['path'])
    assert len(raw)==row['bytes'] and hashlib.sha256(raw).hexdigest()==row['sha256']
    p = G/'work/source'/row['path']
    if row['path']==plan['source_override_path']:
        addition = (G/'work/control/addition.original.cs').read_bytes()
        index = raw.rfind(b'}')
        assert p.read_bytes()==raw[:index]+addition+raw[index:]
    else:
        assert sha(p)==row['sha256']
assert len(plan['source_files'])==328
for row in plan['work_files']:
    if row['path'].startswith('context/'):
        assert (G/'work/control'/row['path']).read_bytes()==git('show',head+':'+row['path'][8:])
assert (G/'work/control/pr13_suite_coverage.py').read_bytes()==git('show',head+':tools/pr13_suite_coverage.py')
for row in plan['work_files']:
    p = G/'work/control'/row['path']
    assert p.stat().st_size==row['bytes'] and sha(p)==row['sha256']
for row in plan['config_files']:
    raw = git('show',head+':'+row['path'])
    assert len(raw)==row['bytes'] and hashlib.sha256(raw).hexdigest()==row['sha256']
result = read(G/'evidence/result.original.json')
assert result['ok'] and result['exit_code']==0 and not result['oom_killed']
assert result['owned_containers_removed'] and result['private_environment_removed_after_owned_containers_ended']
assert result['remaining_owned_fixture_schemas']==0 and result['original_shared_and_controlled_inputs_unchanged']
terminal = read(G/'evidence/terminal-state.original.json')
assert terminal['MainPID']=='0' and terminal['ActiveState']=='inactive' and terminal['ExecMainStatus']=='0'
tree = ET.parse(G/'evidence/persistent-output/results/native-ten.original.trx')
counts = {k:int(v) for k,v in tree.find('.//{*}Counters').attrib.items()}
assert counts['total']==counts['executed']==counts['passed']==10 and counts['failed']==counts['notExecuted']==0
assert {n.find('{*}TestMethod').attrib['name'] for n in tree.findall('.//{*}UnitTest')}==set(plan['required_native_methods'])
assert all(n.attrib['outcome']=='Passed' for n in tree.findall('.//{*}UnitTestResult'))
actuals={}
expected_modes={'PR13-A07.4-T01':'load-passed-numerical-failed','PR13-A07.4-T02':'baseline-compile-failed'}
parent=G/'work/source';testpath=plan['source_override_path'];parentdata=(parent/testpath).read_bytes()
for cid,mode in expected_modes.items():
    native=read(G/'evidence/persistent-output/native-receipts'/(cid+'.json'));assert native['status']=='Passed'
    a=native['actual'];assert a['snapshotBeforeHash']==a['snapshotAfterHash'] and a['databaseBeforeHash']==a['databaseAfterHash']
    assert a['actualMatches']==a['actualSnapshots']==1 and a['productionSourceModified'] is False
    assert a['faultedSourcesAreOwnedDeclaredTestCopies'] is True and a['fullMAINAcceptance'] is False
    v=a['actualGateGuard'];assert v['ok'] and v['mode']==mode and v['full_MAIN_gate_was_not_accepted'] and v['faulted_source_copies_never_deployed']
    root=G/'evidence/persistent-output/gate-controls'/mode
    assert read(root/'actual-observation.original.json')==v
    ob=v['actual_observation'];gate=ob['actual_gate'];assert gate['acceptance'] is False
    phases=v['actual_phases'];assert all(p['actual_exit_code']==p['expected_exit_code'] for p in phases)
    if mode=='load-passed-numerical-failed':
        assert ob['actual_load_exit']==0 and ob['actual_numerical_exit']==1
        assert gate['state']=='Failed' and gate['failed_suites']==['PostgresNumerical']
        counts=ob['actual_numerical_coverage']['counters'];assert counts['total']==counts['executed']==counts['failed']==1 and counts['passed']==counts['notExecuted']==0
        assert '47' in ob['actual_assertion_failure'] and '46' in ob['actual_assertion_failure']
        log=(root/'actual-dedicated-load-python.stderr.original.log').read_text()
        assert '\nOK\n' in log and 'Ran 103 tests' in log
        source=G/'work/control/numerical-failure-source'
        old=b'(3, 46), (4, 72), (5, 113)';new=b'(3, 47), (4, 72), (5, 113)'
        assert (source/testpath).read_bytes()==parentdata.replace(old,new)
        witness=ob['controlled_test_expectation_change']
        assert witness['before_sha256']==sha(parent/testpath) and witness['after_sha256']==sha(source/testpath)
        negative=ET.parse(root/'native/actual.original.trx')
        ncounts={k:int(v) for k,v in negative.find('.//{*}Counters').attrib.items()};assert ncounts==counts
        assert all(r.attrib['outcome']=='Failed' for r in negative.findall('.//{*}UnitTestResult'))
        methods={r.find('{*}TestMethod').attrib['name'] for r in negative.findall('.//{*}UnitTest')}
        assert methods=={'Exact_GDD_fire_contexts_restore_from_database_to_46_72_113'}
        artifact=G/'work/artifacts/numerical-failure/bin/FantasyCard.Domain/release/FantasyCard.Domain.dll'
        assert sha(artifact)==ob['fault_child_domain_assembly_sha256']
    else:
        assert ob['actual_full_server_test_project_compile_exit']==1 and gate['state']=='Blocked' and gate['baseline_compile_exit']==1
        assert all(gate[k]==[] for k in ['missing_suites','stale_source_suites','failed_suites','incomplete_suites'])
        assert ob['positive_original_source_gate']['state']=='ReadyForMainReview' and ob['positive_original_source_gate']['acceptance'] is False
        log=(root/'actual-full-server-tests-baseline-build.stdout.original.log').read_text()
        assert 'CS1029' in log and 'PR13_DECLARED_BASELINE_COMPILATION_FAILURE' in log
        source=G/'work/control/baseline-compile-failure-source'
        prefix=b'#error PR13_DECLARED_BASELINE_COMPILATION_FAILURE\n'
        assert (source/testpath).read_bytes()==prefix+parentdata
        assert ob['original_parent_source_sha256']==sha(parent/testpath) and ob['faulted_baseline_source_sha256']==sha(source/testpath)
        positive=ET.parse(root/'original-nine/actual.original.trx')
        pc={k:int(v) for k,v in positive.find('.//{*}Counters').attrib.items()}
        assert pc['total']==pc['executed']==pc['passed']==9 and pc['failed']==pc['notExecuted']==0
        assert {r.find('{*}TestMethod').attrib['name'] for r in positive.findall('.//{*}UnitTest')}==set(plan['required_native_methods'][:-1])
    for row in plan['source_files']:
        if row['path']!=testpath:
            assert sha(source/row['path'])==sha(parent/row['path'])==row['sha256']
    actuals[cid]=a
domain = G/'work/artifacts/bin/FantasyCard.Domain/release/FantasyCard.Domain.dll'
tests = G/'work/artifacts/bin/FantasyCard.Server.Tests/release/FantasyCard.Server.Tests.dll'
assert sha(domain)==plan['production_domain_assembly_sha256']=='844065af3158b40787699752915ed95befbd3c660c2b10dce501f9f4fc29e352'
proof={'ok':True,'case_ids':plan['case_ids'],'profile':'POSTGRES','actual_outer_native_PG_rows':10,
    'native_clean':True,'owned_container_removed':True,'source_inputs_match_git':True,
    'original_nine_regression_rows':9,'new_gate_matrix_methods':1,'native_skipped':0,
    'actual_inner_positive_PG_rows':9,'actual_intentional_negative_numerical_rows':1,'dedicated_python_LOAD_tests_passed':103,
    'all_original_G_members_rehashed':len(manifest['files']),'archive_SHA_and_CRC_rechecked':True,
    'current_source_members':328,'implementation_source_sha':head,
    'full_Server_Tests_project_baseline_compile_failed_as_declared':True,
    'whole_solution_or_workflow_or_MAIN_acceptance_claimed':False,
    'production_domain_assembly_unchanged':True,'actuals':actuals,
    'all_other_canonical_profiles_retained':True,'MAIN_accepted':False}
OUT.mkdir();(OUT/'independent-G-check.original.json').write_bytes((json.dumps(proof,indent=2)+'\n').encode())
print(json.dumps({k:v for k,v in proof.items() if k!='actuals'}))
