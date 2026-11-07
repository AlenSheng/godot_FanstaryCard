from pathlib import Path
import json,hashlib,tarfile,subprocess,base64,shlex,sys
sys.stdout.reconfigure(encoding='utf-8');b=Path(__file__).parent;o=b/'runtime-r107';selected=[]
for number in range(92,104):
    stage='runtime-r'+str(number);root=b/stage;meta=root/'collection-audit.json'
    if not meta.exists():continue
    audit=json.loads(meta.read_text('utf-8'))
    if audit['state']!='exited' or audit['exit_code']!=0 or audit['counts']['failed']!='0' or audit['counts']['notExecuted']!='0':continue
    archive=root/'public-evidence.tar.gz';digest=hashlib.sha256(archive.read_bytes()).hexdigest();assert digest==audit['public_archive_sha256']
    for name,h in audit['files'].items():assert hashlib.sha256((root/'public'/name).read_bytes()).hexdigest()==h
    with tarfile.open(archive,'r:gz') as tf:
        for member in tf:
            assert member.isfile() and (member.name in audit['files'] or member.name=='audit.json')
            if member.name in audit['files']:assert hashlib.sha256(tf.extractfile(member).read()).hexdigest()==audit['files'][member.name]
    selected.append(dict(stage=stage,bytes=archive.stat().st_size,sha256=digest))
    if len(selected)==9:break
assert len(selected)>=6
code=r"""from pathlib import Path
import json,hashlib,subprocess,shutil
items=ITEMS;proof=[];before=shutil.disk_usage('/home/ubuntu').free
for item in items:
 root=Path('/home/ubuntu/season-balance-20261102-a03-'+item['stage']).resolve();assert root.parent==Path('/home/ubuntu') and not (root/'input').exists()
 assert not subprocess.check_output(['docker','ps','-a','--filter','label=com.fantasycard.task=season-balance-20261102-a03-'+item['stage'],'--format','{{.ID}}']).strip()
 p=root/'public-evidence.tar.gz';assert p.is_file() and not p.is_symlink() and p.resolve().parent==root and p.stat().st_size==item['bytes'] and hashlib.sha256(p.read_bytes()).hexdigest()==item['sha256']
 proof.append(dict(item,root=str(root)))
for item in proof:
 root=Path(item['root']);(root/'public-evidence.tar.gz').unlink();(root/'verified-compressed-duplicate-retirement.json').write_text(json.dumps(dict(only_verified_successful_compressed_duplicate_removed=True,exact_original_and_all_members_retained_locally=True,raw_cloud_result_files_unchanged=True,PG_unchanged=True,**item))+chr(10))
print(json.dumps(dict(successful_duplicates=proof,free_disk_before=before,free_disk_after=shutil.disk_usage('/home/ubuntu').free,failed_batch_archives_untouched=True,all_original_bytes_retained_locally=True)))
""".replace('ITEMS',repr(selected))
cmd='sudo -n python3 -c '+shlex.quote('import base64;exec(base64.b64decode('+repr(base64.b64encode(code.encode()).decode())+'))')
out=o/'successful-public-duplicate-retirement.original.json';assert not out.exists();r=subprocess.run(['ssh','-n','-i',r'C:\Users\SHENGJIAHAO\.ssh\gpt-deploy-release.pem','-o','BatchMode=yes','-o','StrictHostKeyChecking=yes','-o','ConnectTimeout=12','ubuntu@43.172.70.182',cmd],capture_output=True,text=True,encoding='utf-8',timeout=45);out.write_text(r.stdout+r.stderr,encoding='utf-8');print(r.stdout+r.stderr);assert r.returncode==0
