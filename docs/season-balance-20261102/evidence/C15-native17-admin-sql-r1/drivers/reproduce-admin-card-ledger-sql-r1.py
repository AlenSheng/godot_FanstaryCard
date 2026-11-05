from pathlib import Path
import base64,hashlib,json,re,shlex,subprocess,uuid

repo=Path.cwd();base=Path(__file__).parent;work=base/'admin-card-ledger-sql-r1';assert not work.exists();work.mkdir()
files=['server/src/FantasyCard.Server/Admin/AdminRepository.cs','server/src/FantasyCard.Server/Progression/PermanentCardCopies.cs','server/src/FantasyCard.Server/Progression/EconomyReconciliation.cs','server/src/FantasyCard.Server/Persistence/Migrations/V044__permanent_card_reserves.sql']
raw={name:(repo/name).read_bytes() for name in files};text={name:value.decode('utf-8-sig') for name,value in raw.items()}
admin=re.search(r'"""\s*(INSERT INTO player_cards\(.*?WHERE player_cards.unlocked=false OR player_cards.copy_count<1)\s*"""',text[files[0]],re.S).group(1)
ledger=re.search(r'"""\s*(INSERT INTO card_copy_ledger\(.*?VALUES\(\$1,\$2,\$3,\$4,\$5,\$6,\$7,\$8\))\s*"""',text[files[1]],re.S).group(1)
check=text[files[2]]
cte=check.split('), card_copy_chain AS (',1)[1].split('), activity_chain AS (',1)[0]
query=check.split('(SELECT count(*) FROM card_copy_chain',1)[1].split('(SELECT count(*) FROM activity_chain',1)[0].rstrip().rstrip(',')
query='WITH card_copy_chain AS ('+cte+') SELECT (SELECT count(*) FROM card_copy_chain'+query+';'
player=str(uuid.uuid4());movement=str(uuid.uuid4())
sql=f'''\\set ON_ERROR_STOP on
BEGIN;
CREATE TEMP TABLE player_cards(player_id uuid,card_id varchar(80),hero_class smallint,rarity smallint,is_monster boolean,unlocked boolean,copy_count smallint,level smallint,version bigint,PRIMARY KEY(player_id,card_id));
CREATE TEMP TABLE player_card_reserves(player_id uuid,card_id varchar(80),extra_count integer,PRIMARY KEY(player_id,card_id));
CREATE TEMP TABLE card_copy_ledger(movement_id uuid PRIMARY KEY,ledger_sequence bigint GENERATED ALWAYS AS IDENTITY UNIQUE,player_id uuid,card_id varchar(80),delta integer,balance_after integer,reason varchar(80),request_id varchar(128),created_at timestamptz,UNIQUE(player_id,reason,request_id,card_id));
INSERT INTO player_cards VALUES('{player}','declared-card',0,1,false,false,0,0,1);
INSERT INTO card_copy_ledger(movement_id,player_id,card_id,delta,balance_after,reason,request_id,created_at) VALUES('{movement}','{player}','declared-card',-1,0,'test.declared-prior-consumption','prior',now());
PREPARE old_unlock(uuid,varchar,smallint,smallint) AS {admin};
PREPARE grant_ledger(uuid,uuid,varchar,integer,integer,varchar,varchar,timestamptz) AS {ledger};
\\echo BASELINE
{query}
SAVEPOINT before_unlock;
EXECUTE old_unlock('{player}','declared-card',0,1);
\\echo OLD_MUTATION_WITHOUT_CARD_LEDGER
{query}
EXECUTE grant_ledger(gen_random_uuid(),'{player}','declared-card',1,1,'admin.unlock_all_cards','new-admin',now());
\\echo SAME_MUTATION_WITH_TRANSACTIONAL_LEDGER
{query}
ROLLBACK TO SAVEPOINT before_unlock;
\\echo ROLLED_BACK
{query}
ROLLBACK;
'''
(work/'fixture.original.sql').write_text(sql,encoding='utf-8')
pins={name:hashlib.sha256(value).hexdigest() for name,value in raw.items()}
(work/'source-pin.json').write_text(json.dumps(pins,indent=2)+'\n',encoding='utf-8')
source='''from pathlib import Path
import base64,json,shutil,subprocess,time
cid='803968e390014540be88f60b9ac43203946d0145bf886fc61d9d9d4d04bc3b1a'
row=json.loads(subprocess.check_output(['docker','inspect',cid]))[0]
assert row['State']['Running'] and row['Config']['Labels']['com.fantasycard.task']=='season-balance-20261102-a03-storage-r1'
def resources():
 m={s.split(':')[0]:int(s.split()[1])*1024 for s in Path('/proc/meminfo').read_text().splitlines() if len(s.split())>1 and s.split()[1].isdigit()};d=shutil.disk_usage('/home/ubuntu')
 return {'ram':m['MemAvailable'],'disk':d.free,'ratio':d.free/d.total}
samples=[]
for _ in range(3):samples.append(resources());time.sleep(1)
assert all(s['ram']>=1800*1024**2 and s['disk']>=3*1024**3 and s['ratio']>=.05 for s in samples)
env=dict(item.split('=',1) for item in row['Config']['Env'] if '=' in item)
args=['docker','exec','-i',cid,'psql','-X','-A','-t','-v','ON_ERROR_STOP=1','-U',env.get('POSTGRES_USER','postgres'),'-d',env.get('POSTGRES_DB',env.get('POSTGRES_USER','postgres'))]
r=subprocess.run(args,input=base64.b64decode(SQL),capture_output=True,timeout=30)
after=resources();assert after['ram']>=500*1024**2 and after['disk']>=3*1024**3 and after['ratio']>=.05
print(json.dumps({'returncode':r.returncode,'stdout':r.stdout.decode(),'stderr':r.stderr.decode(),'before':samples,'after':after,'temp_tables_only':True,'transaction_rolled_back':r.returncode==0}))
'''.replace('SQL',repr(base64.b64encode(sql.encode()).decode()))
(work/'remote.original.py').write_text(source,encoding='utf-8')
command='sudo -n python3 -c '+shlex.quote('import base64;exec(base64.b64decode('+repr(base64.b64encode(source.encode()).decode())+'))');assert len(command)<30000
r=subprocess.run(['ssh','-i',r'C:\Users\SHENGJIAHAO\.ssh\gpt-deploy-release.pem','-o','BatchMode=yes','-o','StrictHostKeyChecking=yes','-o','ConnectTimeout=12','ubuntu@43.172.70.182',command],capture_output=True,text=True,timeout=45)
(work/'transport.original.json').write_text(json.dumps({'returncode':r.returncode,'stdout':r.stdout,'stderr':r.stderr},indent=2)+'\n',encoding='utf-8');assert r.returncode==0,r.stderr
data=json.loads(r.stdout);(work/'result.original.json').write_text(json.dumps(data,indent=2)+'\n',encoding='utf-8');print(json.dumps(data));assert data['returncode']==0
values=[int(line) for line in data['stdout'].splitlines() if line.isdigit()];assert values==[0,1,0,0],values
assert all(hashlib.sha256((repo/n).read_bytes()).hexdigest()==h for n,h in pins.items())
(work/'validation.json').write_text(json.dumps({'counterexample_proved':True,'discrepancies':values,'scope':'isolated temporary-table SQL counterexample using actual mutation/ledger/reconciliation SQL; not repository/HTTP integration','new_PG_repository_cases_passed':0,'production_changed':False},indent=2)+'\n',encoding='utf-8')
