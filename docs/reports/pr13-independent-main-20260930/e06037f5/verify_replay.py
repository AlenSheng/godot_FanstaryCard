"""Assert recorded real-entry outputs using the fixed production classifier."""
import argparse,json,math,pathlib,re,sys
p=argparse.ArgumentParser();p.add_argument('--source',required=True);p.add_argument('--evidence',required=True);a=p.parse_args()
src=pathlib.Path(a.source).resolve();root=pathlib.Path(a.evidence).resolve();sys.path.insert(0,str(src/'tools'))
from gameplay_load_validation import classify_stop
def read(path):return json.loads(path.read_text())
results=[]
for fixture in ('finite-overflow','archive-match-list','archive-type-list'):
    r=read(root/'original-three'/fixture/'receipt.json');assert r['unhandled_exception'] is None and r['child_reaped']
    assert r['ownership_invalid']==r['event_loss']==0
    w=r['window'];cycle=r.get('cycle_counts');archive_errors=r.get('archive_errors',[])
    invalid=bool(r['ownership_invalid'] or r['event_loss'] or w['invalid_metric_count'] or r['population']['invalid_schema_count'] or archive_errors or (cycle and cycle['evidence_errors']))
    decision=classify_stop('invalid_evidence:invalid_telemetry' if invalid else 'duration_limit')
    checks=dict(no_exception=True,owned_and_sequence_intact=True,child_reaped=True)
    if fixture=='finite-overflow':
        checks.update(finite_mean_exact=math.isfinite(w['http']['mean_ms']) and w['http']['mean_ms']==1e308,
            all_samples_retained=w['sample_count']==w['error_count']==w['valid_latency_count']==w['http']['count']==2,
            no_fabricated_zero_latency=w['http']['min_ms']==w['http']['max_ms']==w['http']['p95_ms']==1e308,
            quality_not_promoted=w['latency_sample_quality']['http']=='insufficient',no_false_invalid=w['invalid_metric_count']==0,
            no_load_pass=decision['exit_code']==1 and not decision['passed'])
    else:
        expected='invalid_business_match_type' if fixture=='archive-match-list' else 'invalid_event_type'
        checks.update(archive_read_clean=not archive_errors,invalid_reason=expected in cycle['evidence_errors'],explicit_invalid_exit3=decision['exit_code']==3 and not decision['passed'],no_false_completions=cycle['final']['completed_cycles']==cycle['final']['acknowledgements']==0)
    assert all(checks.values()),(fixture,checks)
    results.append(dict(fixture=fixture,checks=checks,decision=decision,receipt='original-three/'+fixture+'/receipt.json',sample_count=w['sample_count'],error_count=w['error_count'],http=w['http'],sample_quality=w['latency_sample_quality']['http'],cycle_errors=cycle['evidence_errors'] if cycle else None))
old=read(root/'old-five/REPORT.json');assert old['unhandled_exceptions']==0 and old['invalid_failures']==5 and old['all_reaped'];assert all(r['decision']['exit_code']==3 and not r['decision']['passed'] for r in old['records'])
canonical=read(root/'load01/report.json');assert canonical['source_sha']=='e06037f58738d0fbff86090e86d8bd06f8608e04';assert canonical['executed']==canonical['passed']==12 and canonical['failed']==canonical['skipped']==0
boundaries=read(root/'boundaries/REPORT.json');assert boundaries['passed']==5 and boundaries['failed']==0 and boundaries['all_reaped'];assert all(all(r['checks'].values()) for r in boundaries['records'])
assert re.search(r'Ran 122 tests in .*\n\nOK\s*$',(root/'C-PY.log').read_text())
commands=[read(p) for p in root.glob('*.command.json')];assert all(c['source_sha']=='e06037f58738d0fbff86090e86d8bd06f8608e04' and c['exit_code']==0 for c in commands)
children=read(root/'load01/cleanup.json')['owned_children']+old['records']+boundaries['records']+[read(root/'original-three'/f/'receipt.json') for f in ('finite-overflow','archive-match-list','archive-type-list')]
assert len(children)==17 and all(c.get('reaped',c.get('child_reaped',False)) for c in children)
output=dict(integration_sha='e06037f58738d0fbff86090e86d8bd06f8608e04',original_three=results,old_five_invalid_exit3=5,canonical=dict(executed=12,passed=12,skipped=0,not_new_adjudications_of_accepted_tasks=True),regression=dict(executed=122,passed=122,skipped=0),boundaries=[dict(fixture=r['fixture'],checks=r['checks'],decision=r['decision']) for r in boundaries['records']],dedicated_children_reaped=17,passed=True,exit_code_semantics='Probe/verification process exit0 checks replay; production classify_stop returns invalid3 for bad archive or incomplete1 for valid small diagnostic. Full network CLI was not run.',Accepted=False)
(root/'REPLAY_CHECKS.json').write_text(json.dumps(output,indent=2,allow_nan=False)+'\n')
print(json.dumps(output,allow_nan=False))
