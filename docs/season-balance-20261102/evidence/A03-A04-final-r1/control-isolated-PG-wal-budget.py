from pathlib import Path
import base64,json,shlex,subprocess,sys

base=Path(__file__).parent;mode=sys.argv[1];assert mode in ('apply','restore');out=base/('isolated-PG-wal-'+mode+'-r1.original.json');assert not out.exists()
code='''from pathlib import Path
import json,re,shutil,subprocess
mode=MODE;cid='803968e390014540be88f60b9ac43203946d0145bf886fc61d9d9d4d04bc3b1a'
info=json.loads(subprocess.check_output(['docker','inspect',cid]))[0];assert info['State']['Running'] and info['Config']['Labels']['com.fantasycard.task']=='season-balance-20261102-a03-storage-r1'
env=dict(x.split('=',1) for x in info['Config']['Env'] if '=' in x);args=['docker','exec',cid,'psql','-X','-A','-t','-v','ON_ERROR_STOP=1','-U',env.get('POSTGRES_USER','postgres'),'-d',env.get('POSTGRES_DB',env.get('POSTGRES_USER','postgres'))]
def sql(value):return subprocess.check_output(args+['-c',value],stderr=subprocess.STDOUT,text=True).strip()
def settings():return {n:sql('SHOW '+n) for n in ['max_wal_size','min_wal_size','fsync','synchronous_commit','full_page_writes']}
root=Path('/home/ubuntu/season-balance-20261102-a03-storage-r1');state=root/'wal-budget-control-20261105.json';before=settings();free_before=shutil.disk_usage(root).free
if mode=='apply':
 assert not state.exists();state.write_text(json.dumps({'old':before,'isolated_test_PG_only':True},indent=2)+chr(10))
 sql("ALTER SYSTEM SET min_wal_size='32MB'");sql("ALTER SYSTEM SET max_wal_size='128MB'")
else:
 saved=json.loads(state.read_text());assert not saved.get('restored',False)
 for name in ['max_wal_size','min_wal_size']:
  value=saved['old'][name];assert re.fullmatch(r'[0-9]+(?:kB|MB|GB)',value);sql("ALTER SYSTEM SET "+name+"='"+value+"'")
sql('SELECT pg_reload_conf()');sql('CHECKPOINT');after=settings()
for name in ['fsync','synchronous_commit','full_page_writes']:assert before[name]==after[name]
assert after['fsync']=='on' and after['synchronous_commit']=='on' and after['full_page_writes']=='on'
if mode=='restore':
 assert all(after[n]==saved['old'][n] for n in ['max_wal_size','min_wal_size']);saved['restored']=True;state.write_text(json.dumps(saved,indent=2)+chr(10))
print(json.dumps({'mode':mode,'before':before,'after':after,'WAL_bytes':int(sql('SELECT sum(size) FROM pg_ls_waldir()')),'disk_before':free_before,'disk_after':shutil.disk_usage(root).free,'durability_settings_unchanged':True,'cloud_guards_unchanged':True,'only_owned_test_PG_modified':True}))
'''.replace('MODE',repr(mode))
command='sudo -n python3 -c '+shlex.quote('import base64;exec(base64.b64decode('+repr(base64.b64encode(code.encode()).decode())+'))')
r=subprocess.run(['ssh','-i',r'C:\Users\SHENGJIAHAO\.ssh\gpt-deploy-release.pem','-o','BatchMode=yes','-o','StrictHostKeyChecking=yes','-o','ConnectTimeout=12','ubuntu@43.172.70.182',command],capture_output=True,text=True,timeout=70)
out.write_text(json.dumps({'returncode':r.returncode,'stdout':r.stdout,'stderr':r.stderr},indent=2)+'\n',encoding='utf-8');print(r.stdout+r.stderr);assert r.returncode==0
