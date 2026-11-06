from pathlib import Path
import json,collections,math

base=Path(__file__).parent;out=base/'c16-expansion-inspection-r1.derived.json';assert not out.exists()
stages=['c16-expansion-fire-r1','c16-expansion-wood-r1','c16-counter-probe-r1','c16-remaining-r1'];allrows=[];starts={};total_actions=0;resource_events=0;interrupts=collections.Counter()
def key(e):return(e.get('Theme',e.get('theme')),e.get('Difficulty',e.get('difficulty')),e.get('Hero',e.get('hero')),e.get('Build',e.get('build')),e.get('Boss',e.get('boss',True)),e.get('Seed',e.get('seed',73)))
for stage,expected in zip(stages,[30,18,12,18]):
 root=base/stage;proof=json.loads((root/'result.json').read_bytes());assert proof['exit']==0 and proof['new_started_encounters']==expected and proof['roster_identity_match'] and proof['source_unchanged'] and proof['binary_unchanged']
 p=root/'observations';rows=[json.loads(l) for l in (p/'encounters.original.jsonl').read_text('utf-8').splitlines()];attempts=[json.loads(l) for l in (p/'attempts.original.jsonl').read_text('utf-8').splitlines()]
 aa=[json.loads(l) for l in (p/'actions.original.jsonl').read_text('utf-8').splitlines()];ee=[json.loads(l) for l in (p/'monster-resources.original.jsonl').read_text('utf-8').splitlines()]
 assert len(rows)==len(attempts)==expected
 for r in rows:
  k=key(r);assert k not in starts;a=[x for x in aa if key(x)==k];events=[x for x in ee if x['kind']=='resource-change' and key(x)==k];start=next(x for x in ee if x['kind']=='start' and key(x)==k);starts[k]=start
  assert len(a)==r['Actions'];assert sum(x['resolution']['HpDamage']+x['resolution']['ShieldDamage'] for x in a)==r['Damage']
  assert all(y['seconds']-x['seconds']>=.5-1e-9 for x,y in zip(a,a[1:]));assert all(1<=x['previews']<=3 and not x['resolution']['ActionReplayed'] for x in a)
  for e in events:
   assert e['hpDelta']==e['hpAfter']-e['hpBefore']+e['hpDamage'];assert e['shieldDelta']==e['shieldAfter']-e['shieldBefore']+e['shieldDamage']
  expected_resources={'ActualHpRegeneration':sum(max(0,e['hpDelta']) for e in events),'ActualShieldAdded':sum(max(0,e['shieldDelta']) for e in events),'HpOtherLoss':sum(max(0,-e['hpDelta']) for e in events),'ShieldDiscarded':sum(max(0,-e['shieldDelta']) for e in events)}
  assert all(r[n]==v for n,v in expected_resources.items());assert r['Damage']==r['InitialHp']+r['InitialShield']+r['ActualHpRegeneration']+r['ActualShieldAdded']-r['HpOtherLoss']-r['ShieldDiscarded']-r['RemainingHp']-r['RemainingShield']
  if r['Theme']=='Wood' and r['Boss']:assert r['ActualHpRegeneration']<=r['InitialHp']*.05
  base_hp={'Mage':70,'Priest':80,'Guardian':100}[r['Hero']];limit=base_hp+math.floor(base_hp*start['actualEquipment']['VitalityOvercapBonus']);assert 0<=r['EndingHp']<=limit
  for x in a:
   if x.get('windupBeforeMs',0)>0 and x.get('stunBeforeMs',0)<=0 and x['resolution']['StunSeconds']>0 and not x['resolution']['TargetDefeated'] and x.get('bossPhaseBefore')==x.get('bossPhaseAfter') and x.get('intentIndexBefore')!=x.get('intentIndexAfter'):
    interrupts[x['telegraphed']]+=1
  total_actions+=len(a);resource_events+=len(events);allrows.append(r)
assert len(allrows)==78
oldroot=base/'c16-calibration-pilot-r2/observations';original=[json.loads(l) for l in (oldroot/'encounters.original.jsonl').read_text('utf-8').splitlines()]
oldstart=[json.loads(l) for l in (oldroot/'monster-resources.original.jsonl').read_text('utf-8').splitlines() if json.loads(l)['kind']=='start']
for r in original:assert key(r) not in starts;starts[key(r)]=next(x for x in oldstart if key(x)==key(r))
combined=original+allrows;assert len({key(r) for r in combined})==96
benchmark=[]
for boss in [False,True]:
 for hero in ['Mage','Priest','Guardian']:
  rr=[r for r in combined if r['Difficulty']==5 and r['Hero']==hero and r.get('Boss',True)==boss and r['Build']=='direct-engine'];assert len(rr)==5
  benchmark.append(dict(hero=hero,boss=boss,seconds_by_theme={r['Theme']:r['Seconds'] for r in rr},max_min_ratio=max(r['Seconds'] for r in rr)/min(r['Seconds'] for r in rr),single_seed_only=True))
paired=[]
for theme in ['Fire','Wood']:
 for hero in ['Mage','Priest','Guardian']:
  for boss in [False,True]:
   a=next(r for r in allrows if r['Theme']==theme and r['Hero']==hero and r['Boss']==boss and r['Difficulty']==5 and r['Build']=='counter-combo');b=next(r for r in allrows if r['Theme']==theme and r['Hero']==hero and r['Boss']==boss and r['Build']=='counter-offense')
   sa=starts[key(a)];sb=starts[key(b)];assert a['Deck']==b['Deck'] and sa['initial']==sb['initial']
   ea={n:v for n,v in sa['actualEquipment'].items() if n not in ['Elements','RawElements']};eb={n:v for n,v in sb['actualEquipment'].items() if n not in ['Elements','RawElements']};assert ea==eb
   paired.append(dict(theme=theme,hero=hero,boss=boss,defensive_seconds=a['Seconds'],offensive_seconds=b['Seconds'],same_initial_monsters=True,same_deck=True,same_non_elemental_equipment=True,offensive_vs_defensive_ratio=b['Seconds']/a['Seconds']))
result=dict(new_encounters=78,outcomes=dict(collections.Counter(r['Outcome'] for r in allrows)),actual_casts=total_actions,resource_change_events=resource_events,resource_conservation_verified=True,legal_health_verified=True,
            modern_current_dataset_encounters=96,benchmark_d5=benchmark,counter_armor_pairs=paired,recorded_nonlethal_windup_interrupts=dict(interrupts),
            C16_used=217,C16_remaining=83,C16_complete=False,overall_complete=False,numeric_changes=False,B05_new_attempts=0,
            exact_remaining_gap='Elite work and theme times exceed the ~15% target; versioned monster-base source needed before numeric calibration. Two-seed medians and other-theme archetype viability remain open.')
out.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({k:v for k,v in result.items() if k not in ['benchmark_d5','counter_armor_pairs']}))
