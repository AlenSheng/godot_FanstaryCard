import hashlib,json,os,subprocess,sys,time
from pathlib import Path
SOURCE='3e45dd495215c3a0a5eda53a20449d9ad1e0d00d'
REPO=Path('/opt/fantasycard-github');B=Path('/home/ubuntu/pr13-acceptance-20261009');A='current-history-delivery-audit-r2-20261012';E=B/'evidence'/A;W=B/'work'/A
assert not E.exists() and not W.exists();E.mkdir();W.mkdir();started=time.time();inputs={}
def write(path,value):
 assert not path.exists();path.write_bytes((json.dumps(value,indent=2,ensure_ascii=False)+'\n').encode())
def frozen(name):
 raw=subprocess.check_output(['git','-C',str(REPO),'show',SOURCE+':'+name],timeout=30);oid=subprocess.check_output(['git','-C',str(REPO),'rev-parse',SOURCE+':'+name],text=True,timeout=30).strip();assert hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest()==oid;target=W/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(raw);inputs[name]={'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest(),'git_blob_sha1':oid};return raw
history='docs/reports/pr13-stages-20261009/S4-historical-inventory-audit/'
summary=json.loads(frozen(history+'summary.json'));manifest=json.loads(frozen(history+'manifest.json'))
selected={history+'summary.json'}
for row in manifest['files']:
 if row['path'].startswith('originals/frozen-inputs/local-inventory/'):
  name=history+row['path'];raw=frozen(name);assert len(raw)==row['bytes'] and hashlib.sha256(raw).hexdigest()==row['sha256'] and inputs[name]['git_blob_sha1']==row['git_blob_sha1'];selected.add(name)
assert len(selected)==3
inventory=[]
for name in sorted(selected-{history+'summary.json'}):
 value=json.loads((W/name).read_bytes());assert value['all_declared_members_classified'] and not value['all_raw_available_and_matching'];assert len(value['files'])==value['declared_members'] and value['counts']=={'Missing':value['declared_members']};assert all(row['state']=='Missing' and row['raw_read'] is False for row in value['files']);assert value['historical_totals_reconciled'] is False and value['missing_raw_cannot_be_replaced_by_newer_results'] is True;inventory.append({'path':name,'sha256':inputs[name]['sha256'],'declared_members':value['declared_members'],'counts':value['counts'],'original_manifest_sha256':value['manifest_sha256']})
assert sum(x['declared_members'] for x in inventory)==2144 and summary['original_raw_missing']==2144 and not summary['historical_totals_reconciled'] and not summary['missing_original_raw_recovered'] and summary['new_results_do_not_repair_original_history']
pointer=json.loads(frozen('docs/plans/PR13_CURRENT_ACCEPTANCE_POINTER_20261009.json'));regpath=pointer['current_register'];register=json.loads(frozen(regpath));delivery=json.loads(frozen('docs/plans/PR13_DELIVERY_DECISION_20261008.json'));contracts=json.loads(frozen('docs/plans/PR13_ACCEPTANCE_DETAILS_20260930.json'));contract={c['id']:c for pkg in contracts['packages'] for task in pkg['subtasks'] for c in task['test_cases']}
for name in ('tools/pr13_review_policy.py','tools/pr13_public_evidence.py'):frozen(name)
sys.path.insert(0,str(W));from tools.pr13_review_policy import history_claim
claim=history_claim(0,0,raw_reconciled=False);assert claim['comparison_state']=='Blocked' and not claim['runtime_revalidated'] and claim['current_passed']==0
unfinished=[t['task_id'] for t in register['tasks'] if t['state'] not in ('Accepted','NoChangeWithEvidence')];assert len(register['tasks'])==132 and len(unfinished)==118 and register['all_accepted'] is False;assert delivery['destination']=='origin/release' and delivery['draft_pr_updates'] is False and delivery['merge_release'] is True and delivery['local_summary_required'] is True
records=[{'case_id':'LOAD-11.1-T02','actual':{'actual_historical_inventory_members':2144,'actual_missing_inventory_rows':2144,'inventory_sources':inventory,'history_attribution':claim,'historical_source_raw_read':False,'new_TLS_or_RENDER_results_used_to_repair_old_history':False,'scope_limit':'Actual immutable historical inventory audit; this does not recheck a Windows drive from Linux or recover deleted 50/100 raw.'}}, {'case_id':'PR13-A08.4-T03','actual':{'current_register_path':regpath,'current_register_sha256':inputs[regpath]['sha256'],'actual_unaccepted_tasks':unfinished,'actual_missing_case_profiles_retained':True,'all_accepted':False,'delivery_decision_sha256':inputs['docs/plans/PR13_DELIVERY_DECISION_20261008.json']['sha256'],'user_authorized_direct_release_stage_summary':True,'draft_updates_waived_by_explicit_user_decision':True},'expected_override':'Explicit user delivery decision permits local stage summaries and direct release publication; the unfinished list and unaccepted verdict must remain.', 'override_source':{'path':'docs/plans/PR13_DELIVERY_DECISION_20261008.json','sha256':inputs['docs/plans/PR13_DELIVERY_DECISION_20261008.json']['sha256']}}]
for row in records:
 c=contract[row['case_id']];row.update(executed=True,status='Passed',source_sha=SOURCE,profiles_executed=['AUDIT'],setup=c['setup_and_injection'],expected=c['expected'],scope='Tencent process audits actual frozen Git inventory and current acceptance/delivery records. No database, historical recovery, capacity, or whole MAIN claim.')
for name,row in inputs.items():
 raw=(W/name).read_bytes();assert len(raw)==row['bytes'] and hashlib.sha256(raw).hexdigest()==row['sha256']
(E/'cases.original.jsonl').write_bytes((''.join(json.dumps(row,ensure_ascii=False)+'\n' for row in records)).encode());write(E/'input-ledger.original.json',inputs);write(E/'result.original.json',{'ok':True,'implementation_source_sha':SOURCE,'executed':2,'passed':2,'profiles_executed':['AUDIT'],'current_unaccepted_tasks':len(unfinished),'audited_missing_historical_members':2144,'original_Git_inputs_unchanged':True,'local_native_computation':False,'actual_cloud_PID':os.getpid(),'started_at':started,'completed_at':time.time(),'native_clean':True,'owned_container_removed':True,'owned_container_note':'No new container started; this bounded cloud Python process owns only its evidence/input directories.','source_inputs_match_git':True,'MAIN_accepted':False})
print(json.dumps({'ok':True,'case_ids':[x['case_id'] for x in records],'evidence_directory':str(E),'source_sha':SOURCE,'actual_cloud_PID':os.getpid(),'MAIN_accepted':False}))
