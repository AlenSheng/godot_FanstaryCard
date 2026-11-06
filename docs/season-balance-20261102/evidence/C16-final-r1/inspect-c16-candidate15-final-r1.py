from pathlib import Path
import json,collections,statistics,math

base=Path(__file__).parent;out=base/'c16-candidate15-final-inspection.derived.json';assert not out.exists()
pairs={x['theme']:x for x in json.loads((base/'c16-candidate15-preflight-r2/reuse-equivalence.original.json').read_bytes())['pairs']}
reused=json.loads((base/'c16-candidate15-reused-observations.derived.json').read_bytes())['eligible_observations'];old=[x['row'] for x in reused]
def key(e):return(e.get('Theme',e.get('theme')),e.get('Difficulty',e.get('difficulty')),e.get('Hero',e.get('hero')),e.get('Build',e.get('build')),e.get('Boss',e.get('boss',True)),e.get('Seed',e.get('seed',73)))
new=[];casts=0;changes=0;previews=0
for label,n in [('elites',30),('bosses',15),('builds',36)]:
 root=base/('c16-candidate15-'+label+'-r1');run=json.loads((root/'result.json').read_bytes());assert run['exit']==0 and run['new_started_encounters']==n and run['roster_identity_match'] and run['source_unchanged'] and run['binary_unchanged'] and run['frozen_workbook_unchanged']
 p=root/'observations';rows=[json.loads(l) for l in (p/'encounters.original.jsonl').read_text('utf-8').splitlines()];aa=[json.loads(l) for l in (p/'actions.original.jsonl').read_text('utf-8').splitlines()];events=[json.loads(l) for l in (p/'monster-resources.original.jsonl').read_text('utf-8').splitlines()];assert len(rows)==n
 for r in rows:
  k=key(r);a=[e for e in aa if key(e)==k];e=[x for x in events if x['kind']=='resource-change' and key(x)==k];start=next(x for x in events if x['kind']=='start' and key(x)==k)
  assert start['Version']==pairs[r['Theme']]['newVersion'] and start['ContentHash']==pairs[r['Theme']]['newHash']
  assert r['Outcome']=='Win' and r['RemainingHp']==r['RemainingShield']==0
  assert len(a)==r['Actions'] and sum(x['resolution']['HpDamage']+x['resolution']['ShieldDamage'] for x in a)==r['Damage']
  assert all(y['seconds']-x['seconds']>=.5-1e-9 for x,y in zip(a,a[1:]));assert all(1<=x['previews']<=3 and not x['resolution']['ActionReplayed'] for x in a)
  assert sum(x['previews'] for x in a)<=r['PreviewCalls']
  for x in e:
   assert x['hpDelta']==x['hpAfter']-x['hpBefore']+x['hpDamage'];assert x['shieldDelta']==x['shieldAfter']-x['shieldBefore']+x['shieldDamage']
  sums={'ActualHpRegeneration':sum(max(0,x['hpDelta']) for x in e),'ActualShieldAdded':sum(max(0,x['shieldDelta']) for x in e),'HpOtherLoss':sum(max(0,-x['hpDelta']) for x in e),'ShieldDiscarded':sum(max(0,-x['shieldDelta']) for x in e)}
  assert all(r[name]==v for name,v in sums.items());assert r['Damage']==r['InitialHp']+r['InitialShield']+r['ActualHpRegeneration']+r['ActualShieldAdded']-r['HpOtherLoss']-r['ShieldDiscarded']-r['RemainingHp']-r['RemainingShield']
  hp={'Mage':70,'Priest':80,'Guardian':100}[r['Hero']];limit=hp+math.floor(hp*start['actualEquipment']['VitalityOvercapBonus']);assert 0<r['EndingHp']<=limit
  if r['Theme']=='Wood' and r['Boss']:assert r['ActualHpRegeneration']<=r['InitialHp']*.05
  casts+=len(a);changes+=len(e);previews+=r['PreviewCalls'];new.append(r)
assert len(new)==81 and len({key(x) for x in new})==81
combined=old+new;assert len(combined)==135 and len({key(x) for x in combined})==135
medians=[]
for boss in [False,True]:
 for hero in ['Mage','Priest','Guardian']:
  rr=[r for r in combined if r['Difficulty']==5 and r['Hero']==hero and r['Build']=='direct-engine' and r.get('Boss',True)==boss]
  assert len(rr)==10
  values={}
  for theme in ['Fire','Wood','Earth','Metal','Water']:
   subset=[r for r in rr if r['Theme']==theme];assert {r['Seed'] for r in subset}=={73,137};values[theme]=statistics.median(r['Seconds'] for r in subset)
  ratio=max(values.values())/min(values.values());medians.append(dict(boss=boss,hero=hero,medians=values,max_min_ratio=ratio,original_15_percent_passed=ratio<=1.15,authorized_limit=1.25 if boss else 1.20,authorized_limit_passed=ratio<=(1.25 if boss else 1.20)))
viability=[]
for theme in ['Fire','Wood','Earth','Metal','Water']:
 for hero in ['Mage','Priest','Guardian']:
  for build in ['direct-engine','counter-combo','fortress-control']:
   for boss in [False,True]:
    rr=[r for r in combined if r['Theme']==theme and r['Difficulty']==5 and r['Hero']==hero and r['Build']==build and r.get('Boss',True)==boss and r['Seed']==73];assert len(rr)==1 and rr[0]['Outcome']=='Win';viability.append(key(rr[0]))
assert len(viability)==90
for d in range(6):
 for h in ['Mage','Priest','Guardian']:assert any(r['Theme']=='Fire' and r['Difficulty']==d and r['Hero']==h and r['Build']=='direct-engine' and r.get('Boss',True) and r['Seed']==73 and r['Outcome']=='Win' for r in combined)
policy=json.loads((base/'c16-candidate15-acceptance-policy.before-timing.json').read_bytes());assert policy['registered_before_candidate15_timed_runs'] and all(x['authorized_limit_passed'] for x in medians)
result=dict(status='C16_accepted_with_predeclared_user_authorized_boss_timing_relaxation',new_encounters=81,new_wins=81,reused_unchanged_observations=54,not_one_new_all_current_run=True,accepted_dependency_equivalent_dataset=135,
            independently_checked_new_casts=casts,new_resource_changes=changes,readonly_previews=previews,original_15_percent_all_passed=all(x['original_15_percent_passed'] for x in medians),
            original_15_percent_elites_all_passed=all(x['original_15_percent_passed'] for x in medians if not x['boss']),original_15_percent_bosses_all_passed=all(x['original_15_percent_passed'] for x in medians if x['boss']),
            authorized_boss_limit=1.25,boss_relaxation_applied=True,elite_relaxation_needed=False,medians=medians,all5themes_3heroes_3archetypes_boss_elite_seed73=90,viability_case_keys=viability,
            formal_first_theme_six_difficulty_baseline_verified=True,C16_used=298,C16_remaining=2,B05_budget=300,B05_new_runs=0,D03_complete=False,population_medians_claimed=False,production_deployed=False,production_restarted=False)
out.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({k:v for k,v in result.items() if k not in ['medians','viability_case_keys']}));print('median ratios',[(x['boss'],x['hero'],round(x['max_min_ratio'],4)) for x in medians])
