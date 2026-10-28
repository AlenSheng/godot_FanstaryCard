import hashlib
import json
import os
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
import pr13_suite_coverage

C=Path('/control');O=Path('/output/gate-controls');O.mkdir(exist_ok=True)
plan=json.loads((C/'plan.original.json').read_bytes())
mode=sys.argv[1];root=O/mode;root.mkdir(exist_ok=False)
project_rel='server/tests/FantasyCard.Server.Tests/FantasyCard.Server.Tests.csproj'
path=plan['source_override_path']
phases=[]
def command(label,args,expected,*,cwd='/work/server',env=None,timeout=480):
    with (root/(label+'.stdout.original.log')).open('xb') as stdout,(root/(label+'.stderr.original.log')).open('xb') as stderr:
        result=subprocess.run(args,cwd=cwd,env=env,stdout=stdout,stderr=stderr,timeout=timeout)
    phases.append({'label':label,'arguments':args,'actual_exit_code':result.returncode,'expected_exit_code':expected})
    assert result.returncode==expected,label+' unexpected exit'
    return result.returncode
def test_environment(folder):
    env=dict(os.environ)
    env['FANTASYCARD_PR13_NUMERICAL_EVIDENCE']=str(folder/'receipts')
    return env
def test_args(project,artifacts,selector,folder):
    return ['dotnet','test',str(project),'-c','Release','--no-build','--no-restore','--artifacts-path',str(artifacts),
        '--filter',selector,'--results-directory',str(folder),'--logger','trx;LogFileName=actual.original.trx']

if mode=='load-passed-numerical-failed':
    env=dict(os.environ,PYTHONPATH='/control/context:/control/context/tools')
    modules=['tools.tests.test_gameplay_load_validation','tools.tests.test_gameplay_load_finalization',
             'tools.tests.test_gameplay_load_stop','tools.tests.test_gameplay_load_sampling_contract']
    load_exit=command('actual-dedicated-load-python',['python3','-m','unittest','-v',*modules],0,
        cwd='/control/context',env=env,timeout=180)
    load_log=(root/'actual-dedicated-load-python.stderr.original.log').read_text()
    assert '\nOK\n' in load_log and 'Ran ' in load_log
    source=C/'numerical-failure-source';shutil.copytree('/work',source)
    original=(source/path).read_bytes()
    old=b'(3, 46), (4, 72), (5, 113)';new=b'(3, 47), (4, 72), (5, 113)'
    assert original.count(old)==1
    changed=original.replace(old,new)
    (source/path).write_bytes(changed)
    assert changed.replace(new,old)==original
    artifacts=Path('/artifacts/numerical-failure');project=source/project_rel
    command('negative-restore',['dotnet','restore',str(project),'--source','/packages','--artifacts-path',str(artifacts),
        '-p:RestorePackagesPath=/packages','-p:UseSharedCompilation=false','-maxcpucount:1'],0,cwd=str(source/'server'))
    command('negative-build',['dotnet','build',str(project),'-c','Release','--no-restore','--artifacts-path',str(artifacts),
        '-p:UseSharedCompilation=false','-maxcpucount:1'],0,cwd=str(source/'server'),timeout=600)
    name='Exact_GDD_fire_contexts_restore_from_database_to_46_72_113'
    selector='FullyQualifiedName=FantasyCard.Server.Tests.Persistence.PostgresNumericalContractTests.'+name
    native=root/'native';native.mkdir()
    numerical_exit=command('actual-numerical-failure',test_args(project,artifacts,selector,native),1,
        cwd=str(source/'server'),env=test_environment(native),timeout=180)
    coverage=pr13_suite_coverage.assess_trx(native/'actual.original.trx',{name:1})
    counts=coverage['counters'];assert counts['total']==counts['executed']==counts['failed']==1 and counts['passed']==counts['notExecuted']==0
    trx=ET.parse(native/'actual.original.trx')
    message=trx.find('.//{*}Message').text
    assert '47' in message and '46' in message
    suites={'DedicatedLoadPython':{'state':'CoveredForMainReview','source_sha':plan['source_base_sha'],
        'actual_exit_code':load_exit,'scope':'All current tests in four dedicated Python LOAD modules; no workflow, Godot, public load or capacity claim'},
        'PostgresNumerical':{**coverage,'source_sha':plan['source_base_sha']}}
    gate=pr13_suite_coverage.assess_gate(suites,list(suites),expected_source_sha=plan['source_base_sha'])
    assert gate['state']=='Failed' and gate['acceptance'] is False and gate['failed_suites']==['PostgresNumerical']
    observation={'actual_load_exit':load_exit,'actual_numerical_exit':numerical_exit,'actual_numerical_coverage':coverage,
        'actual_assertion_failure':message,'actual_gate':gate,'actual_suites':suites,
        'controlled_test_expectation_change':{'before':old.decode(),'after':new.decode(),
            'before_sha256':hashlib.sha256(original).hexdigest(),'after_sha256':hashlib.sha256(changed).hexdigest()},
        'production_domain_source_modified':False,'fault_child_domain_assembly_sha256':hashlib.sha256((artifacts/'bin/FantasyCard.Domain/release/FantasyCard.Domain.dll').read_bytes()).hexdigest()}
