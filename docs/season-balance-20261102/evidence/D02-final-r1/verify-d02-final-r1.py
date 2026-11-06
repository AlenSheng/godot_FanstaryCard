from pathlib import Path
import hashlib,json,xml.etree.ElementTree as ET

base=Path(__file__).parent
sources=['d02-duels-inspection-r2.derived.json','d02-routes-inspection-r1.derived.json','d02-rebuild-inspection-Priest-Mage-Guardian-r1.derived.json','d02-gate-inspection-r1.derived.json']
for name in sources:
    data=json.loads((base/name).read_bytes())
    for path,expected in data.get('source_sha256',{}).items():assert hashlib.sha256((base/path).read_bytes()).hexdigest()==expected
audit=json.loads((base/'d02-final-requirement-audit-r1.derived.json').read_bytes());assert audit['D02_complete'] and len(audit['requirements'])==6 and all(x['status']=='achieved' for x in audit['requirements'])
gate=base/'d02-pvp-gates-r1';rows=[json.loads(x) for x in (gate/'observations/cases.original.jsonl').read_text('utf-8').splitlines()];assert len(rows)==3
for row in rows:
    assert row['blocked700']['Elapsed']=='00:00:00.7000000' and row['blocked400']['Elapsed']=='00:00:01.2000000' and row['final']['Elapsed']=='00:00:01.3000000'
    assert row['accepted800']['CombatActionId'].startswith('1:') and row['accepted500']['CombatActionId'].startswith('2:') and row['rejections_preserve_full_state'] and row['final']['Duels']==[]
for stage in ['d02-rebuild-pg-mage-r1','d02-rebuild-pg-guardian-r1']:
    proof=json.loads((base/stage/'result.json').read_bytes());assert proof['exit']==0 and proof['cleanup_verified'] and proof['actual_match_attempts']==2
    counters=next(e.attrib for e in ET.fromstring((base/stage/'cases.trx').read_bytes()).iter() if e.tag.endswith('Counters'));assert counters['passed']=='1' and counters['failed']==counters['notExecuted']=='0'
budget=json.loads(Path('docs/season-balance-20261102/D02-BUDGET.json').read_bytes());assert budget['used']==100 and budget['remaining']==200 and budget['current_handle'] is None
assert not (base/'d02-rebuild-pg-r1/cases.trx').exists();assert json.loads((base/'d02-rebuild-owned-cleanup-r1/stdout.original.json').read_bytes())['still_present']==[]
print('D02 all six requirements, archived-source hashes, exact gate clocks, actual PG receipts and cleanup verified;100/300, whole goal remains active')
