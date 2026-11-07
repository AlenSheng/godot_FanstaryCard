from pathlib import Path

b=Path(__file__).parent;source=(b/'audit-f01-existing-same-tier-efficiency-r1.py').read_text('utf-8')
source=source.replace('f01-existing-same-tier-efficiency-r1.derived.json','f01-existing-same-tier-efficiency-r2.derived.json')
old='assert len(rows)==84 and all(s==signatures[0] for s in signatures)'
new="""assert len(rows)==84
non_class_keys=[k for k in signatures[0] if k not in ['deck','potions']]
assert all(all(s[k]==signatures[0][k] for k in non_class_keys) for s in signatures)
class_decks={}
for actor in sorted({r['actor'] for r in rows}):
    own=[s for r,s in zip(rows,signatures) if r['actor']==actor]
    assert all(s['deck']==own[0]['deck'] for s in own)
    class_decks[actor]=own[0]['deck']
for row,sig in zip(rows,signatures):row['initial_potions']=sig['potions']
potion_counts={actor:dict(collections.Counter(r['initial_potions'] for r in rows if r['actor']==actor)) for actor in class_decks}
assert all(v==next(iter(potion_counts.values())) for v in potion_counts.values())"""
assert old in source;source=source.replace(old,new)
source=source.replace('all_selected_inputs_equal_after_class_identity_normalization=True','non_class_gear_level_inputs_matched=True,class_specific_decklists=class_decks,initial_potion_counts_matched=potion_counts')
old="out.write_text(json.dumps(proof,indent=2)+'\\n');print(json.dumps({k:v for k,v in proof.items() if k not in ['normalized_input','raw_rows']}))"
new="""strata=[]
for potions in sorted({r['initial_potions'] for r in rows}):
    values=[]
    for actor in class_decks:
        own=[r for r in rows if r['actor']==actor and r['initial_potions']==potions];duration=sum(r['active_seconds'] for r in own)
        values.append(dict(actor=actor,n=len(own),median_seconds=statistics.median(r['active_seconds'] for r in own),gold_per_hour=sum(r['gold'] for r in own)/duration*3600,fragments_per_hour=sum(r['fragments'] for r in own)/duration*3600))
    strata.append(dict(potions=potions,groups=values,ratios={k:max(v[k] for v in values)/min(v[k] for v in values) for k in ['median_seconds','gold_per_hour','fragments_per_hour']}))
proof['all_potion_strata']=strata
proof['not_exact_same_deck_or_paired_route_causal_proof']=True
proof['checker_r1_extra_common_deck_identity_assumption_withdrawn']=True
proof['remaining_other_tiers_and_mature_route_yield_not_inferred']=True
out.write_text(json.dumps(proof,indent=2)+'\\n');print(json.dumps({k:v for k,v in proof.items() if k not in ['normalized_input','raw_rows','class_specific_decklists']}))"""
assert old in source;source=source.replace(old,new)
target=b/'audit-f01-existing-same-tier-efficiency-r2.py';assert not target.exists();compile(source,str(target),'exec');target.write_text(source,encoding='utf-8');print(str(target))
