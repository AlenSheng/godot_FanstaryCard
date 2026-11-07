from pathlib import Path
import collections, datetime, hashlib, json, xml.etree.ElementTree as ET

b=Path(__file__).parent;out=b/'f03-approved-protection-scope-r1';assert not out.exists();out.mkdir()
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
decision=dict(schema_version=1,question_id='call_46151f4602a14b0a8c7b1844dcabf721',question_item=0,
    user_answer='按本轮具名范围验收，明确保留79项未执行限制',
    applies_to='Fixed1fe8 protected-package acceptance scope only; no new numerical budget or production authorization',
    source_commit='1fe8e4b219714688c0bed061a3162628c5dd1cbe',recorded_at_utc=datetime.datetime.now(datetime.timezone.utc).isoformat())
(out/'decision.original.json').write_text(json.dumps(decision,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
report_path=b/'f03-protected-build-r3/result.json';report=json.loads(report_path.read_bytes());package=Path(report['output'])
assert report['source_commit']==decision['source_commit']
assert len(report['package_files'])==18
assert {p.name for p in package.iterdir() if p.is_file()}==set(report['package_files'])
for name,value in report['package_files'].items():
    p=package/name;assert p.stat().st_size==value['size'] and sha(p)==value['sha256']
plan_path=b/'f03-fixed-ordinary-r1/plan.original.json';plan=json.loads(plan_path.read_bytes())
selected={(r['type'],r['method']) for r in plan['selected_methods']}
excluded={(r['type'],r['method']) for r in plan['excluded_methods']}
assert len(selected)==1139 and len(excluded)==79 and not selected&excluded
inventory_path=b/'f03-fixed-inventory-r1/inventory.original.json';inventory=json.loads(inventory_path.read_bytes())
all_methods={(r['type'],r['method']) for r in inventory['rows']}
assert len(all_methods)==1218 and selected|excluded==all_methods
assert plan['source_commit']==report['source_commit']
for name,value in plan['all_input_pins'].items():assert sha(Path(name))==value,name
for name,value in report['assemblies'].items():assert sha(package/name)==value['protected_sha256']
totals={key:0 for key in ['total','passed','failed','notExecuted']};seen=set();evidence=[];per_assembly=collections.Counter()
for trx in sorted((b/'f03-fixed-ordinary-r1').rglob('*.trx')):
    root=ET.parse(trx);counts=root.find('.//{*}Counters');assert counts is not None
    for key in totals:totals[key]+=int(counts.get(key,'0'))
    for result in root.findall('.//{*}UnitTestResult'):assert result.get('outcome')=='Passed'
    for unit in root.findall('.//{*}UnitTest'):
        method=unit.find('{*}TestMethod');assert method is not None
        key=(method.get('className','').split(',')[0],method.get('name',''));assert key in selected;seen.add(key)
    run=json.loads((trx.parent/'result.json').read_bytes());assert run['ok'] and run['own_test_job_closed']
    per_assembly[run['assembly']]+=run['tests']['passed']
    evidence.append(dict(path=str(trx),sha256=sha(trx),kind='actual protected TRX'))
assert seen==selected and totals==dict(total=1867,passed=1867,failed=0,notExecuted=0)
assert dict(per_assembly)=={'FantasyCard.Domain.Tests.dll':759,'FantasyCard.Server.Tests.dll':1108}
ordinary_path=b/'f03-fixed-ordinary-r1/result.json';ordinary=json.loads(ordinary_path.read_bytes())
assert ordinary['ok'] and ordinary['own_PG_stopped'] and ordinary['own_job_closed']
probe_root=b/'f03-fixed-probes-r1';probes=json.loads((probe_root/'result.json').read_bytes())
before=json.loads((probe_root/'original-surface.original.json').read_bytes());after=json.loads((probe_root/'protected-surface.original.json').read_bytes())
assert before['signatures']==after['signatures'] and len(before['signatures'])==21128
assert hashlib.sha256('\n'.join(before['signatures']).encode()).hexdigest()==before['hash']==after['hash']==probes['surface_hash']
snapshots={mode:json.loads((probe_root/(mode+'-snapshots.original.json')).read_bytes()) for mode in ['original','protected']}
for mode,proof in snapshots.items():
    assert proof['ok'] and proof['count']==50 and not proof['errors']
    for name in ['FantasyCard.Domain.dll','FantasyCard.Contracts.dll']:
        assert proof['assemblies'][name]==report['assemblies'][name]['original_sha256' if mode=='original' else 'protected_sha256']
left={r['id']:r['canonical_sha256'] for r in snapshots['original']['results']};right={r['id']:r['canonical_sha256'] for r in snapshots['protected']['results']};assert left==right and len(left)==50
cloud_root=b/'f03-fixed-app-cloud-resume-r1';cloud=json.loads((cloud_root/'result.json').read_bytes());http=json.loads((cloud_root/'public/http-probe.original.json').read_bytes());cleanup=json.loads((cloud_root/'public/cleanup.original.json').read_bytes())
assert cloud['ok'] and cloud['source_commit']==report['source_commit'] and cloud['upload_tmpfs_unmounted']
assert sha(cloud_root/'public-evidence.original.tar.gz')==cloud['archive_sha256']
assert len(http['checks'])==14 and all(r['passed'] and r['status']==r['expected'] for r in http['checks'])
cloud_manifest=json.loads((cloud_root/'public/input-manifest.original.json').read_bytes())
assert cloud_manifest['compiled_source']==report['source_commit']
assert cloud_manifest['payload_files']=={name:value['sha256'] for name,value in report['package_files'].items()}
assert cleanup['production_state_unchanged'] and cleanup['owned_schema_removed'] and cleanup['private_env_removed'] and cleanup['owned_candidate_image_removed']
assert len(cleanup['owned_containers_removed'])==6
for p,kind in [(report_path,'original fixed export'),(plan_path,'selected/excluded complete partition'),(inventory_path,'PE inventory'),(ordinary_path,'ordinary terminal'),
    (probe_root/'result.json','surface/snapshot terminal'),(cloud_root/'result.json','cloud terminal'),(cloud_root/'public/http-probe.original.json','HTTP14'),
    (cloud_root/'public/cleanup.original.json','cloud cleanup'),(b/'f03-fixed-app-upload-cleanup-r1/result.original.json','verified orphan cleanup')]:
    evidence.append(dict(path=str(p),sha256=sha(p),kind=kind))
limitations=[dict(type=r['type'],method=r['method'],gate=r['gate'],reason=r['reason'],current_fixed_package_executed=False,
    acceptance_status='Excluded under explicit user-approved scope; not counted as passed',historical_results_and_gaps_retained=True) for r in plan['excluded_methods']]
(out/'excluded79.derived.json').write_text(json.dumps(limitations,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
certificate=dict(schema_version=1,ok=True,status='AcceptedWithinExplicitUserNamedScope',source_commit=report['source_commit'],package=str(package),
    decision_sha256=sha(out/'decision.original.json'),package_files=report['package_files'],assemblies=report['assemblies'],ordinary_tests=totals,
    ordinary_method_definitions=1139,excluded_method_definitions=79,all_method_definitions=1218,excluded_methods_sha256=sha(out/'excluded79.derived.json'),
    whole_suite_all_methods_passed=False,excluded_methods_counted_as_passed=False,public_surface_records=21128,public_surface_hash=before['hash'],
    snapshot_original_passed=50,snapshot_protected_passed=50,snapshot_results_equal=True,cloud_HTTP_passed=14,cloud_cleanup_complete=True,
    evidence=evidence,no_new_tests_or_gameplay=True,original_failures_and_gaps_retained=True,
    protection_subgate_accepted=True,whole_F03_accepted=False,production_deployment_authorized=False,
    remaining_release_gate='D03 actual308/308; proposed317 nine paired routes not yet approved; formal promotion/backup/deployment/restart/public verification pending',
    original_package_and_marker_unchanged=True,accepted_at_utc=datetime.datetime.now(datetime.timezone.utc).isoformat())
(out/'protection-scope-verification.json').write_text(json.dumps(certificate,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
assert (package/'CANDIDATE-NOT-YET-VALIDATED.txt').is_file()
assert all(sha(package/name)==value['sha256'] for name,value in report['package_files'].items())
print(json.dumps(dict(status=certificate['status'],ordinary_passed=1867,excluded_not_passed=79,certificate=str(out/'protection-scope-verification.json'),D03_budget_unchanged=True,production_changed=False)))
