"""Actual migrations and READ ONLY ledger-alert/permission faults on owned PG."""
import argparse,hashlib,json,subprocess,sys,time,uuid
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from tools.pr13_local_runtime import LocalRuntime,run
from tools.pr13_ledger_attribution import attribute
QUERY="WITH chain AS (SELECT *,lag(balance_after) OVER(PARTITION BY player_id,currency ORDER BY created_at,ledger_id) previous FROM economy_ledger WHERE currency<>'ClassSoul') SELECT jsonb_build_object('checked_at',CURRENT_TIMESTAMP,'ledger',COALESCE((SELECT jsonb_agg(to_jsonb(t)) FROM economy_ledger t),'[]'::jsonb),'ledger_chain_mismatches',(SELECT count(*) FROM chain WHERE previous IS NOT NULL AND previous+delta<>balance_after))"
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def write(p,v):p.write_bytes((json.dumps(v,ensure_ascii=False,indent=2,allow_nan=False)+'\n').encode())
def main():
 parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',required=True,type=Path);parser.add_argument('--database-container',required=True);args=parser.parse_args();out=args.output.resolve();head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip();records=[];role='pr13_ledger_'+uuid.uuid4().hex;role_created=False
 plan_path=ROOT/'docs/plans/PR13_ACCEPTANCE_DETAILS_20260930.json';plan=json.loads(plan_path.read_text(encoding='utf8'));contracts={c['id']:c for p in plan['packages'] for s in p['subtasks'] for c in s['test_cases']}
 with LocalRuntime(out,args.database_container) as host:
  query_hash=hashlib.sha256(QUERY.encode()).hexdigest();write(out/'preregistration.json',{'profiles':['OFFLINE','POSTGRES','AUDIT'],'cases':['PR13-A05.4-T01','PR13-A05.4-T02','PR13-A05.4-T03'],'source_sha':head,'query_sha256':query_hash,'scope':'new disposable database after actual Program migrations; synthetic actor/ledger seeds are explicit fault setup','mutation_policy':'Only setup inserts and owned role setup; collector READ ONLY/ROLLBACK; no repair/delete of balances or ledger','deadline_seconds':1800,'case_deadline_seconds':180})
  def capture(name,denied=None):
   if denied is None:
    raw=host.sql("BEGIN READ ONLY; SET LOCAL statement_timeout='5s'; "+QUERY+"; ROLLBACK;")
    (out/(name+'.raw.txt')).write_bytes(raw.encode())
    values=[json.loads(l) for l in raw.splitlines() if l.strip().startswith('{')]
    if len(values)!=1:raise ValueError('No unique native read-only snapshot')
    result=values[0]
   else:result=denied
   path=out/(name+'.json');write(path,{'scope':host.database,'querySha256':query_hash,'transaction':'READ ONLY; rollback; no mutation','result':result});return path
  def compare(case_id,before,after):
   files=[{'path':p.name,'bytes':p.stat().st_size,'sha256':sha(p)} for p in (before,after)];actual=attribute(out,{'files':files});expected={'PR13-A05.4-T01':'ExistingWithEvidence','PR13-A05.4-T02':'NewDifferenceBlocksAssets','PR13-A05.4-T03':'Blocked'}[case_id];contract=contracts[case_id]
   records.append({'case_id':case_id,'executed':True,'status':'Passed' if actual['classification']==expected and actual['asset_acceptance'] is False else 'Failed','setup':contract['setup_and_injection'],'expected':contract['expected'],'actual':actual,'profiles_executed':['OFFLINE','POSTGRES','AUDIT'],'scope':'Owned fresh migrated native database fault; no attribution to deleted historical/production data'})
  def seed_actor(bad):
   player=str(uuid.uuid4());one=str(uuid.uuid4());two=str(uuid.uuid4())
   host.sql("INSERT INTO players(user_id,display_name,created_at,updated_at) VALUES ('"+player+"','owned-ledger-"+player[:8]+"',CURRENT_TIMESTAMP,CURRENT_TIMESTAMP); INSERT INTO economy_ledger(ledger_id,player_id,currency,delta,balance_after,reason,created_at) VALUES ('"+one+"','"+player+"','Gold',25,25,'owned.fixture',CURRENT_TIMESTAMP-interval '2 seconds'),('"+two+"','"+player+"','Gold',1,"+('24' if bad else '26')+",'owned.fixture',CURRENT_TIMESTAMP-interval '1 second');")
   return player
  seed_actor(True);before=capture('existing-before');host.sql('SELECT 1');after=capture('existing-after');compare('PR13-A05.4-T01',before,after)
  player=seed_actor(False);before=capture('new-before');third=str(uuid.uuid4());host.sql("INSERT INTO economy_ledger(ledger_id,player_id,currency,delta,balance_after,reason,created_at) VALUES ('"+third+"','"+player+"','Gold',1,20,'owned.new-fault',CURRENT_TIMESTAMP)");after=capture('new-after');compare('PR13-A05.4-T02',before,after)
  before=capture('denied-before')
  try:
   host.sql('CREATE ROLE '+role+' NOLOGIN');role_created=True
   command=['docker','exec',host.container,'psql','-X','-A','-t','-v','ON_ERROR_STOP=1','-v','VERBOSITY=verbose','-U',host.info['user'],'-d',host.database,'-c',"BEGIN READ ONLY; SET LOCAL statement_timeout='5s'; SET LOCAL ROLE "+role+'; '+QUERY+'; ROLLBACK;']
   denied=run(command)
   if denied.returncode==0 or '42501' not in denied.stderr:raise ValueError('Expected native permission denial not observed')
   (out/'permission.private.log').write_bytes(denied.stderr.encode());after=capture('denied-after',{'native_sqlstate':'42501','available':False,'reason':'actual restricted-role SELECT denied'});compare('PR13-A05.4-T03',before,after)
  finally:
   if role_created:host.sql('DROP ROLE '+role);role_created=False
 (out/'cases.jsonl').write_bytes(''.join(json.dumps(r,ensure_ascii=False,allow_nan=False)+'\n' for r in records).encode())
 write(out/'report.json',{'source_sha':head,'source':{'scope':'actual full Program migrations, complete read-only native ledger snapshots and native restricted-role denial','input_hashes':{p:sha(ROOT/p) for p in ('tools/pr13_ledger_attribution.py','tools/pr13_ledger_postgres_cases.py','tools/pr13_local_runtime.py')}},'plan_sha256':sha(plan_path),'executed':len(records),'passed':sum(r['status']=='Passed' for r in records),'owned_host_database_cleanup':host.record['cleanup'],'owned_role_removed':not role_created,'accepted':False,'historical_recovery':False})
 write(out/'artifact-index.json',{'files':[{'path':p.name,'bytes':p.stat().st_size,'sha256':sha(p)} for p in sorted(out.glob('*.json'))]});print(json.dumps({'executed':len(records),'passed':sum(r['status']=='Passed' for r in records),'cleanup':host.record['cleanup']}));return 0 if len(records)==3 and all(r['status']=='Passed' for r in records) and host.record['cleanup'] else 1
if __name__=='__main__':raise SystemExit(main())
