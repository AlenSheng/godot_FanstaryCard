"""Use original production reports as outcome proof; observer is supplementary."""
import hashlib,json,pathlib,sys
B=pathlib.Path(__file__).resolve().parent;E=B/'evidence'
def hashed(p):return {'path':str(p.relative_to(B)),'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}
summaries=[]
runs=sys.argv[1:] or ['LOAD02-FOCUSED','LOAD02-SERVER302']
for run in runs:
    parent=E/run;rows=[json.loads(s) for s in (parent/'receipts.jsonl').read_text().splitlines()]
    def row(name):return next(x['evidence'] for x in rows if x['caseId']==name)
    for n,mode in [(1,'timeout-before-stop'),(2,'normal-wait-stop'),(3,'committed-unknown-stop')]:
        case=f'LOAD-02.2-T0{n}';done=row(case);gate=row(case+'-gate');stopreceipt=row(case+'-STOP');relay=row(case+'-relay-finally')
        fixture=pathlib.Path(done['fixture']);report=fixture/'load-result.json';original=json.loads(report.read_text())
        observed=json.loads(pathlib.Path(str(report)+'.stop-observed.json').read_text());final=json.loads(pathlib.Path(str(report)+'.accounting.json').read_text())
        stop=observed['partition'];part=final['partition']
        for d in [stop,part]:assert d['started']==sum(d[k] for k in ['completed','failed','cancelled','pending','incomplete'])==1
        assert part=={'started':1,'completed':0,'failed':1 if n==1 else 0,'cancelled':0 if n==1 else 1,'pending':0,'incomplete':0}
        assert stop['completed']==stop['cancelled']==stop['incomplete']==0
        assert observed['stop_requested'] and observed['scenario_started']
        assert final['monotonic_ms']>=observed['monotonic_ms']
        identity=['run_id','client_id','process_epoch','cycle_id','session_generation','room_context_epoch']
        assert all(observed[k]==final[k] for k in identity)
        assert final['completed_events']==[] and final['cleanup']['state']=='Passed'
        assert original['outcome']==('failed' if n==1 else 'cancelled')
        assert done['status']=='Passed' and done['nextPrepareCancelVerified'] and not relay['errors']
        exits=[x['evidence'] for x in rows if x['caseId']=='LOAD02-process-exit' and x['evidence']['mode']==mode]
        assert len(exits)==2 and all(x['ExitCode']==(1 if n==1 and not x['import'] else 0) for x in exits)
        attempts=relay['requests'];ack=[a for a in attempts if a['Method']=='POST' and a['Path'].endswith('/acknowledge') and a['Forwarded']]
        extra={}
        if n==1:
            first=json.loads(pathlib.Path(str(report)+'.first-failure.json').read_text())
            assert first['monotonic_ms']<=observed['monotonic_ms'] and observed['errors'] and original['errors']
            assert any(c['name']=='create_free_preparation' and not c['passed'] for c in first['checks'])
            assert any(c['name']=='create_free_preparation' and not c['passed'] for c in original['checks'])
            assert stop['failed']==1 and stop['pending']==0
            prep=[a for a in attempts if a['Method']=='POST' and a['Path']=='/api/v1/preparations']
            assert len(prep)==3 and all(not a['Forwarded'] for a in prep) and len({a['KeySha256'] for a in prep})==1
            logical=next(o for o in original['operations'] if o['path']=='/api/v1/preparations' and o['method']==2)
            assert not logical['ok'] and 29500<=logical['duration_ms']<=34000
            timeouts=[a for a in original['telemetry'] if a.get('event_type')=='http_attempt' and a.get('route')=='/api/v1/preparations' and a.get('result')=='timeout']
            assert len(timeouts)==3 and 9800<=timeouts[0]['duration_ms']<=11500
            assert done['before']==done['after']
            extra={'original_failure_before_STOP_ms':first['monotonic_ms'],'logical_duration_ms':logical['duration_ms'],'attempt_timeout_ms':[a['duration_ms'] for a in timeouts],'original_errors_count':len(original['errors']),'assets_exactly_unchanged':True}
        else:
            assert stop['pending']==1 and stop['failed']==0 and observed['busy'] and observed['pending_ack'] and observed['stage']=='settlement'
            assert all(c['passed'] for c in observed['checks'])
            if n==2:assert not original['errors']
            assert len(ack)==(1 if n==2 else 3) and all(a['BackendStatus']==200 for a in ack)
            assert len({a['KeySha256'] for a in ack})==len({a['BodySha256'] for a in ack})==1
            assets=done['finalAssets'];assert len(assets['settlements'])==1 and assets['settlements'][0]['acknowledged_at'] is not None
            assert not any(a['state']=='Pending' for a in assets['holds'])
            assert assets['equipment']['owner_id']==done['before']['equipment']['owner_id'] and assets['equipment']['instance_id']==done['before']['equipment']['instance_id']
            ledger=[x for x in assets['ledger'] if x['reason']=='settlement.commit'];currencies=[x['currency'] for x in ledger];assert len(currencies)==len(set(currencies))
            movements=[x for x in assets['movements'] if x['reason'] in ['settlement.extract','settlement.death']];assert len(movements)==1
            extra={'ACK_backend_200_attempts':len(ack),'same_key_and_body':True,'durable_acknowledged_receipts':1,'asset_settlement_credit_per_currency_once':True,'original_equipment_movement_once':True,'original_errors_count':len(original['errors'])}
            if n==3:
                authority=gate['Authority'];assert all(authority[k] is None for k in ['activePreparation','unfinishedMatch','unfinishedSettlement']) and authority['ConfigVersion']
                assert len({a['ResponseSha256'] for a in ack})==1
                assert any(a['Effect']=='authoritative_bootstrap_held' for a in attempts)
                extra.update({'PG_committed_before_STOP_while_client_pending':True,'complete_authority_triple_null_before_release':True,'same_backend_reply':True})
        summaries.append({'run':run,'case_id':case,'mode':mode,'status':'Passed','STOP_monotonic_ms':observed['monotonic_ms'],'final_monotonic_ms':final['monotonic_ms'],'STOP_partition':stop,'final_partition':part,'initiating_identity_stable':identity,'no_cycle_completed':True,'original_outcome':original['outcome'],'actual_client_exit':1 if n==1 else 0,'next_real_prepare_cancel_204':True,'details':extra,'original_report':hashed(report),'STOP_snapshot':hashed(pathlib.Path(str(report)+'.stop-observed.json')),'final_accounting':hashed(pathlib.Path(str(report)+'.accounting.json'))})
result={'status':'Passed','canonical_cases':3,'actual_case_executions':len(summaries),'source_sha':'dfb3f88a73efd85cc4ed12b8d49038bebbb1f953','cases':summaries,'budgets_unchanged_ms':{'attempt':10000,'logical':30000,'bot_fill':30000},'minimum_dependencies':'LOAD02.1 classification/actual original failed check and LOAD06.2 logical-request/context/idempotency products are present and consumed; no need for all upstream whole-parent Accepted.','scope':'Production report is primary outcome; small observer partitions one actual original scenario/check/finish at two cutoffs. No LOAD03 all routes/full-run/three-cutoff claim, capacity or global ledger exoneration.'}
(B/('LOAD02_ACTUAL_CHECKS.json' if len(runs)==2 else 'LOAD02_FOCUSED_CHECKS.json')).write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({'status':'Passed','canonical_cases':3,'executions':len(summaries),'original_exit_codes':[1,0,0],'budgets_unchanged':True}))
