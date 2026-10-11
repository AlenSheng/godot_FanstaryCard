import base64,hashlib,importlib.util,json,time
from pathlib import Path
B=Path(__file__).parent;P=B/'information-default-render-full972-r2';O=B/'information-full-R2-manager-proof-and-pool-release';assert not O.exists();O.mkdir()
spec=importlib.util.spec_from_file_location('information_terminal_transport',B/'b08_lifecycle_r4_G_transport_gc_r2.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);m.OUT=O;base=m.load('backup_failed_tuning_equivalence_r1_to_G.py')
deadline=time.monotonic()+14400
while not (P/'complete.json').exists():
 assert time.monotonic()<deadline
 print(json.dumps({'waiting_for_complete_original972_G_rows':True,'no_native_dispatch':True}),flush=True);time.sleep(20)
complete=json.loads((P/'complete.json').read_bytes());assert complete['ok'] and complete['rows']==972 and complete['PNGs']==54
plan=json.loads((B/'b09-information-default-render-full972-r2-runners/plan.json').read_bytes());receipts=[]
def remote(code):
 c=base.connect()
 try:
  ch=c.get_transport().open_session(timeout=45);ch.exec_command('python3 -');ch.sendall(code.encode());ch.shutdown_write();raw,_,err=m.receive(ch);assert not err;return json.loads(raw)
 finally:c.close()
for unit in plan['units']:
 L=P/unit['locale'];r=json.loads((L/'local-backup-receipt.json').read_bytes());assert r['ok'] and r['actual_rows']==486 and r['original_PNG_CRC_verified']==27 and r['all_original_members_SHA_verified'] and r['archive_gzip_CRC_verified'];assert m.sha(Path(r['local_archive']))==r['sha256']
 manifest=json.loads((L/'delivery-manifest.json').read_bytes());assert hashlib.sha256((L/'delivery-manifest.json').read_bytes()).hexdigest()==r['manifest_sha256']
 for row in manifest['files']:
  p=Path(r['local_directory'])/row['path'];assert p.stat().st_size==row['bytes'] and m.sha(p)==row['sha256']
 code=(B/'read_information_R5_actual_PID1_complete_original_readonly_once.py').read_text(encoding='utf-8').replace("A='b09-information-default-render-smoke-r5-20261011'",'A='+repr(unit['attempt'])).replace("'rows':18,'PNGs':9","'rows':486,'PNGs':27")
 v=remote(code);assert v['ok'];raw=base64.b64decode(v['terminal_journal_base64'],validate=True);proof=v['proof'];assert len(raw)==proof['terminal_journal_bytes'] and hashlib.sha256(raw).hexdigest()==proof['terminal_journal_sha256'] and proof['actual_PID1_unique_invocation_success'];T=O/unit['locale'];T.mkdir();(T/'terminal-journal.original.jsonl').write_bytes(raw);(T/'actual-PID1-proof.json').write_text(json.dumps(proof,indent=2)+'\n',encoding='utf-8');receipts.append({'unit':unit,'G_originals':r,'actual_PID1':proof});print(json.dumps({'actual_PID1_and_G_closed':unit['locale'],'rows':486,'visual_review_pending':True}),flush=True)
code=r'''
import fcntl,json,subprocess
from pathlib import Path
B=Path('/home/ubuntu/pr13-acceptance-20261009');H=B/'evidence/pool-render-segments-r3/scheduling-hold.json';P=B/'evidence/information-default-render-full972-r2';R=P/'pool-hold-release-after-all972-G.json'
with (B/'evidence/shared-resource-coordination.lock').open('a') as lock:
 fcntl.flock(lock.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB);hold=json.loads(H.read_bytes());assert hold['active'] and hold['owner']=='pr13-information-default-render-full972-r2' and not R.exists()
 for row in RECEIPTS:
  a=row['unit']['attempt'];e=B/'evidence'/a;v=json.loads((e/'run-result.json').read_bytes());assert v['ok'] and v['rows']==486 and v['PNGs']==27 and v['owned_container_removed'];state=dict(x.split('=',1) for x in subprocess.check_output(['systemctl','show','pr13-cap-'+a,'--property=MainPID,ActiveState,ExecMainStatus'],text=True).splitlines());assert state['MainPID']=='0' and state['ActiveState']=='inactive' and state['ExecMainStatus']=='0';assert json.loads((e/'run-started.json').read_bytes())['invocation_id']==row['actual_PID1']['invocation_id']
 (P/'full972-hold-before-release.original.json').write_bytes(H.read_bytes());receipt={'ok':True,'exact_owner':hold['owner'],'complete_G_rows':972,'complete_G_PNGs':54,'actual_PID1_proofs':RECEIPTS,'visual_review_pending':True,'MAIN_accepted':False};R.write_text(json.dumps(receipt,indent=2)+'\n');hold.update(active=False,released_reason='Both original full locale matrices SHA and gzip/PNG CRC closed on G with actual PID1 unique successful invocations; visual review pending');tmp=H.with_name('full972-complete-release.tmp');assert not tmp.exists();tmp.write_text(json.dumps(hold)+'\n');tmp.replace(H);print(json.dumps({'ok':True,'exact_owned_pool_hold_released':True,'old_pool_can_resume':True,'rows':972,'PNGs':54,'visual_review_pending':True,'MAIN_accepted':False}))
'''
(O/'release-intent.json').write_text(json.dumps({'no_automatic_retry':True,'exact_owner':'pr13-information-default-render-full972-r2','receipts':receipts},indent=2)+'\n',encoding='utf-8');v=remote('RECEIPTS='+repr(receipts)+'\n'+code);assert v['ok'];(O/'release-result.json').write_text(json.dumps(v,indent=2)+'\n',encoding='utf-8');print(json.dumps(v),flush=True)
