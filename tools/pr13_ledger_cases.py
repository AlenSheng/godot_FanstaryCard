"""Explicit ledger attribution cases plus hash-verified current native audits."""
import argparse,hashlib,json,subprocess,sys,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from tools.tests.test_pr13_ledger_attribution import snapshot,run_pair
from tools.pr13_ledger_attribution import attribute

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def write(p,v):p.write_bytes((json.dumps(v,ensure_ascii=False,indent=2,allow_nan=False)+'\n').encode())
def main():
 parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',required=True,type=Path);parser.add_argument('--native-audit',type=Path);args=parser.parse_args();out=args.output.resolve();out.mkdir(parents=True,exist_ok=False)
 plan_path=ROOT/'docs/plans/PR13_ACCEPTANCE_DETAILS_20260930.json';plan=json.loads(plan_path.read_text(encoding='utf8'));contracts={c['id']:c for p in plan['packages'] for s in p['subtasks'] for c in s['test_cases']};records=[]
 for number in (1,2,3):
  with tempfile.TemporaryDirectory() as directory:
   before=snapshot(number==1);after=snapshot(number!=3,'2026-10-08T00:00:01+00:00')
   if number==3:after['result']={'error':'permission denied; chain unavailable'}
   result=run_pair(Path(directory),before,after)
  expected=['ExistingWithEvidence','NewDifferenceBlocksAssets','Blocked'][number-1];case_id='PR13-A05.4-T0'+str(number)
  records.append({'case_id':case_id,'executed':True,'status':'Passed' if result['classification']==expected and not result['asset_acceptance'] else 'Failed','setup':contracts[case_id]['setup_and_injection'],'expected':contracts[case_id]['expected'],'actual':result,'profiles_executed':['OFFLINE','AUDIT'],'scope':'Controlled complete/denied source snapshots, not deleted historical recovery or native PostgreSQL fault proof'})
 actual=[]
 if args.native_audit:
  native=args.native_audit.resolve();receipts=[json.loads(l) for l in (native/'receipts.jsonl').read_text(encoding='utf8').splitlines()];declared={Path(r['evidence']['path']).name:r['evidence']['resultSha256'] for r in receipts if r['caseId']=='A05-readonly-audit'}
  for before in sorted(native.glob('a05-audit-*-before.json')):
   after=before.with_name(before.name.replace('-before.json','-after.json'))
   if not after.exists():raise ValueError('Current native after-audit missing')
   files=[]
   for file in (before,after):
    if declared.get(file.name)!=sha(file):raise ValueError('Native receipt snapshot hash changed')
    files.append({'path':file.name,'bytes':file.stat().st_size,'sha256':sha(file)})
   result=attribute(native,{'files':files})
   if result['classification']!='NoAlertInObservedScope':raise ValueError('Current native ledger audit requires review')
   actual.append({'before':files[0],'after':files[1],'result':result})
 (out/'cases.jsonl').write_bytes(''.join(json.dumps(r,ensure_ascii=False,allow_nan=False)+'\n' for r in records).encode())
 head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
 write(out/'report.json',{'source_sha':head,'source':{'scope':'immutable controlled attribution fixtures and optional actual native snapshot replay','input_hashes':{p:sha(ROOT/p) for p in ('tools/pr13_ledger_attribution.py','tools/pr13_ledger_cases.py','tools/tests/test_pr13_ledger_attribution.py')}},'plan_sha256':sha(plan_path),'executed':3,'passed':sum(r['status']=='Passed' for r in records),'native_audit_pairs':len(actual),'accepted':False,'remaining':'POSTGRES alert/permission fault layer is still separate; normal current native zero-alert snapshots do not replace those faults.'})
 write(out/'native-audits.json',{'results':actual});print(json.dumps({'executed':3,'passed':sum(r['status']=='Passed' for r in records),'native_pairs':len(actual)}));return 0 if all(r['status']=='Passed' for r in records) else 1
if __name__=='__main__':raise SystemExit(main())
