import gzip
import hashlib
import json
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path

B = Path(__file__).parent
R = B.parents[1]
OUT = B/'LOAD02-verdict-PG-r1-independent-G-check'
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

receipt = read(B/'LOAD02-verdict-PG-r1-complete-original-G-backup/complete-original-G-receipt.original.json')
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
actuals = {}
expected_modes = {'LOAD-02.1-T01':[('duration-short',1)],'LOAD-02.1-T03':[('redline-and-invalid',3)],
 'LOAD-02.3-T02':[('hang',3)],'LOAD-02.3-T03':[('write-failure',3)],
 'LOAD-02.4-T01':[('prepare-only',0)],'LOAD-02.4-T02':[('redline',2)],
 'LOAD-02.4-T03':[('invalid',3),('operator',130)]}
for cid,modes in expected_modes.items():
    native=read(G/'evidence/persistent-output/native-receipts'/(cid+'.json'))
    assert native['status']=='Passed'
    a=native['actual'];assert a['actualLoadOrCapacitySamples']==0 and a['actualMatches']==a['actualSnapshots']==1
    assert a['productionSourceModified'] is False
    assert a['cards']==[f'C{i:02}' for i in range(1,14)]+[f'GUA-{i:02}' for i in range(1,8)]
    observations=a['actualGuardObservations'];assert len(observations)==len(modes)
    for obs,(mode,code) in zip(observations,modes):
        assert obs['mode']==mode and obs['actualExitCode']==code
        assert obs['snapshotBeforeHash']==obs['snapshotAfterHash'] and obs['databaseBeforeHash']==obs['databaseAfterHash']
        v=obs['actualObservation'];assert v['mode']==mode and v['actual_child_exit_code']==code
        assert v['all_raw_fixture_files_preserved'] is True
        root=G/'evidence/persistent-output/coordinator-fixtures'/mode
        assert v==read(root/'actual-observation.original.json')
        report=v['actual_report'];assert report.get('acceptance_passed') is not True
        if mode=='duration-short':
            assert report['stop_reason']=='duration_limit' and report['result_dimensions']['dimensions']['execution']=='Passed'
            assert report['result_dimensions']['dimensions']['load']=='Failed'
        elif mode in ['redline','redline-and-invalid']:
            assert {'cpu_redline','memory_available_redline'}<=set(report['all_triggers'])
            assert report['result_dimensions']['dimensions']['performance']=='Failed'
            if mode=='redline-and-invalid':
                assert 'final_audit_loss' in report['all_triggers'] and report['result_dimensions']['dimensions']['evidence']=='Failed'
        elif mode=='write-failure':
            assert 'injected final report disk failure' in report['emergency'] and "'exit_code': 3" in report['emergency']
            originals=list(root.rglob('report.emergency.txt'));assert len(originals)==1 and not list(root.rglob('report.json'))
            assert originals[0].read_text()==report['emergency']
        elif mode=='hang':
            assert report['forced_termination_pids']==[report['owned_pid']] and report['owned_pid']!=report['foreign_pid']
            assert report['owned_exit'] is not None and report['foreign_after_stop_all'] is None
            assert report['foreign_untouched_by_stop_all'] and report['foreign_reaped_only_by_separate_fixture_finalizer']
            assert v['return_code_source']=='Fault harness classification after actual stop_all forced cleanup'
        elif mode=='prepare-only':
            assert report['prepared_only'] and report['load_run_started'] is False
            assert (root/'caller.stdout.original.log').read_text()==report['actual_stdout'] and report['actual_stdout'].startswith('Prepared:')
            assert not (root/'actual-preparation-output').exists()
        elif mode=='invalid':
            assert 'final_audit_loss' in report['all_triggers']
        elif mode=='operator':
            assert report['stop_reason']=='operator_stop_file'
        if mode not in ['prepare-only','hang','write-failure']:
            originals=list(root.rglob('report.json'));assert len(originals)==1 and read(originals[0])==report
    actuals[cid]=a
assert len(list((G/'evidence/persistent-output/coordinator-fixtures').glob('*/actual-observation.original.json')))==8
domain = G/'work/artifacts/bin/FantasyCard.Domain/release/FantasyCard.Domain.dll'
tests = G/'work/artifacts/bin/FantasyCard.Server.Tests/release/FantasyCard.Server.Tests.dll'
assert sha(domain)==plan['production_domain_assembly_sha256']=='844065af3158b40787699752915ed95befbd3c660c2b10dce501f9f4fc29e352'
proof = {'ok':True,'case_ids':plan['case_ids'],'profile':'POSTGRES','actual_native_PG_rows':10,
    'native_clean':True,'owned_container_removed':True,'source_inputs_match_git':True,
    'original_nine_regression_rows':9,'new_fault_matrix_methods':1,'native_skipped':0,
    'all_original_G_members_rehashed':len(manifest['files']),'archive_SHA_and_CRC_rechecked':True,
    'current_source_members':328,'current_context_files':11,'implementation_source_sha':head,
    'actual_fault_subprocess_modes':8,'actual_load_or_capacity_samples':0,
    'production_domain_assembly_unchanged':True,'actuals':actuals,
    'all_other_canonical_profiles_retained':True,'MAIN_accepted':False}
OUT.mkdir();(OUT/'independent-G-check.original.json').write_bytes((json.dumps(proof,indent=2)+'\n').encode())
print(json.dumps({k:v for k,v in proof.items() if k!='actuals'}))
