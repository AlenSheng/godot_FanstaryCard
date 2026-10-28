import hashlib,json,tempfile,unittest
from pathlib import Path
from tools.pr13_ledger_attribution import attribute


def snapshot(mismatch=False,checked='2026-10-08T00:00:00+00:00'):
 rows=[dict(ledger_id='00000000-0000-0000-0000-000000000001',player_id='fixture-player',currency='Gold',created_at='2026-10-07T00:00:00+00:00',delta=25,balance_after=25),dict(ledger_id='00000000-0000-0000-0000-000000000002',player_id='fixture-player',currency='Gold',created_at='2026-10-07T00:00:01+00:00',delta=1,balance_after=24 if mismatch else 26)]
 return {'scope':'owned-fixture','querySha256':'a'*64,'transaction':'READ ONLY; rollback; no mutation','result':{'checked_at':checked,'ledger_chain_mismatches':int(mismatch),'ledger':rows}}


def run_pair(root,before,after):
 files=[]
 for name,data in [('before.json',before),('after.json',after)]:
  path=root/name;path.write_bytes((json.dumps(data)+'\n').encode());files.append({'path':name,'bytes':path.stat().st_size,'sha256':hashlib.sha256(path.read_bytes()).hexdigest()})
 return attribute(root,{'files':files})

class LedgerAttributionTests(unittest.TestCase):
 def test_existing_requires_complete_unchanged_prior_chain(self):
  with tempfile.TemporaryDirectory() as directory:
   result=run_pair(Path(directory),snapshot(True),snapshot(True,'2026-10-08T00:00:01+00:00'))
   self.assertEqual(result['classification'],'ExistingWithEvidence');self.assertFalse(result['asset_acceptance'])
 def test_new_warning_blocks_assets_and_is_not_relabelled_existing(self):
  with tempfile.TemporaryDirectory() as directory:
   result=run_pair(Path(directory),snapshot(),snapshot(True,'2026-10-08T00:00:01+00:00'))
   self.assertEqual(result['classification'],'NewDifferenceBlocksAssets');self.assertFalse(result['existing_attribution']);self.assertTrue(result['changes'])
 def test_native_postgres_trimmed_fractional_timestamp_is_usable(self):
  with tempfile.TemporaryDirectory() as directory:
   before=snapshot();after=snapshot(False,'2026-10-08T00:00:01.12345+00:00')
   after['result']['ledger'][1]['created_at']='2026-10-07T00:00:01.12345+00:00'
   result=run_pair(Path(directory),before,after)
   self.assertEqual(result['classification'],'NoAlertInObservedScope')

 def test_malformed_clock_and_oversized_balance_block_without_exception(self):
  with tempfile.TemporaryDirectory() as directory:
   for kind in ('clock','balance'):
    after=snapshot(False,'2026-10-08T00:00:01+00:00')
    if kind=='clock':after['result']['checked_at']=None
    else:after['result']['ledger'][0]['balance_after']=2**100
    result=run_pair(Path(directory),snapshot(),after)
    self.assertEqual(result['classification'],'Blocked')

 def test_denied_or_incomplete_snapshot_never_means_zero_impact(self):
  with tempfile.TemporaryDirectory() as directory:
   for result in ({'error':'permission denied'},{'checked_at':'2026-10-08T00:00:01+00:00','ledger_chain_mismatches':0}):
    after=snapshot();after['result']=result
    outcome=run_pair(Path(directory),snapshot(),after)
    self.assertEqual(outcome['classification'],'Blocked');self.assertFalse(outcome['asset_acceptance'])

if __name__=='__main__':unittest.main()
