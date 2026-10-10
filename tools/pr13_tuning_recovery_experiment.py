"""Stream and reconcile original advancing-encounter and per-cast evidence."""
import argparse
from collections import Counter
import copy
import gzip
import hashlib
import json
from pathlib import Path

def require(value, message):
    if not value: raise ValueError(message)

def validate_event(row):
    require(row['Passed'] is True,'Actual cast contract failed')
    ids=[c['InstanceId'] for c in row['Selected']]
    require(1<=len(ids)<=5 and len(ids)==len(set(ids)),'Owned selected order/identity differs')
    o=row['Oracle'];d=row['Draft'];a=row['Actual']
    require((o['Core'],o['R'],o['P'],o['K'],o['D'],o['Damage'],o['OrdinaryHeal']+o['ConflictHeal'])==
            (d['CoreElement'],d['CoreCount'],d['ConflictPairCount'],d['ResonanceMultiplier'],d['ConflictCancellation'],d['Damage'],d['Heal']),'Independent oracle differs')
    require(a['Heal']>=0 and a['Heal']<=d['Heal'] and row['HpBefore']>0 and row['AtSeconds']<=600,'Actual recovery/time differs')
    require(o['R']>=0 and o['P']>=0 and o['B'] in [0,1] and o['RawConflictHeal']>=0,'Contract counts differ')
    if o['Core'] is not None:require(abs(o['K']-(1+.2*max(0,o['R']-1+o['B']-o['P'])))<1e-9,'K does not include indirect P reduction')
    if o['P']==0:require(o['D']==o['RawConflictHeal']==o['ConflictHeal']==0,'Conflict recovery without P')
    equipment=row['Equipment'];expected=int(o['RawConflictHeal']*(1+equipment['VitalityHealBonus']))
    require(o['ConflictHeal']==expected,'Conflict recovery incorrectly uses Priest multipliers')

def stream(path, summary, callback):
    require(path.stat().st_size==summary['stored_bytes'] and hashlib.sha256(path.read_bytes()).hexdigest()==summary['stored_sha256'],'Stored evidence hash differs')
    digest=hashlib.sha256();size=0;count=0
    with gzip.open(path,'rb') as f:
        for raw in f:
            digest.update(raw);size+=len(raw);count+=1;callback(json.loads(raw))
    require(size==summary['raw_bytes'] and digest.hexdigest()==summary['raw_sha256'],'Original raw bytes/hash differ')
    return count

