
import hashlib,importlib.util,json,sys
from pathlib import Path
W=Path('/work');OUT=Path('/evidence');sys.path.insert(0,str(W))
from tools.pr13_historical_inventory_audit import inventory,sha
root=Path('/home/ubuntu/pr13-acceptance-20261009/historical-original-inputs-missing-r1');assert not root.exists()
results=[]
for name,count,local_name in [('cloud-evidence-manifest-v2.json',2084,'historical-cloud2084-current-inventory-v2.json'),('local-evidence-manifest.json',60,'historical-early60-current-inventory-v2.json')]:
 p=W/'docs/reports/gameplay-load-20260929'/name;local=json.loads((W/'local-inventory'/local_name).read_bytes());value=inventory(p,root);assert value['declared_members']==count and value['counts']=={'Missing':count} and local['counts']==value['counts'] and local['manifest_sha256']==value['manifest_sha256'];(OUT/(name+'.audit.json')).write_text(json.dumps(value,indent=2)+'\n');results.append({'manifest':name,'members':count,'local_actual_root_missing':True,'cloud_original_dataset_not_recovered':True,'local_inventory_sha256':sha(W/'local-inventory'/local_name),'manifest_sha256':value['manifest_sha256'],'counts':value['counts']})
# Production/source identity is collected separately by the host dispatcher;
# this report makes no historical runtime restoration or new capacity claim.
v={'ok':True,'execution_host':'Tencent Linux','actual_original_inventory_members':2144,'all_2084_and_early60_members_classified':True,'originals_missing':2144,'historical_raw_recovered':False,'historical_totals_reconciled':False,'old_86_90_and_130_139_discrepancies_not_repaired':True,'separate_new_tests_required_by_user':True,'datasets':results,'AUDIT_inventory_execution_complete':True,'historical_reconciliation_accepted':False,'MAIN_accepted':False};(OUT/'result.json').write_text(json.dumps(v,indent=2)+'\n');print(json.dumps(v))
