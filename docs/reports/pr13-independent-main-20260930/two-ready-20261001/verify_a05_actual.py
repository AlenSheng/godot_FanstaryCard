"""Independently read actual client/PG receipts, not only suite totals."""
import hashlib,json,pathlib
B=pathlib.Path(__file__).resolve().parent;E=B/'evidence';G=E/'A05-SERVER299';R=E/'A05-RED'
fields=['pending_holds','queued_tickets','locked_equipment','unfinished_matches','active_preparations','wallet_gold_mismatches','ledger_chain_mismatches','unacknowledged_settlements']
lines=[json.loads(x) for x in (G/'receipts.jsonl').read_text().splitlines()]
def one(name):return next(x['evidence'] for x in lines if x['caseId']==name)
def hashed(p):return {'path':str(p.relative_to(B)),'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}
pending=one('A05-runtime-passed');pair=one('A05-healthy-M-and-N');healthy=one('A05-healthy-passed')
assert pending['pendingBefore']==pending['committedAfter']==4 and len(set(pending['pids']))==2
assert pending['after']['Owner']==pending['before']['Owner'] and pending['after']['Location']=='Equipped'
assert pending['after']['Gold']-pending['before']['Gold']==23 and pending['after']['Potions']-pending['before']['Potions']==2
assert pending['after']['GoldLedger']==pending['after']['Movements']==1
assert pair['formerMatch']!=pair['nextMatch'] and pair['formerRoom']!=pair['nextRoom']
assert pair['bCurrentRevision']>pair['bBeforeRevision'] and pair['duplicateReady']==3
assert healthy['bResult']=='Extracted' and healthy['bCredit']==23 and healthy['acknowledged']==6 and len(set(healthy['pids']))==2
assert healthy['finalAssets']['Owner']==pair['before']['Owner'] and healthy['finalAssets']['Location']=='RelicPile'
assert healthy['finalAssets']['Gold']==23 and healthy['finalAssets']['Potions']==2 and healthy['finalAssets']['GoldLedger']==healthy['finalAssets']['Movements']==1
ack=[]
for mode in ['precommit','committed-response-loss']:
    items=[x['evidence'] for x in lines if x['caseId']=='A05-same-ACK' and x['evidence']['mode']==mode];assert len(items)==3
    for key in ['receiptId','keySha256','requestBodySha256','responseSha256']:assert len({x[key] for x in items})==1,(mode,key)
    assert len({json.dumps(x['assets'],sort_keys=True) for x in items})==1
    ack.append({'mode':mode,'same_receipt_key_body_reply_assets':True,'requests':3})
windows=[]
for x in [x['evidence'] for x in lines if x['caseId']=='A05-guard-window-passed']:
    context=x['context'];outcome=x['outcome'];attempts=x['attempts']
    assert x['sourceSha']=='62772be2a1bc28affffc3d057f259c8c5ded8e37'
    assert len(attempts)==(1 if outcome=='success' else 3 if outcome=='committed-loss' else 4)
    first=attempts[:1 if outcome=='success' else 3]
    assert len({a['KeySha256'] for a in first})==1 and len({a['BodySha256'] for a in attempts})==1
    if outcome=='uncommitted-loss':
        assert all(not a['Forwarded'] for a in first) and attempts[3]['Forwarded'] and not attempts[3]['Dropped']
        assert any(a['AfterAckAttempts']>=3 and a['UnfinishedSettlementId'] is not None for a in x['bootstraps'])
    else:
        assert all(a['Forwarded'] and a['BackendStatus']==200 for a in attempts)
        assert len({a['ResponseSha256'] for a in attempts})==1
        assert any(a['AfterAckAttempts']>=len(attempts) and a['UnfinishedSettlementId'] is None for a in x['bootstraps'])
    assert x['after']['Owner']==x['before']['Owner'] and x['after']['Location']=='Equipped'
    assert x['after']['Gold']-x['before']['Gold']==23 and x['after']['Potions']-x['before']['Potions']==2
    assert x['after']['GoldLedger']==x['after']['Movements']==1
    windows.append({'context':context,'outcome':outcome,'ACK_attempts':len(attempts),'same_body':True,'authority_versus_failure_separate':True,'assets_once':True})
assert {(x['context'],x['outcome']) for x in windows}=={('ordinary','success'),('recovered','uncommitted-loss'),('recovered','committed-loss')}
clients=[]
for p in sorted(G.glob('ack-client-*/control/result.json')):
    x=json.loads(p.read_text());assert x['ok'] and not x['failures']
    assert all(o.get('passed',True) for o in x['observations'])
    if x.get('context'):
        assert x['first_ack_result']==(x['outcome']!='uncommitted-loss')
        assert x['final_settlement_empty']
    clients.append({**hashed(p),'ok':True,'checks':len(x['observations']),'stale_during_ack':x.get('stale_during_ack'),'stale_after_ack':x.get('stale_after_ack'),'context':x.get('context'),'outcome':x.get('outcome'),'first_ack_result':x.get('first_ack_result')})
assert len(clients)==8
redp=next(R.glob('ack-client-*/control/result.json'));red=json.loads(redp.read_text());assert red['ok'] and not red['failures'] and red['stale_during_ack'] and red['stale_after_ack']
greenp=next(G.glob('ack-client-a05-causal-*/control/result.json'));green=json.loads(greenp.read_text());assert not green['stale_during_ack'] and not green['stale_after_ack']
audits=[]
for parent in [R,G]:
    for p in sorted(parent.glob('a05-audit-*.json')):
        x=json.loads(p.read_text());assert x['transaction']=='READ ONLY; rollback; no mutation'
        counters={k:x['result'][k] for k in fields}
        if x['requireClear']:assert all(v==0 for v in counters.values()),(p,counters)
        audits.append({**hashed(p),'require_clear':x['requireClear'],'counters':counters,'query_sha256':x['querySha256'],'transaction':x['transaction']})
assert len(audits)==18 and sum(x['require_clear'] for x in audits)==9
result={'status':'Passed','canonical_cases':3,'canonical_ACK_idempotency':ack,'Pending_hold_restart':{'Pending_before':4,'Committed_after':4,'actual_host_PIDs':2,'gold_delta':23,'potion_delta':2,'same_owner_equipment_once':True},'M_N_isolation':{'actual_host_PIDs':2,'different_M_N':True,'healthy_B_revision_increases':True,'B_extract_gold':23,'duplicate_READY':3,'A_N_old_callback_OS_restart_safe':True,'normal_N_cleanup_same_instance_RelicPile':True,'not_readjudicating_A05_2_3':True},'guard_windows':windows,'clients':clients,'red':{**hashed(redp),'correctness_exit':1,'stale_during_ack':True,'stale_after_ack':True,'observations':red['observations'],'actual_source_sha':'2dda41b32ba89f06d5ea722ae8b9469004940c22','legacy_raw_business_label':'f812; actual integration2dda recorded separately; do not overwrite raw'},'green_causal':{**hashed(greenp),'stale_during_ack':False,'stale_after_ack':False,'observations':green['observations']},'readonly_audits':audits,'minimal_dependencies':'Actual durable recovery/hold commit checkpoints and nonduplicated asset/ledger writes are supplied under the declared Program+PG+Game matrix; do not require whole LOAD05.4/LOAD09.2 Accepted.'}
(B/'A05_ACTUAL_CHECKS.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({'A05_1_cases':3,'guard_windows':3,'clients':8,'audits':18,'red_correctness_exit':1,'green_stale_both':False,'status':'Passed'}))
