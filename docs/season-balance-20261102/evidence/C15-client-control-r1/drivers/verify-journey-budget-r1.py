from pathlib import Path
import copy,hashlib,importlib.util,json

repo=Path.cwd();base=Path(__file__).parent;target=base/'journey-budget-r2/verification.json'
assert not target.exists()
spec=importlib.util.spec_from_file_location('budget',repo/'tools/check_journey_reward_budget.py');module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
catalog=json.loads((repo/'client/data/catalog.json').read_text('utf-8'))
report=json.loads((base/'journey-budget-r2/budget.json').read_text('utf-8'))
assert report['checker_sha256']==hashlib.sha256((repo/'tools/check_journey_reward_budget.py').read_bytes()).hexdigest()
checks={}
checks['reproduce budget byte-equivalent logical report']=all(report[key]==value for key,value in module.build(catalog).items())
checks['short season rounds each threshold separately']=[(r['duration_days'],r['level20_experience'],r['level30_experience']) for r in report['duration_sensitivity']]==[(30,4901,8959),(42,6850,12525),(60,6850,12525)]
checks['class rewards choose one class with eight total']=len(report['class_allocations'])==15 and all(sum(row.values())==8 for row in report['class_allocations'])
checks['bonus levels mint only the ten display entitlements']=report['cosmetic_counts']=={'AvatarFrame':3,'CardBack':2,'Collection':2,'Title':3} and all(r['new_source_if_all_eligible_claimed']==report['main_total_if_all_claimed'] for r in report['levels'][20:])
checks['no direct equipment or currency source']=all(value==0 for value in report['direct_other_sources'].values()) and not report['shadow_cost_is_minted_gold'] and not report['shadow_cost_is_realized_sink_reduction']
mutations=[('double fragments','SeasonJourneyRewards',0,'amount',20),('duplicate level','SeasonJourneyRewards',1,'level',1),('missing explicit class choice','SeasonJourneyRewards',2,'requires_class_choice',False),('bonus becomes a resource','SeasonJourneyRewards',20,'kind','WarriorSoul'),('unknown cosmetic','SeasonJourneyRewards',20,'cosmetic_id','unknown'),('four cards per pack','SeasonShopRules',0,'pack_cards',4),('weights exceed100','SeasonShopRules',0,'purple_weight',6),('wrong xp threshold','SeasonProgression',1,'xp_to_next_42',214),('wrong source ownership','SeasonJourneyRewards',0,'ownership','PermanentBound')]
for label,table,index,key,value in mutations:
    invalid=copy.deepcopy(catalog);invalid['tables'][table][index][key]=value
    try:module.build(invalid)
    except AssertionError:checks['reject '+label]=True
    else:checks['reject '+label]=False
result={'ok':all(checks.values()),'checks':checks,'scope':'configuration arithmetic only; no battles, routes, cohorts or live claims','original_failure_note':'First checker draft expected a content_hash property that the public catalog intentionally does not contain. Removed that property assumption; the report pins the exact catalog SHA. No product/configuration values changed.'}
target.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8');print(json.dumps(result));assert result['ok']
