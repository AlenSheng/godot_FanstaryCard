import hashlib,json,os,subprocess,sys,urllib.request
from pathlib import Path
SOURCE='bfa7d7aa9a132e3515d443d0fdafc4f7186e7e86'
B=Path('/home/ubuntu/pr13-acceptance-20261009');A='current-default-deployment-six-audit-r1-20261012';E=B/'evidence'/A;W=B/'work'/A;REPO='/opt/fantasycard-github'
assert not E.exists() and not W.exists();E.mkdir();W.mkdir();inputs={};sys.dont_write_bytecode=True
def frozen(name):
 raw=subprocess.check_output(['git','-C',REPO,'show',SOURCE+':'+name],timeout=30);oid=subprocess.check_output(['git','-C',REPO,'rev-parse',SOURCE+':'+name],text=True).strip();assert hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest()==oid;p=W/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(raw);inputs[name]={'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest(),'git_blob_sha1':oid};return raw
def write(p,v):
 assert not p.exists();p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes((json.dumps(v,ensure_ascii=False,indent=2)+'\n').encode())
plan=json.loads(frozen('docs/plans/PR13_ACCEPTANCE_DETAILS_20260930.json'));pointer=json.loads(frozen('docs/plans/PR13_CURRENT_ACCEPTANCE_POINTER_20261009.json'));regpath=pointer['current_register'];register=json.loads(frozen(regpath))
for name in ('tools/pr13_review_policy.py','tools/pr13_public_evidence.py','tools/pr13_stages.py','client/data/catalog.json'):frozen(name)
sys.path.insert(0,str(W));from tools.pr13_review_policy import deployment_claim,candidate_matrix,asset_gate;from tools.pr13_stages import default_policy
with urllib.request.urlopen('http://127.0.0.1:8080/health/ready',timeout=10) as response:health=response.status
assert health==200 and register['all_accepted'] is False
actual_head=subprocess.check_output(['git','-C',REPO,'rev-parse','HEAD'],text=True).strip()
closed=deployment_claim(pr_closed=True);assert closed['code_review_closed'] and not closed['runtime_rollback_verified'] and closed['current_runtime_health']=='Unknown'
unobserved=deployment_claim();assert unobserved['current_runtime_health']=='Unknown' and not unobserved['runtime_rollback_verified']
policy=default_policy(W/'client/data/catalog.json');flags=('cards_spent_draw','fractional_guardian','optional_monster_pool','budgeted_bot_loot','mortal_bot_pve');assert all(policy[k] is False for k in flags)
negative=[]
for flag in flags:
 catalog=json.loads((W/'client/data/catalog.json').read_bytes());catalog['tables']['NumericalRules'][0][flag]=True;p=W/'controlled-negative-copies'/('on-'+flag+'.json');write(p,catalog);rejected=False;reason=''
 try:default_policy(p)
 except ValueError as error:reason=str(error);rejected='Formal numerical candidate defaults changed' in reason
 assert rejected;negative.append({'candidate_flag':flag,'controlled_on_catalog_path':str(p),'rejected':rejected,'actual_rejection':reason})
failed=candidate_matrix(False,{},list(flags));assert failed['state']=='Failed' and failed['reason']=='default_off_regression' and not failed['production_activation']
required=['cards_spent_draw','fractional_guardian','optional_monster_pool'];absent=candidate_matrix(True,{},required);assert absent['state']=='Blocked' and absent['missing_candidates']==required and not absent['production_activation']
alert={'id':'controlled-unexplained-asset-warning','explained':False};alerts=asset_gate([alert]);assert alerts['state']=='Blocked' and alerts['unexplained_alerts']==[alert['id']] and not alerts['asset_acceptance']
controls={'review_closed_without_runtime_proof':{'pr_closed':True},'unobserved_health_input':{'current_health_verified':None},'default_off_failed_input':False,'candidate_on_missing_input':{},'unexplained_asset_warning':alert,'on_catalog_copies':negative,'actual_current_health_status_separate_from_controlled_missing_health':health};write(E/'controlled-inputs.original.json',controls)
actuals=[('LOAD-11.4-T02',{'controlled_review_closed_claim':closed,'actual_current_cloud_health_status':health,'actual_current_cloud_HEAD':actual_head,'no_production_rollback_performed':True}),('PR13-A08.4-T02',{'controlled_unobserved_health_claim':unobserved,'actual_current_cloud_health_status':health,'controlled_unknown_not_actual_health_outage':True}),('PR13-B12.2-T01',{'controlled_default_off_failure_gate':failed,'actual_formal_default_policy':policy,'actual_default_regression_failure_not_claimed':True}),('PR13-B12.2-T02',{'controlled_missing_on_run_gate':absent,'candidate_runs_not_executed_by_this_audit':True,'actual_candidate_experiment_acceptance_not_claimed':True}),('PR13-B12.3-T03',{'actual_formal_default_policy':policy,'independent_controlled_flag_on_rejections':negative,'formal_catalog_unchanged':True}),('PR13-B12.4-T03',{'controlled_unexplained_asset_gate':alerts,'actual_asset_warning_not_invented':True,'actual_asset_acceptance_not_claimed':True})]
contracts={c['id']:c for pkg in plan['packages'] for t in pkg['subtasks'] for c in t['test_cases']};records=[]
for cid,actual in actuals:
 task=next(t for t in register['tasks'] if cid in t['missing_case_profiles']);assert 'AUDIT' in task['missing_case_profiles'][cid];c=contracts[cid];records.append({'case_id':cid,'executed':True,'status':'Passed','source_sha':SOURCE,'profiles_executed':['AUDIT'],'setup':c['setup_and_injection'],'expected':c['expected'],'actual':actual,'scope':'Tencent execution of exact current Git policy and declaration functions. Missing health/review-closed/failure/on-absence/asset-warning inputs and each one-flag-on catalog are controlled owned probes. Actual health is 200; no production rollback, candidate activation, gameplay, asset clearance or MAIN acceptance.'})
for name,row in inputs.items():
 raw=(W/name).read_bytes();assert len(raw)==row['bytes'] and hashlib.sha256(raw).hexdigest()==row['sha256']
(E/'cases.original.jsonl').write_bytes((''.join(json.dumps(row,ensure_ascii=False)+'\n' for row in records)).encode());write(E/'input-ledger.original.json',inputs);write(E/'result.original.json',{'ok':True,'implementation_source_sha':SOURCE,'native_clean':True,'source_inputs_match_git':True,'owned_container_removed':True,'owned_container_note':'No container started; bounded source-policy Python audit owns only its evidence and working copies.','actual_cloud_PID':os.getpid(),'executed':6,'passed':6,'negative_flag_controls':len(negative),'actual_current_health_status':health,'all_original_source_and_register_bytes_unchanged':True,'human_policy_unchanged_and_excluded':True,'production_MAIN_decision_applied':False,'MAIN_accepted':False});print(json.dumps({'ok':True,'case_ids':[r['case_id'] for r in records],'source_sha':SOURCE,'actual_cloud_PID':os.getpid(),'actual_current_health_status':health,'MAIN_accepted':False}))
