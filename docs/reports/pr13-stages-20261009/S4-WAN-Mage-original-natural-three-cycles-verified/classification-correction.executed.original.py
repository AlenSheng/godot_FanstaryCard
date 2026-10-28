import collections,hashlib,json
from pathlib import Path
E=Path('/home/ubuntu/pr13-acceptance-20261009/evidence/WAN-Mage-natural3-r3-original-review')
original=E/'natural-baseline-review.original.json';before=hashlib.sha256(original.read_bytes()).hexdigest()
v=json.loads(original.read_bytes());rows=[json.loads(l) for l in (E/'originals/player.original.json.telemetry.jsonl').read_bytes().splitlines()]
realtime=[r for r in rows if r.get('type')=='realtime'];counts=dict(collections.Counter(r.get('result') for r in realtime))
# The actual registered client names successful completed responses "completed".
failed=[{'action':r.get('action'),'result':r.get('result'),'response_type':r.get('response_type'),'request_id':r.get('request_id')} for r in realtime if r.get('result')!='completed']
responses=dict(collections.Counter(r.get('response_type') for r in realtime));v['realtime_non_success_rows']=failed
v['actual_realtime_result_counts']=counts;v['actual_realtime_response_type_counts']=responses
v['prior_postcollection_wrong_literal_classification_preserved']=True;v['prior_original_review_SHA256']=before
v['classification_revision_only_no_latency_or_original_raw_change']=True;v['new_gameplay_runs']=0
p=E/'natural-baseline-review-result-semantics-r2.original.json';assert not p.exists();p.write_text(json.dumps(v,indent=2)+'\n')
assert hashlib.sha256(original.read_bytes()).hexdigest()==before
print(json.dumps(v))
