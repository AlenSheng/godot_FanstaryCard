from pathlib import Path
import json,collections,hashlib,statistics

repo=Path.cwd();base=Path(__file__).parent;root=repo/'docs/season-balance-20261102/evidence/C16-themes/comparison/local-theme-pilot-r5/observations'
rows=[json.loads(x) for x in (root/'encounters.original.jsonl').read_text('utf-8').splitlines()];actions=[json.loads(x) for x in (root/'actions.original.jsonl').read_text('utf-8').splitlines()]
groups=[]
for difficulty in [2,5]:
 for boss in [False,True]:
  for hero in ['Mage','Priest','Guardian']:
   rr=[x for x in rows if x['Difficulty']==difficulty and x['Boss']==boss and x['Hero']==hero]
   aa=[x for x in actions if x['difficulty']==difficulty and x['boss']==boss and x['hero']==hero]
   groups.append(dict(difficulty=difficulty,boss=boss,hero=hero,seconds_by_theme={r['Theme']:r['Seconds'] for r in rr},
                      max_min_ratio=max(r['Seconds'] for r in rr)/min(r['Seconds'] for r in rr),zero_direct_damage_cast_fraction=sum(a['HpDamage']+a['ShieldDamage']==0 for a in aa)/len(aa),
                      armor_effect_counts=dict(collections.Counter(g['EffectAffix'] for g in rr[0]['Armor'])),
                      damage_and_resources=[dict(theme=r['Theme'],initial_hp=r['InitialMonsterHp'],initial_shield=r['InitialMonsterShield'],actual_damage=r['Damage'],
                          recorded_theme_shield=r['GeneratedShield'],recorded_regeneration=r['RegeneratedHp'],
                          absorbed_resource_not_explained_by_old_fields=r['Damage']-r['InitialMonsterHp']-r['InitialMonsterShield']-r['GeneratedShield']-r['RegeneratedHp']) for r in rr]))
old=json.loads((base/'local-theme-pilot-r5/client/data/catalog.json').read_bytes())['tables'];current=json.loads((repo/'client/data/catalog.json').read_bytes())['tables']
names=[n for n in old if any(k in n for k in ['Cards','CardLevels','Weapon','Equipment','Difficulty','Monster','Theme'])]
comparison={n:dict(unchanged=old[n]==current[n],old_sha256=hashlib.sha256(json.dumps(old[n],sort_keys=True).encode()).hexdigest(),current_sha256=hashlib.sha256(json.dumps(current[n],sort_keys=True).encode()).hexdigest()) for n in names}
proof=dict(kind='derived diagnostic from original r5; no new encounters',original_encounters=len(rows),original_actions=len(actions),old_configuration_tables_vs_current=comparison,groups=groups,
           findings=['Elite comparison changes enemy species along with theme; base HP and recurring shields confound theme attribution.',
                     'Old GeneratedShield counts only ThemeShieldGenerated. Ordinary elite shields appear in actual absorbed damage but are not separately recorded.',
                     'Class comparison also changes affix allocation; it is not an isolated test of class passives.',
                     'Old defense-heavy decks/controllers have many non-damage casts; inspect build/action policy before changing production numbers.'],
           C16_complete=False,remaining_budget_before_pilot=179,B05_current_budget=300,B05_retests=False)
out=base/'c16-baseline-diagnosis-r1.derived.json';assert not out.exists();out.write_text(json.dumps(proof,indent=2)+'\n',encoding='utf-8')
print(json.dumps({'old_rows':len(rows),'old_casts':len(actions),'combat_tables_checked':len(comparison),'tables_changed':[n for n,d in comparison.items() if not d['unchanged']],'new_encounters':0}))
