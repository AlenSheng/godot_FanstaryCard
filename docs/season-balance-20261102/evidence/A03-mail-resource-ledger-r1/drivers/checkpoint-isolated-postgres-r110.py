from pathlib import Path
import base64,json,shlex,subprocess

base=Path(__file__).parent;target=base/'runtime-r110/isolated-PG-checkpoint.original.json';assert not target.exists()
code='''from pathlib import Path
import json,subprocess,shutil
cid='803968e390014540be88f60b9ac43203946d0145bf886fc61d9d9d4d04bc3b1a'
row=json.loads(subprocess.check_output(['docker','inspect',cid]))[0];assert row['State']['Running'] and row['Config']['Labels']['com.fantasycard.task']=='season-balance-20261102-a03-storage-r1'
env=dict(s.split('=',1) for s in row['Config']['Env'] if '=' in s);args=['docker','exec',cid,'psql','-X','-A','-t','-v','ON_ERROR_STOP=1','-U',env.get('POSTGRES_USER','postgres'),'-d',env.get('POSTGRES_DB',env.get('POSTGRES_USER','postgres'))]
before=shutil.disk_usage('/home/ubuntu').free
r=subprocess.run(args+['-c','SELECT sum(size) FROM pg_ls_waldir(); CHECKPOINT; SELECT sum(size) FROM pg_ls_waldir();'],capture_output=True,text=True,timeout=40)
print(json.dumps({'returncode':r.returncode,'stdout':r.stdout,'stderr':r.stderr,'disk_before':before,'disk_after':shutil.disk_usage('/home/ubuntu').free,'isolated_test_PG_only':True,'retirement_key_note':'runtime108_next_base_unchanged in r108 retirement means retained runtime109 base; actual code verifies that exact path.'}))
'''
command='sudo -n python3 -c '+shlex.quote('import base64;exec(base64.b64decode('+repr(base64.b64encode(code.encode()).decode())+'))')
r=subprocess.run(['ssh','-i',r'C:\Users\SHENGJIAHAO\.ssh\gpt-deploy-release.pem','-o','BatchMode=yes','-o','StrictHostKeyChecking=yes','-o','ConnectTimeout=12','ubuntu@43.172.70.182',command],capture_output=True,text=True,timeout=50)
target.write_text(json.dumps({'returncode':r.returncode,'stdout':r.stdout,'stderr':r.stderr},indent=2)+'\n',encoding='utf-8');print(r.stdout+r.stderr);assert r.returncode==0
