import json,pathlib,os,re
B=pathlib.Path(__file__).resolve().parent
P=B/'load02/evidence'
results=[]
def report(mode):return json.loads(next((P/mode/'runs').glob('*/report.json')).read_text())
dimensions={'execution','evidence','load','gameplay','performance','cleanup'}
rows=json.loads((P/'independent_modes.json').read_text())
for row in rows:
    assert row['exit_code']==row['expected'],row
    if row['mode']=='emergency':
        text=next((P/'emergency/runs').glob('*/report.emergency.txt')).read_text()
        assert 'report_write_failed' in text or 'report write' in text.lower() or 'write failure' in text
        results.append(dict(mode='emergency',exit_code=3,emergency_present=True,emergency_text=text));continue
    d=report(row['mode'])
    assert set(d['result_dimensions']['dimensions'])==dimensions
    assert not d['full_acceptance_passed']
    if row['expected']!=0:assert not d['acceptance_passed']
    cleanup=json.loads((P/row['mode']/'cleanup-real-time.json').read_text())
    for child in cleanup['children']:
        assert child['returncode'] is not None
        assert not pathlib.Path('/proc',str(child['pid'])).exists()
    results.append(dict(mode=row['mode'],exit_code=row['exit_code'],dimensions=d['result_dimensions'],first_trigger=d['first_trigger'],all_triggers=d['all_triggers'],process_cleanup_complete=d['process_cleanup_complete'],business_cleanup_verified=d['business_cleanup_verified'],process_exits=d['process_exits'],forced_termination_pids=d['forced_termination_pids'],children_reaped=True))
time_limit=report('time_limit')
assert time_limit['result_dimensions']['dimensions']['execution']=='Passed'
assert time_limit['result_dimensions']['dimensions']['load']=='Failed'
prior=report('timeout_before')
assert prior['result_dimensions']['dimensions']['gameplay']=='Failed'
assert {'operator_stop_file','final_business_failure'}<=set(prior['all_triggers'])
assert prior['final_clients'][0]['errors']
assert prior['samples'][0]['window']['error_count']==1
corrupt=report('redline_corrupt')
assert corrupt['outcome']['exit_code']==3
assert corrupt['result_dimensions']['dimensions']['performance']=='Failed'
assert corrupt['result_dimensions']['dimensions']['evidence']=='Failed'
assert 'final_audit_loss' in corrupt['all_triggers']
assert report('cleanup_unknown')['result_dimensions']['dimensions']['cleanup']=='Unknown'
assert report('exit7')['process_exits'][0]['after_stop']==7
assert all(r['compatible'] for r in json.loads((P/'caller-integration/receipt.json').read_text()))
assert json.loads((P/'hang-with-sentinel/ownership-receipt.json').read_text())['external_sentinel_alive_after_coordinator']
L=B/'load03/evidence'
sequences=json.loads((L/'sequence/receipts.json').read_text());extras=json.loads((L/'sequence/additional-criteria.json').read_text())
phases=json.loads((L/'phase/receipts.json').read_text());sticky=json.loads((L/'coordinator-sticky-verified/receipt.json').read_text())
assert len(sequences)==3 and all(r['passed'] for r in sequences)
assert len(extras)==4 and all(r['passed'] for r in extras)
assert len(phases)==7 and all(r['passed'] for r in phases)
assert sticky['caller_exit']==3 and sticky['first_window_lost']==1 and sticky['evidence_dimension']=='Failed'
R=B/'b02/evidence'
exact=[json.loads(x) for x in (R/'exact/cases.jsonl').read_text().splitlines()]
negative=json.loads((R/'negative-case.json').read_text());godot=json.loads((R/'exact-godot.json').read_text())
assert len(exact)==11 and all(r['status']=='Passed' for r in exact)
assert negative['status']=='Passed' and all(r['matched'] and r['exit_code']==1 for r in negative['actual'])
assert godot['ok'] and not godot['failures']
result=dict(status='Passed',LOAD02=dict(canonical_case_count=9,model_modes=results,before_STOP_business_error_retained=True,unrelated_coordinator_sentinel_survives=True),LOAD03=dict(canonical_case_count=6,sequence_canonical=sequences,sequence_extra_count=4,phase_canonical_count=3,phase_extra_count=4,sticky=sticky),B02=dict(canonical_case_count=12,negative=negative,exact_cases=exact,godot=godot),PG_full_suites='pending; not asserted by this short replay validator')
(B/'SHORT_REPLAY_CHECKS.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(dict(status='Passed',canonical_counts=dict(LOAD02=9,LOAD03=6,B02=12))))
