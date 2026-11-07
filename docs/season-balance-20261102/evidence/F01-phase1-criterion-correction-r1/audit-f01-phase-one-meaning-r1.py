from pathlib import Path
import hashlib,json

b=Path(__file__).parent;repo=Path.cwd();out=b/'f01-phase-one-meaning-r1.derived.json';assert not out.exists()
design=repo/'docs/season-balance-20261102/source/Season_Balance_Design.md'
line=next((n,text) for n,text in enumerate(design.read_text('utf-8').splitlines(),1) if '| 第1至3日 |' in text)
assert '得到可用绿蓝装备' in line[1] and '五' not in line[1]
groups={}
for scope,root in [('default20',b/'f01-calendar-r1/observations'),('owned-support20',b/'f01-support-week-r1/observations')]:
    records=[]
    for path in root.rglob('after.original.json'):
        d=json.loads(path.read_bytes());s=d['scheduled']
        if (scope=='default20' and not s['Actor'].startswith('F01-novice-')):continue
        gear=[g for g in d['inventory']['Equipments'] if g['Location'] in ['Inventory','Equipped'] and g['Quality'] in ['Green','Blue']]
        records.append(dict(actor=s['Actor'],day=s['Day'],hour=s['Hour'],case=s['Id'],slots=sorted({g['Slot'] for g in gear}),source=str(path),sha256=hashlib.sha256(path.read_bytes()).hexdigest()))
    summaries=[]
    for actor in sorted({r['actor'] for r in records}):
        own=sorted([r for r in records if r['actor']==actor],key=lambda r:(r['day'],r['hour']))
        first_any=next((dict(attempt=n+1,**r) for n,r in enumerate(own) if r['slots']),None)
        first_five=next((dict(attempt=n+1,**r) for n,r in enumerate(own) if len(r['slots'])==5),None)
        summaries.append(dict(actor=actor,first_any_usable_green_blue=first_any,first_all_five_green_blue=first_five,day1_3_any_gear_observed=first_any is not None and first_any['day']<=3,observed_attempts=len(own)))
    groups[scope]=summaries
proof=dict(original_design_sha256=hashlib.sha256(design.read_bytes()).hexdigest(),source_line=line[0],source_requirement=line[1],
    source_does_not_require_complete_five_slots_by_day3=True,reporting_correction='The original phase1 target asks for usable Green/Blue gear, not a complete five-slot set. The stricter five-slot observation remains a separate reported metric; day5 by itself is not a phase1 target violation.',
    cohorts=groups,no_new_gameplay_starts=True,D03_accepted_not_inferred=True)
out.write_text(json.dumps(proof,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps(dict(source_line=line[0],requires_complete_five_by_day3=False,results={k:[dict(actor=r['actor'],first_any_day=r['first_any_usable_green_blue']['day'] if r['first_any_usable_green_blue'] else None,first_any_attempt=r['first_any_usable_green_blue']['attempt'] if r['first_any_usable_green_blue'] else None,first_five_day=r['first_all_five_green_blue']['day'] if r['first_all_five_green_blue'] else None) for r in v] for k,v in groups.items()})))
