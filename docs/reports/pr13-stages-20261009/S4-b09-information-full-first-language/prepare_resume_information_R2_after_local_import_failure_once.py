import ast,gzip,hashlib,importlib.util,json,sys,tarfile
from pathlib import Path
B=Path(__file__).parent;R=B.parents[1];sys.path.insert(0,str(R));from tools.pr13_pool_render_evidence import png_validate
P=B/'information-default-render-full972-r2';L=P/'zh-CN';archive=L/'delivery.private.tar.gz';manifest=json.loads((L/'delivery-manifest.json').read_bytes());expected={x['path']:x for x in manifest['files']};seen=set();raw=(L/'delivery-manifest.json').read_bytes()
with tarfile.open(archive,'r|gz') as t:
 for item in t:
  assert item.isfile() and item.name not in seen;seen.add(item.name);data=t.extractfile(item).read()
  if item.name=='manifest.json':assert data==raw;continue
  row=expected[item.name];p=L/'verified'/item.name;assert len(data)==item.size==row['bytes'] and hashlib.sha256(data).hexdigest()==row['sha256'] and p.read_bytes()==data
assert seen==set(expected)|{'manifest.json'}
with gzip.open(archive,'rb') as f:
 for _ in iter(lambda:f.read(65536),b''):pass
images=list((L/'verified/outputs').glob('*.png'));assert len(images)==27
for p in images:png_validate(p)
native=json.loads((L/'verified/metadata/run-result.json').read_bytes());assert native['ok'] and native['rows']==486 and native['PNGs']==27 and native['owned_container_removed']
plan=json.loads((B/'b09-information-default-render-full972-r2-runners/plan.json').read_bytes());proof={'ok':True,'unit':plan['units'][0],'local_directory':str(L/'verified'),'local_archive':str(archive),'sha256':hashlib.sha256(archive.read_bytes()).hexdigest(),'bytes':archive.stat().st_size,'manifest_sha256':hashlib.sha256(raw).hexdigest(),'members_verified':len(expected),'archive_gzip_CRC_verified':True,'all_original_members_SHA_verified':True,'original_PNG_CRC_verified':27,'actual_rows':486,'visual_review_pending':True,'actual_PID1_terminal_proof_pending':True,'local_controller_import_failure_corrected_without_native_rerun':True,'MAIN_accepted':False};assert not (L/'local-backup-receipt.json').exists();(L/'local-backup-receipt.json').write_text(json.dumps(proof,indent=2)+'\n',encoding='utf-8')
s=(B/'run_full_information972_R2_serial_and_G_close_once.py').read_text(encoding='utf-8');s=s.replace('import ast,base64,gzip,hashlib,importlib.util,json,os,tarfile,time','import ast,base64,gzip,hashlib,importlib.util,json,os,sys,tarfile,time')
s=s.replace('assert not OUT.exists();OUT.mkdir();','assert OUT.exists();sys.path.insert(0,str(B.parents[1]));')
old="assert json_remote('G='+repr(g)+'\\nPLAN='+repr(plan)+'\\n'+setup)['ok']";assert old in s
audit=r'''
import json,subprocess
from pathlib import Path
B=Path('/home/ubuntu/pr13-acceptance-20261009');P=B/'evidence/information-default-render-full972-r2';a='b09-information-default-render-full-en-r2-20261011';assert P.exists() and json.loads((B/'evidence/pool-render-segments-r3/scheduling-hold.json').read_bytes())['owner']=='pr13-information-default-render-full972-r2';assert not (B/'evidence'/a).exists() and not (B/'work'/a).exists() and not (Path('/etc/systemd/system')/('pr13-cap-'+a+'.service')).exists();zh=B/'evidence/b09-information-default-render-full-zh-cn-r2-20261011';v=json.loads((zh/'run-result.json').read_bytes());assert v['ok'] and v['rows']==486;state=dict(x.split('=',1) for x in subprocess.check_output(['systemctl','show','pr13-cap-b09-information-default-render-full-zh-cn-r2-20261011','--property=MainPID,ActiveState,ExecMainStatus'],text=True).splitlines());assert state['MainPID']=='0' and state['ActiveState']=='inactive' and state['ExecMainStatus']=='0';print(json.dumps({'ok':True,'original_zh_passed_not_restarted':True,'en_dispatch_authoritatively_absent':True}))
'''
s=s.replace(old,'audit='+repr(audit)+'\nassert json_remote(audit)[\'ok\']');s=s.replace("for unit in plan['units']:","for unit in plan['units'][1:]:",1)
ast.parse(s)
for node in ast.walk(ast.parse(s)):
 if isinstance(node,ast.Assign) and any(isinstance(t,ast.Name) and t.id in ('setup','audit','dispatch','collect') for t in node.targets) and isinstance(node.value,ast.Constant) and isinstance(node.value.value,str):ast.parse(node.value.value)
p=B/'resume_information_R2_original_en_after_complete_zh_G_once.py';assert not p.exists();p.write_text(s,encoding='utf-8');print(json.dumps({'ok':True,'zh_complete_original_G_bytes':archive.stat().st_size,'PNGs_CRC_checked':27,'remaining_native_en_rows':486,'no_zh_native_rerun':True,'all_embedded_AST_checked':True}))
