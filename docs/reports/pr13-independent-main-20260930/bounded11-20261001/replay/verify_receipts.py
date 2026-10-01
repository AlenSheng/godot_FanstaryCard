"""Read-only independent source, receipt and canonical metadata audit."""
import hashlib,json,pathlib,subprocess
B=pathlib.Path(__file__).resolve().parent
REPO=pathlib.Path('/workspace/godot_FanstaryCard')
SEAL=pathlib.Path('/workspace/pr13-main-bounded-seal')
plan_path=SEAL/'docs/plans/PR13_ACCEPTANCE_DETAILS_20260930.json'
plan=json.loads(plan_path.read_text())
contract={t['id']:t for p in plan['packages'] for t in p['subtasks']}
groups=json.loads((B/'PACKETS.json').read_text())
fields=plan['evidence_contract']['report_fields']
results=[]
def check(path,entry):
    data=path.read_bytes()
    if 'bytes' in entry:
        assert len(data)==entry['bytes'], str(path)+' size'
    assert hashlib.sha256(data).hexdigest()==entry['sha256'], str(path)+' hash'
for g in groups:
    p=pathlib.Path(g['packet']);manifest=json.loads((p/'MANIFEST.json').read_text())
    records=manifest['files'];verified=0
    for entry in records:
        rel=entry['path'];dest=p/rel
        if rel.startswith('evidence/'):
            dest=p/'evidence-original'/rel
        if g['group']=='B02' and rel.startswith('fixtures/'):
            dest=p/'evidence-original'/rel
        # Historical harness must remain exact; generated outputs excluded by packet manifest.
        check(dest,entry);verified+=1
    reports=list((p/'evidence-original/evidence').glob('*/ROOT_REPORT.json')) if g['group']!='A05' else list((p/'tasks').glob('*/ROOT_REPORT.json'))
    task_checks=[]
    for f in reports:
        d=json.loads(f.read_text());tid=d['task_id']
        if tid in ['LOAD-02.2','PR13-A05.1']:continue
        c=contract[tid]
        assert d['integration_sha']==g['source_sha'],tid
        assert d['case_ids']==[x['id'] for x in c['test_cases']],tid+' cases'
        rows=[d,*d['stage_receipts']]
        for row in rows:
            assert not set(fields)-set(row), (tid,row.get('stage'),set(fields)-set(row))
            assert row['profile_hash'] and row['algorithm_version'],tid+' metadata'
            for field in fields:
                if row[field] is None:
                    assert field in row['missing_reasons'],(tid,row.get('stage'),field)
        task_checks.append(dict(task_id=tid,report=str(f.relative_to(p)),rows_checked=len(rows),profile_hash=d['profile_hash'],algorithm_version=d['algorithm_version'],minimum_dependencies=c['requires_before_integration'],canonical_cases=c['test_cases'],profiles=c['profiles'],runtime_stage=c['runtime_stage'],missing_reasons=d['missing_reasons']))
    if g['group']=='LOAD03.1/.2':
        source=json.loads((p/'evidence-original/evidence/SOURCE_PROOF.json').read_text())
        for entry in source['files']:
            if entry['path'].startswith('fixture/'):
                src=p/'source/client'/entry['path'][len('fixture/'):]
            elif entry['path'].startswith('source/'):
                src=p/entry['path']
            else:continue
            check(src,entry)
    results.append(dict(group=g['group'],source_sha=g['source_sha'],report_commit=g['report_commit'],manifest_path='MANIFEST.json',manifest_sha256=hashlib.sha256((p/'MANIFEST.json').read_bytes()).hexdigest(),manifest_files_verified=verified,tasks=task_checks))
result=dict(canonical_plan_sha256=hashlib.sha256(plan_path.read_bytes()).hexdigest(),groups=results,status='Passed',scope='11 Ready only; LOAD01 and four Partial tasks excluded')
(B/'STATIC_CHECK.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
print(json.dumps(dict(status=result['status'],groups=[dict(group=g['group'],manifest_files_verified=g['manifest_files_verified'],tasks=len(g['tasks'])) for g in results]),ensure_ascii=False))