def validate(directory, source, controls=False):
    directory=Path(directory);manifest=json.loads((directory/'manifest.json').read_text());summary=json.loads((directory/'summary.json').read_text())
    require(manifest['schema']=='actual_tuning_recovery_experiment_v1' and manifest['source_sha']==summary['source_sha']==source,'Source/schema differs')
    require(summary['passed'] and summary['errors']==0 and manifest['paired_budget_guard_passed'] and not manifest['candidate_activation'],'Native run/budget failed')
    require(manifest['weapon_level']==manifest['card_level']==0 and manifest['equipment']=='Empty' and manifest['strategy']=='basic' and manifest['cutoff_seconds']==600,'Frozen resource/information conditions differ')
    a=manifest['baseline_deck'];b=manifest['candidate_deck'];require(len(a)==len(set(a))==len(b)==len(set(b))==20 and set(a)-set(b)=={'ET-WATER-G'} and set(b)-set(a)=={manifest['alternative']},'Exactly one tuning replacement required')
    require(manifest['seed_start']==420001+1000*manifest['block_index'] and 3<=manifest['samples']<=1000,'Seed block differs')
    encounters={};casts=Counter();denominators=Counter();ledger={};witnesses=[];outcomes=Counter()
    def encounter(row):
        identity=(row['Seed'],row['Profile']);require(identity not in encounters,'Duplicate encounter identity');encounters[identity]=row
        require(row['Outcome'] in ['Victory','Death','Censored'] and row['Error'] is None,'Encounter failed')
        require(row['Hero']==manifest['hero'] and row['Group']==manifest['group'] and row['Deck']==manifest['alternative'] and row['WeaponLevel']==0,'Encounter stratum differs')
        outcomes[row['Outcome']]+=1
    count=stream(directory/'encounters.jsonl.gz',summary,encounter);require(count==summary['rows']==manifest['samples']*2,'Encounter denominator differs')
    expected={(s,p) for s in range(manifest['seed_start'],manifest['seed_start']+manifest['samples']) for p in ['BaselineGreenWater','SingleGreenReplacement']};require(set(encounters)==expected,'Paired encounter coverage differs')
    for seed in range(manifest['seed_start'],manifest['seed_start']+manifest['samples']):
        left=encounters[(seed,'BaselineGreenWater')];right=encounters[(seed,'SingleGreenReplacement')]
        require((left['OpeningEnemyHp'],left['OpeningEnemyShield'],left['EnemyNonHpInputSha256'])==(right['OpeningEnemyHp'],right['OpeningEnemyShield'],right['EnemyNonHpInputSha256']),'Paired encounter input differs')
    def event(row):
        validate_event(row);identity=(row['Seed'],row['Profile']);require(identity in encounters,'Cast has no declared encounter')
        require(row['Cast']==casts[identity] and row['Hero']==manifest['hero'] and row['Group']==manifest['group'] and row['SeedBlock']==manifest['block_index'],'Original cast order/stratum differs')
        casts[identity]+=1;o=row['Oracle'];arm=row['Profile']+'/'
        denominators[arm+'all_casts']+=1
        for case,flag in [('T01',o['FirstEligibleIsTuning']),('T02',o['SameCoreTuningWithCounter']),('T03',o['RawConflictHeal']>0)]:denominators[arm+case+('_applicable' if flag else '_not_applicable')]+=1
        if o['OrdinaryAndConflict']:denominators[arm+'ordinary_and_conflict']+=1
        if o['IncorrectPriestConflictHeal']!=o['ConflictHeal']:denominators[arm+'incorrect_priest_multiplier_counterexample']+=1
        sums=ledger.setdefault(identity,Counter());sums['RequestedHeal']+=row['Draft']['Heal'];sums['EffectiveHeal']+=row['Actual']['Heal'];sums['HealOverflow']+=row['Draft']['Heal']-row['Actual']['Heal']
        if len(witnesses)<5:witnesses.append(row)
    actual_events=0
    for part in summary['event_parts']:
        path=directory/part['path'];require(path.resolve().is_relative_to(directory.resolve()),'Part path escaped');part_count=stream(path,part,event);require(part_count==part['events'],'Part event denominator differs');actual_events+=part_count
    require(actual_events==summary['actual_casts'] and dict(denominators)==summary['case_denominators'],'Complete cast denominator differs')
    for identity,row in encounters.items():
        require(casts[identity]==row['Actions'],'Actual cast count differs from encounter actions')
        for key in ['RequestedHeal','EffectiveHeal','HealOverflow']:require(ledger.get(identity,{}).get(key,0)==row[key],'Original cast/encounter ledger differs: '+key)
    negative=[]
    if controls:
        require(witnesses,'Pilot must contain actual casts')
        mutations={'wrong-main-core-count':lambda r:r['Oracle'].update(R=r['Oracle']['R']+1),'merged-heal':lambda r:r['Oracle'].update(ConflictHeal=r['Oracle']['ConflictHeal']+1),'duplicate-owned-card':lambda r:r['Selected'].append(r['Selected'][0]),'native-contract-failed':lambda r:r.update(Passed=False)}
        for name,mutate in mutations.items():
            row=copy.deepcopy(witnesses[0]);mutate(row)
            try:validate_event(row)
            except ValueError:negative.append({'name':name,'rejected':True})
            else:raise ValueError('Corrupt cast accepted: '+name)
    applicable={case:{arm:denominators[arm+'/'+case+'_applicable'] for arm in ['BaselineGreenWater','SingleGreenReplacement']} for case in ['T01','T02','T03']}
    return {'ok':True,'source_sha':source,'encounters':count,'pairs':count//2,'actual_events':actual_events,'outcomes':dict(outcomes),'applicable_cases':applicable,'case_denominators':dict(denominators),'negative_controls':negative,'full_unit':manifest['samples']==1000,'whole_experiment_complete':False,'required_cases_accepted':False,'main_acceptance_granted':False}

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--input',required=True);p.add_argument('--source-sha',required=True);p.add_argument('--output',required=True);p.add_argument('--controls',action='store_true');a=p.parse_args();r=validate(a.input,a.source_sha,a.controls);Path(a.output).write_text(json.dumps(r,indent=2)+'\n');print(json.dumps(r))
