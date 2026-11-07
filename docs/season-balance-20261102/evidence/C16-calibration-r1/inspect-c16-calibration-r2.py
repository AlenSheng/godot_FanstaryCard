from pathlib import Path
import json,collections,hashlib

repo=Path.cwd();base=Path(__file__).parent;root=base/'c16-calibration-pilot-r2';p=root/'observations';out=base/'c16-calibration-inspection-r2.derived.json';assert not out.exists()
proof=json.loads((root/'result.json').read_bytes());assert proof['exit']==0 and proof['new_started_encounters']==18 and proof['source_unchanged'] and proof['binary_unchanged']
attempts=[json.loads(l) for l in (p/'attempts.original.jsonl').read_text('utf-8').splitlines()];rows=[json.loads(l) for l in (p/'encounters.original.jsonl').read_text('utf-8').splitlines()];events=[json.loads(l) for l in (p/'monster-resources.original.jsonl').read_text('utf-8').splitlines()];actions=[json.loads(l) for l in (p/'actions.original.jsonl').read_text('utf-8').splitlines()]
assert len(attempts)==len(rows)==18 and [x['number'] for x in attempts]==list(range(1,19))
assert {(x['Difficulty'],x['Hero']) for x in rows}=={(d,h) for d in range(6) for h in ['Mage','Priest','Guardian']}
def key(e):return e.get('difficulty',e.get('Difficulty')),e.get('hero',e.get('Hero'))
stats=[]
for row in rows:
 k=key(row);aa=[x for x in actions if key(x)==k];rr=[x for x in events if x['kind']=='resource-change' and key(x)==k]
 start=next(x for x in events if x['kind']=='start' and key(x)==k)
 assert row['Theme']=='Fire' and row['Build']=='direct-engine' and row['Seed']==73 and row['Outcome']=='Win'
 assert start['Version']=='season-v1-config-14' and len(start['deck'])==len(set(start['deck']))==20
 assert start['context']['Difficulty']==row['Difficulty'] and start['context']['ConfigVersion']==start['Version']
 assert all(g['Equipment']['Level']==3 for g in start['armor'])
 qualities=[g['Equipment']['Quality'] for g in start['armor']]
 if k[0]==0:assert set(qualities)=={'Blue'} and all(g['Equipment']['EffectAffix'] is None for g in start['armor'])
 elif k[0]==1:assert set(qualities)=={'Purple'}
 else:assert qualities.count('Orange')==1 and qualities.count('Purple')==4
 assert len(aa)==row['Actions'] and sum(x['resolution']['HpDamage']+x['resolution']['ShieldDamage'] for x in aa)==row['Damage']
 assert all(b['seconds']-a['seconds']>=.5-1e-9 for a,b in zip(aa,aa[1:]))
 assert all(1<=x['previews']<=3 and not x['resolution']['ActionReplayed'] for x in aa)
 assert sum(x['previews'] for x in aa)<=row['PreviewCalls']
 for e in rr:
  assert e['hpDelta']==e['hpAfter']-(e['hpBefore']-e['hpDamage'])
  assert e['shieldDelta']==e['shieldAfter']-(e['shieldBefore']-e['shieldDamage'])
 sums=dict(ActualHpRegeneration=sum(max(0,x['hpDelta']) for x in rr),ActualShieldAdded=sum(max(0,x['shieldDelta']) for x in rr),HpOtherLoss=sum(max(0,-x['hpDelta']) for x in rr),ShieldDiscarded=sum(max(0,-x['shieldDelta']) for x in rr))
 assert all(row[n]==v for n,v in sums.items())
 assert row['Damage']==row['InitialHp']+row['InitialShield']+row['ActualHpRegeneration']+row['ActualShieldAdded']-row['HpOtherLoss']-row['ShieldDiscarded']-row['RemainingHp']-row['RemainingShield']
 assert row['RemainingHp']==row['RemainingShield']==0
 stats.append(dict(difficulty=k[0],hero=k[1],seconds=row['Seconds'],actions=len(aa),actual_shield_added=row['ActualShieldAdded'],actual_hp_regeneration=row['ActualHpRegeneration'],ending_hp=row['EndingHp'],damage_per_second=row['Damage']/row['Seconds'],non_damage_casts=sum(x['resolution']['HpDamage']+x['resolution']['ShieldDamage']==0 for x in aa)))
new=dict(kind='Independent arithmetic check of original events; no gameplay replays',actual_encounters=18,wins=18,casts=len(actions),read_only_previews=sum(r['PreviewCalls'] for r in rows),monster_resource_events=sum(e['kind']=='resource-change' for e in events),
         actor_snapshot_immutability_asserted_in_every_selection=True,damage_resource_conservation_verified=True,no_numeric_or_monster_edits=True,
         groups=[dict(difficulty=d,seconds={x['hero']:x['seconds'] for x in stats if x['difficulty']==d},max_min_class_ratio=max(x['seconds'] for x in stats if x['difficulty']==d)/min(x['seconds'] for x in stats if x['difficulty']==d)) for d in range(6)],rows=stats,
         declared_scope='Current formal Fire, one seed, direct-engine only. Other archetypes have static preflight only. Not population or cross-theme medians.',
         C16_complete=False,D03_complete=False,old_encounters=121,current_budget_used=139,remaining=161,B05_current_budget=300,B05_new_attempts=0)
out.write_text(json.dumps(new,indent=2)+'\n',encoding='utf-8');print(json.dumps({k:v for k,v in new.items() if k not in ['groups','rows']}))
