import hashlib,json,os,shutil,subprocess,sys,time
from pathlib import Path
SOURCE='581e4068643508d479eba8ca304dca2fb3de6aa4';REPO=Path('/opt/fantasycard-github');B=Path('/home/ubuntu/pr13-acceptance-20261009');A='current-config-bytes-two-audit-r1-20261012';E=B/'evidence'/A;W=B/'work'/A;assert not E.exists() and not W.exists();E.mkdir();W.mkdir();F=W/'frozen-inputs';F.mkdir();inputs={}
def sha(raw):return hashlib.sha256(raw).hexdigest()
def write(p,v):assert not p.exists();p.write_bytes((json.dumps(v,indent=2)+'\n').encode())
def frozen(name):
 raw=subprocess.check_output(['git','-C',str(REPO),'show',SOURCE+':'+name],timeout=30);oid=subprocess.check_output(['git','-C',str(REPO),'rev-parse',SOURCE+':'+name],text=True,timeout=30).strip();assert hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest()==oid;p=F/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(raw);inputs[name]={'bytes':len(raw),'sha256':sha(raw),'git_blob_sha1':oid};return raw
paths=['config/FantasyCard_Config.xlsx','client/data/catalog.json']+[folder+'/'+name for folder in ('server/config/generated','client/data/generated') for name in ('fantasycard.config.bytes','fantasycard.config.sha256','fantasycard.config.version.txt')]
for name in paths+['tools/pr13_stages.py','tools/export_client_catalog.py','docs/plans/PR13_ACCEPTANCE_DETAILS_20260930.json']:frozen(name)
sys.path.insert(0,str(F));from tools.pr13_stages import config_identity,config_bundle_identity
good=W/'positive-originals';bad=W/'same-filename-controlled-corruption'
for root in (good,bad):
 root.mkdir()
 for name in paths:
  p=root/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes((F/name).read_bytes())
initial=config_identity(good);assert initial['source_export_revalidated'] is False
source=good/'client/data/generated/fantasycard.config.bytes';raw=source.read_bytes();assert raw==(good/'server/config/generated/fantasycard.config.bytes').read_bytes();assert len(raw)>128;changed=raw[:-1]+bytes([raw[-1]^1]);assert changed!=raw and config_bundle_identity(raw)['content_sha256']==initial['content_sha256']
for folder in ('server/config/generated','client/data/generated'):(bad/folder/'fantasycard.config.bytes').write_bytes(changed)
old_decl=(good/'client/data/generated/fantasycard.config.sha256').read_bytes();old_version=(good/'client/data/generated/fantasycard.config.version.txt').read_bytes();assert (bad/'client/data/generated/fantasycard.config.sha256').read_bytes()==(bad/'server/config/generated/fantasycard.config.sha256').read_bytes()==old_decl;assert (bad/'client/data/generated/fantasycard.config.version.txt').read_bytes()==(bad/'server/config/generated/fantasycard.config.version.txt').read_bytes()==old_version
rejected=False;reason=''
try:config_identity(bad)
except ValueError as error:reason=str(error);rejected='embedded hash' in reason
assert rejected and sha(raw)!=sha(changed);final=config_identity(good);assert final==initial
for name,row in inputs.items():
 original=(F/name).read_bytes();assert len(original)==row['bytes'] and sha(original)==row['sha256']
for name in paths:assert (good/name).read_bytes()==(F/name).read_bytes()
actual={'actual_current_config_version':initial['version'],'actual_original_content_sha256':initial['content_sha256'],'original_bundle_bytes':len(raw),'actual_original_bundle_SHA256':sha(raw),'controlled_changed_bundle_SHA256':sha(changed),'same_filename':True,'same_declarations_and_version_retained':True,'both_server_and_client_changed_copy_bytes_identical':True,'actual_embedded_content_validation_rejection':reason,'original_inputs_unchanged':True,'positive_original_validation_before_and_after':True,'source_export_revalidated':False,'production_config_mutated':False};write(E/'observations.original.json',actual);plan=json.loads((F/'docs/plans/PR13_ACCEPTANCE_DETAILS_20260930.json').read_bytes());contracts={c['id']:c for p in plan['packages'] for task in p['subtasks'] for c in task['test_cases']};rows=[]
for cid in ('PR13-A08.1-T03','PR13-B12.1-T02'):
 c=contracts[cid];rows.append({'case_id':cid,'executed':True,'status':'Passed','source_sha':SOURCE,'profiles_executed':['AUDIT'],'setup':c['setup_and_injection'],'expected':c['expected'],'actual':actual,'scope':'Actual current published configuration bytes and current validator on Tencent, with one-bit corruption of owned copies only. No source-table regeneration, database, gameplay, render, experiment, or whole MAIN claim.'})
(E/'cases.original.jsonl').write_bytes((''.join(json.dumps(row,ensure_ascii=False)+'\n' for row in rows)).encode());write(E/'input-ledger.original.json',inputs);write(E/'result.original.json',{'ok':True,'implementation_source_sha':SOURCE,'native_clean':True,'source_inputs_match_git':True,'owned_container_removed':True,'owned_container_note':'No container started; bounded cloud Python process owns only its metadata and working copies.','actual_cloud_PID':os.getpid(),'executed':2,'passed':2,'profiles_executed':['AUDIT'],'positive_config_version':initial['version'],'source_table_export_revalidated':False,'original_config_source_bytes_unchanged':True,'MAIN_accepted':False});print(json.dumps({'ok':True,'case_ids':[r['case_id'] for r in rows],'source_sha':SOURCE,'actual_cloud_PID':os.getpid(),'MAIN_accepted':False}))
