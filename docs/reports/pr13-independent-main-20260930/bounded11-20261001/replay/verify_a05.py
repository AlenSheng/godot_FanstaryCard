"""Derive nonsensitive assertions from actual owned PG/client receipts."""
import hashlib,json,pathlib
B=pathlib.Path(__file__).resolve().parent
E=B/'a05/evidence'
fields=['pending_holds','queued_tickets','locked_equipment','unfinished_matches','active_preparations','wallet_gold_mismatches','ledger_chain_mismatches','unacknowledged_settlements']
focused=E/'A05-FOCUSED'
lines=[json.loads(x) for x in (focused/'receipts.jsonl').read_text().splitlines()]
def row(name):return next(x['evidence'] for x in lines if x['caseId']==name)
healthy=row('A05-healthy-passed');pair=row('A05-healthy-M-and-N');pending=row('A05-runtime-passed')
assert pair['formerMatch']!=pair['nextMatch'] and pair['formerRoom']!=pair['nextRoom']
assert pair['bCurrentRevision']>pair['bBeforeRevision'] and pair['duplicateReady']==3
assert healthy['bResult']=='Extracted' and healthy['bCredit']==23 and healthy['acknowledged']==6
assert len(set(healthy['pids']))==2 and len(set(pending['pids']))==2
assert healthy['finalAssets']['Gold']==23 and healthy['finalAssets']['Potions']==2
assert healthy['finalAssets']['GoldLedger']==healthy['finalAssets']['Movements']==1
assert healthy['finalAssets']['Owner']==pair['before']['Owner']
assert pair['afterM']['Location']=='Equipped' and healthy['finalAssets']['Location']=='RelicPile'
assert pending['pendingBefore']==pending['committedAfter']==4
assert pending['after']['Gold']-pending['before']['Gold']==23
assert pending['after']['Potions']-pending['before']['Potions']==2
assert pending['after']['Owner']==pending['before']['Owner'] and pending['after']['Location']=='Equipped'
assert pending['after']['GoldLedger']==pending['after']['Movements']==1
acks=[]
for mode in ['precommit','committed-response-loss']:
    items=[x['evidence'] for x in lines if x['caseId']=='A05-same-ACK' and x['evidence']['mode']==mode]
    assert len(items)==3
    for key in ['receiptId','keySha256','requestBodySha256','responseSha256']:
        assert len({x[key] for x in items})==1,(mode,key)
    assert len({json.dumps(x['assets'],sort_keys=True) for x in items})==1
    acks.append(dict(mode=mode,requests=3,same_receipt_key_body_response=True,assets_identical=True))
audits=[]
for p in sorted(focused.glob('a05-audit-*.json'))+sorted((E/'A05-CAUSAL').glob('a05-audit-*.json')):
    d=json.loads(p.read_text());assert d['transaction']=='READ ONLY; rollback; no mutation'
    counters={k:d['result'][k] for k in fields}
    if d['requireClear']:assert all(v==0 for v in counters.values()),(p,counters)
    audits.append(dict(path=str(p.relative_to(B)),bytes=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest(),require_clear=d['requireClear'],counters=counters,query_sha256=d['querySha256'],transaction=d['transaction']))
assert len(audits)==10 and sum(x['require_clear'] for x in audits)==5
causal=next((E/'A05-CAUSAL').glob('ack-client-*/control/result.json'))
d=json.loads(causal.read_text())
assert d['ok'] and d['counterexample_confirmed'] and d['stale_during_ack'] and d['stale_after_ack']
assert not d['failures']
obs=d['observations']
assert all(x.get('passed',True) for x in obs)
assert any(x.get('check')=='actual post-ACK Bootstrap confirms completion' for x in obs)
client_results=[]
for p in focused.glob('ack-client-*/control/result.json'):
    d=json.loads(p.read_text());assert d['ok'] and not d['failures']
    client_results.append(dict(path=str(p.relative_to(B)),sha256=hashlib.sha256(p.read_bytes()).hexdigest(),ok=d['ok'],checks=len(d['observations']),failures=d['failures']))
assert len(client_results)==4
result=dict(status='PassedForA05_2_3_contracts',canonical_target_cases=6,healthy=dict(different_M_N=True,B_continues_M=True,B_revision_increases=True,original_READY_duplicates=3,OS_host_pids=2,B_completes_extraction=True,A_N_survives_old_callbacks_and_OS_restart=True,total_acknowledged=6,A_gold=23,A_potions=2,A_gold_ledger=1,A_item_movements=1,original_equipment_instance_preserved=True,allowed_location_transfer='InMatchEquipped -> Equipped after M -> RelicPile after normal N disconnect-death cleanup; no duplicate credit'),pending=dict(OS_host_pids=2,pending_before=4,committed_after=4,same_owner=True,gold_delta=23,potion_delta=2,gold_ledger=1,item_movements=1,location_after='Equipped'),ACK_idempotency=acks,client_results=client_results,readonly_audits=audits,retained_A05_1_counterexample=dict(actual_exit_code=1,correctness_assertion_status='Failed',counterexample_confirmed=True,stale_during_ack=True,stale_after_ack=True,after_asset_audit_clear=True,raw_result_path=str(causal.relative_to(B)),raw_result_sha256=hashlib.sha256(causal.read_bytes()).hexdigest(),observations=obs,scope='A05.1 outside adjudication; preserve Partial; does not prove an A05.2 route or A05.3 asset violation'),historical_focused='3Passed/1Failed preserved in fixed 80687833 packet; current focused4Passed does not erase it')
(B/'A05_CHECKS.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
print(json.dumps(dict(status=result['status'],target_cases=6,client_results=4,readonly_audits=10,causal_correctness_exit=1)))