elif mode=='baseline-compile-failed':
    source=C/'baseline-compile-failure-source';shutil.copytree('/work',source)
    original=(source/path).read_bytes();prefix=b'#error PR13_DECLARED_BASELINE_COMPILATION_FAILURE\n'
    (source/path).write_bytes(prefix+original)
    artifacts=Path('/artifacts/baseline-compile-failure');project=source/project_rel
    command('baseline-restore',['dotnet','restore',str(project),'--source','/packages','--artifacts-path',str(artifacts),
        '-p:RestorePackagesPath=/packages','-p:UseSharedCompilation=false','-maxcpucount:1'],0,cwd=str(source/'server'))
    compile_exit=command('actual-full-server-tests-baseline-build',['dotnet','build',str(project),'-c','Release',
        '--no-restore','--artifacts-path',str(artifacts),'-p:UseSharedCompilation=false','-maxcpucount:1'],1,
        cwd=str(source/'server'),timeout=600)
    build_log=(root/'actual-full-server-tests-baseline-build.stdout.original.log').read_text()
    assert 'CS1029' in build_log and 'PR13_DECLARED_BASELINE_COMPILATION_FAILURE' in build_log
    native=root/'original-nine';native.mkdir()
    selector='FullyQualifiedName~PostgresNumericalContractTests&FullyQualifiedName!~Actual_failed_numerical_and_baseline_build_gates_preserve_postgres_room'
    command('actual-original-nine-positive',test_args(Path('/work')/project_rel,Path('/artifacts'),selector,native),0,
        env=test_environment(native),timeout=180)
    methods={name:1 for name in plan['required_native_methods'][:-1]}
    coverage=pr13_suite_coverage.assess_trx(native/'actual.original.trx',methods)
    assert coverage['state']=='CoveredForMainReview' and coverage['counters']['passed']==9
    suites={'PostgresNumerical':{**coverage,'source_sha':plan['source_base_sha']}}
    blocked=pr13_suite_coverage.assess_gate(suites,list(suites),expected_source_sha=plan['source_base_sha'],baseline_compile_exit=compile_exit)
    positive=pr13_suite_coverage.assess_gate(suites,list(suites),expected_source_sha=plan['source_base_sha'],baseline_compile_exit=0)
    assert blocked['state']=='Blocked' and blocked['baseline_compile_exit']==1 and blocked['acceptance'] is False
    assert positive['state']=='ReadyForMainReview' and positive['acceptance'] is False
    assert all(blocked[key]==[] for key in ['missing_suites','stale_source_suites','failed_suites','incomplete_suites'])
    observation={'actual_full_server_test_project_compile_exit':compile_exit,'actual_positive_original_PG_coverage':coverage,
        'actual_gate':blocked,'positive_original_source_gate':positive,
        'controlled_compile_fault_prefix':prefix.decode(),'original_parent_source_sha256':hashlib.sha256(original).hexdigest(),
        'faulted_baseline_source_sha256':hashlib.sha256(prefix+original).hexdigest(),
        'scope':'Full current Server.Tests project and referenced production projects; not the entire solution or an obsolete-API miniature probe. Positive nine run from original parent artifacts; faulty clone is separately recorded.'}
else:
    raise ValueError('Unknown frozen gate fault')
actual={'ok':True,'mode':mode,'actual_observation':observation,'actual_phases':phases,
    'full_MAIN_gate_was_not_accepted':True,'faulted_source_copies_never_deployed':True}
(root/'actual-observation.original.json').write_bytes((json.dumps(actual,indent=2)+'\n').encode())
print(json.dumps(actual))
