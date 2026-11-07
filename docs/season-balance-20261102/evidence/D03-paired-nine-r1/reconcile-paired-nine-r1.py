from pathlib import Path
import datetime, hashlib, json, os, xml.etree.ElementTree as ET

b=Path(__file__).parent;repo=Path.cwd();out=b/'d03-paired-routes-approved-r1';sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def read_stream(path):
    text=path.read_text('utf-8-sig');decoder=json.JSONDecoder();index=0;rows=[]
    while index<len(text):
        while index<len(text) and text[index].isspace():index+=1
        if index==len(text):break
        row,index=decoder.raw_decode(text,index);rows.append(row)
    return rows
inputs=json.loads((out/'inputs.original.json').read_bytes());attempts_path=out/'observations/attempts.original.jsonl';attempts=read_stream(attempts_path)
assert attempts==inputs['cases'] and len(attempts)==9 and len({r['id'] for r in attempts})==9
routes=read_stream(out/'observations/routes.original.jsonl');assert len(routes)==9
root=ET.parse(out/'routes.trx');counts=root.find('.//{*}Counters');assert counts.get('passed')=='1' and counts.get('failed')=='0' and counts.get('notExecuted')=='0'
source_pins=json.loads((b/'d03-paired-route-preflight-r2/source-pin.original.json').read_bytes());assert all(sha(repo/n)==v for n,v in source_pins.items())
preflight=json.loads((b/'d03-paired-route-preflight-r2/result.json').read_bytes());binary=Path(preflight['binary']);binary_pins=json.loads((b/'d03-paired-route-preflight-r2/binary-manifest.original.json').read_bytes());assert all(sha(binary/n)==v for n,v in binary_pins.items())
path=repo/'docs/season-balance-20261102/D03-BUDGET.json';before=path.read_bytes();budget=json.loads(before)
assert budget['used']==308 and budget['maximum']==317 and budget['reserved_current']==9
assert budget['current_handle']==json.loads((out/'started.original.json').read_bytes())
assert budget['paired_routes_user_reply_received'] and budget['paired_routes_authorization_reference']
for name,used in [('F01',300),('B05',330),('D01',297),('D02',112),('C16',298)]:
    d=json.loads((repo/f'docs/season-balance-20261102/{name}-BUDGET.json').read_bytes());assert d['used']==used and d['current_handle'] is None
(out/'budget-before-reconciliation.original.json').write_bytes(before)
(out/'attempts.canonical.derived.jsonl').write_text(''.join(json.dumps(r,separators=(',',':'))+'\n' for r in attempts),encoding='utf-8')
proof=dict(exit=0,actual_started=9,actual_route_records=9,D03_used=317,D03_maximum=317,D03_remaining=0,source_unchanged=True,binary_unchanged=True,
    attempt_order_and_IDs_match_frozen_plan=True,original_attempts_sha256=sha(attempts_path),original_routes_sha256=sha(out/'observations/routes.original.jsonl'),
    original_multiline_JSON_kept=True,orchestrator_original_error='Original finally reader used splitlines/json.loads on pretty JSON object stream; no execution retry',
    reconciliation_only=True,F01_new=0,B05_new=0,production_changed=False,reconciled_at_utc=datetime.datetime.now(datetime.timezone.utc).isoformat())
assert not (out/'result.json').exists();(out/'result.json').write_text(json.dumps(proof,indent=2)+'\n')
budget.update(used=317,remaining=0,current_handle=None,reserved_current=0,last_result=str(out/'result.json'),prior_budget=str(out/'prior-budget.original.json'),paired_reconciliation_proof=str(out/'result.json'))
temp=path.with_name(path.name+'.reconcile.tmp');assert not temp.exists();temp.write_text(json.dumps(budget,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');os.replace(temp,path)
print(json.dumps(proof))
