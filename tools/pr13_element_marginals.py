"""Validate native paired tuning-card ledgers; acceptance is a separate stage."""
import argparse
from collections import Counter
import copy
import gzip
import hashlib
import json
from pathlib import Path


def require(value, reason):
    if not value: raise ValueError(reason)


def validate_row(row):
    require(row['Outcome'] in ('Victory','Death','Censored') and row['Error'] is None, 'Native encounter failed')
    require(row['WeaponLevel']==0 and row['Strategy']=='basic', 'Undeclared budget/strategy')
    require(0<=row['ObservedSeconds']<=600 and row['FinalPoolSize']>=20, 'Observation or pool differs')
    for key in ('RequestedImmediateCards','ImmediateCardsDrawn','NaturalCardsDrawn','CardsSpent','RequestedHeal','RequestedShield','EffectiveHeal','EffectiveShield','HealOverflow','ShieldOverflow','RequestedControlTicks','ConvertedControlTicks','AdmittedControlTicks','AddedAliveControlUnionTicks','ObservedAliveControlUnionTicks'):
        require(type(row[key]) is int and row[key]>=0, 'Nonnegative native metric required: '+key)
    require(row['RequestedHeal']==row['EffectiveHeal']+row['HealOverflow'], 'Heal requested/effective/overflow differ')
    require(row['RequestedShield']==row['EffectiveShield']+row['ShieldOverflow'], 'Shield requested/effective/overflow differ')
    require(row['AddedAliveControlUnionTicks']<=row['AdmittedControlTicks'] and row['ObservedAliveControlUnionTicks']<=row['AddedAliveControlUnionTicks'], 'Control overlap/window accounting differs')
    targets=row['ControlUnionTicksByTarget'];require(all(type(v) is int and v>=0 for v in targets.values()) and sum(targets.values())==row['ObservedAliveControlUnionTicks'], 'Target union totals differ')
    require(all(v<=round(row['ObservedSeconds']*10000000) for v in targets.values()), 'One target control exceeds observation')
    require(row['Actions']==row['EffectiveActions']+row['ZeroEffectiveActions'] and row['CardsSpent']>=row['Actions'], 'Action ledger differs')


def validate(directory, expected_source=None):
    directory=Path(directory);manifest=json.loads((directory/'manifest.json').read_text());summary=json.loads((directory/'summary.json').read_text());raw=directory/'encounters.jsonl.gz'
    require(manifest['schema']=='actual_element_marginals_v1' and manifest['source_sha']==summary['source_sha'], 'Native schema/source differs')
    if expected_source:require(summary['source_sha']==expected_source,'Execution SHA differs')
    require(summary['passed'] is True and summary['errors']==0 and manifest['paired_budget_guard_passed'] is True and manifest['candidate_activation'] is False,'Native execution/budget failed')
    require(manifest['weapon_level']==manifest['card_level']==0 and manifest['cutoff_seconds']==600 and manifest['strategy']=='basic','Frozen conditions differ')
    table=manifest['tune_table'];require(len(table)==5 and {c['CardId'] for c in table}=={'ET-'+e+'-G' for e in ('FIRE','WOOD','EARTH','METAL','WATER')},'Five current tuning definitions required')
    require(all(c['Quality']=='Green' and c['Rarity']==2 for c in table) and len({c['UnlockCost'] for c in table})==1,'Replacement quality/cost differs')
    decks=manifest['baseline_decks'];require({d['hero'] for d in decks}==set(manifest['heroes']) and len(decks)==len(manifest['heroes']),'Baseline hero coverage differs')
    for deck in decks:
        require(len(deck['cards'])==len(set(deck['cards']))==20 and deck['cards'].count('ET-FIRE-G')==1,'Unique twenty-card baseline required')
        budget=deck['budget'];require(set(budget)=={'rarity','unlock_cost'} and all(type(v) is int and v>0 for v in budget.values()),'Explicit serialized deck budget required')
    require(raw.stat().st_size==summary['stored_bytes'] and hashlib.sha256(raw.read_bytes()).hexdigest()==summary['stored_sha256'],'Stored bytes/hash differ')
    rows={};digest=hashlib.sha256();size=0
    with gzip.open(raw,'rb') as stream:
        for text in stream:
            digest.update(text);size+=len(text);require(size<=512*1024**2,'Original evidence bound exceeded');row=json.loads(text);validate_row(row)
            key=(row['Seed'],row['Hero'],row['Deck'],row['Group'],row['Profile']);require(key not in rows,'Duplicate native identity');rows[key]=row
    expected={(seed,hero,card,group,profile) for seed in range(manifest['seed_start'],manifest['seed_start']+manifest['samples']) for hero in manifest['heroes'] for card in manifest['alternatives'] for group in manifest['groups'] for profile in ('BaselineGreenFire','SingleGreenReplacement')}
    require(set(rows)==expected and len(rows)==summary['rows'],'Declared paired coverage differs')
    require(size==summary['raw_bytes'] and digest.hexdigest()==summary['raw_sha256'],'Original bytes/hash differ')
    for seed,hero,card,group,profile in expected:
        if profile!='BaselineGreenFire':continue
        a=rows[(seed,hero,card,group,profile)];b=rows[(seed,hero,card,group,'SingleGreenReplacement')]
        require(a['OpeningEnemyHp']==b['OpeningEnemyHp'] and a['OpeningEnemyShield']==b['OpeningEnemyShield'] and a['EnemyNonHpInputSha256']==b['EnemyNonHpInputSha256'],'Paired encounter input differs')
        require(a['SeedBlock']==b['SeedBlock']==manifest['block_index'],'Declared seed block differs')
    return {'ok':True,'source_sha':summary['source_sha'],'rows':len(rows),'paired_encounters':len(rows)//2,'outcomes':dict(Counter(r['Outcome'] for r in rows.values())),'full_experiment':False,'main_acceptance_granted':False},rows


def corruption_controls(rows, directory):
    original=next(iter(rows.values()));controls=[]
    mutations={
        'heal-overflow':lambda r:r.update(HealOverflow=r['HealOverflow']+1),
        'shield-overflow':lambda r:r.update(ShieldOverflow=r['ShieldOverflow']+1),
        'target-union-sum':lambda r:r.update(ObservedAliveControlUnionTicks=r['ObservedAliveControlUnionTicks']+1),
        'negative-actual-draw':lambda r:r.update(ImmediateCardsDrawn=-1),
        'native-error':lambda r:r.update(Outcome='Error',Error='Injected native evidence corruption'),
    }
    for name,mutate in mutations.items():
        row=copy.deepcopy(original);mutate(row)
        try:validate_row(row)
        except ValueError:controls.append({'control':name,'passed':True})
        else:raise AssertionError('Corrupt native row accepted: '+name)
    data=bytearray((Path(directory)/'encounters.jsonl.gz').read_bytes());data[-8]^=1
    try:gzip.decompress(data)
    except (OSError,EOFError):controls.append({'control':'gzip-crc','passed':True})
    else:raise AssertionError('Corrupt CRC accepted')
    return {'ok':True,'controls':controls}


def validate_boundaries(path, expected_source):
    evidence=json.loads(Path(path).read_text())
    require(evidence['schema']=='actual_element_marginal_boundaries_v1' and evidence['source_sha']==expected_source and evidence['passed'] is True,'Native boundary source/status differs')
    require(evidence['weapon_level']==evidence['card_level']==0 and evidence['candidate_activation'] is False,'Boundary budget differs')
    rows=evidence['rows'];expected={(case,hero) for case in ('PR13-B08.2-T01','PR13-B08.2-T02','PR13-B08.2-T03') for hero in ('Mage','Priest','Guardian')}
    require(len(rows)==9 and {(r['case_id'],r['hero']) for r in rows}==expected,'Boundary strata differ')
    events=0
    for row in rows:
        require(row['passed'] is True and row['paired_budget_guard_passed'] is True and row['natural_seconds']==0,'Boundary execution failed')
        a=row['baseline_deck'];b=row['candidate_deck'];require(len(a)==len(b)==len(set(a))==len(set(b))==20 and set(a)-set(b)=={'ET-FIRE-G'} and set(b)-set(a)=={row['replacement']},'Boundary must replace one card')
        arms={arm['profile']:arm['events'] for arm in row['arms']};require(set(arms)=={'BaselineGreenFire','SingleGreenReplacement'},'Both native arms required')
        for profile,arm in arms.items():
            require(len(arm)==(3 if row['case_id'].endswith('T02') else 1),'Boundary cast count differs')
            for cast,event in enumerate(arm):
                require(event['cast']==cast,'Boundary event order differs');events+=1
                for name in ('before_state_sha256','after_state_sha256'):
                    digest=event[name];raw=row['states'][digest];require(hashlib.sha256(raw.encode()).hexdigest()==digest,'Original native state bytes differ')
                    room=json.loads(raw);require(len(room['Players'])==1 and room['Players'][0]['Combat']['WeaponLevel']==0,'Boundary player state differs')
                    combat=room['Players'][0]['Combat'];pool=combat['Deck']['Hand']+combat['Deck']['Library']+combat['Deck']['Discard']
                    require(len(pool)==20 and len({c['InstanceId'] for c in pool})==20 and {c['CardId'] for c in pool}==set(b if profile=='SingleGreenReplacement' else a),'Boundary pool conservation differs')
                before=json.loads(row['states'][event['before_state_sha256']])['Players'][0];after=json.loads(row['states'][event['after_state_sha256']])['Players'][0]
                require(len(before['Combat']['Deck']['Hand'])==5,'Boundary must start with a full hand')
                selected=set(event['selected_cards']);old={c['InstanceId'] for c in before['Combat']['Deck']['Hand'] if c['CardId'] not in selected}
                require(event['actual_draw']==sum(c['InstanceId'] not in old for c in after['Combat']['Deck']['Hand']),'Native actual draw differs')
                require(event['requested_draw']==event['actual_draw']+event['immediate_overflow'] and event['immediate_overflow']>=0,'Boundary immediate cap differs')
                for kind in ('heal','shield'):
                    require(event['requested_'+kind]==event['effective_'+kind]+event[kind+'_overflow'] and event['effective_'+kind]>=0 and event[kind+'_overflow']>=0,'Boundary recovery accounting differs')
                require(event['added_control_union_ticks']<=event['admitted_control_ticks']<=event['converted_control_ticks'],'Boundary union/DR differs')
                if profile=='SingleGreenReplacement':
                    if row['case_id'].endswith('T01'):require(event['requested_draw']>event['actual_draw']==1,'Water hand cap missing')
                    elif row['case_id'].endswith('T02'):
                        first=arm[0]['converted_control_ticks'];require(first>0 and event['admitted_control_ticks']==(first if cast==0 else first//2 if cast==1 else 0),'Current full/half/zero DR differs')
                        require(event['added_control_union_ticks']==(first if cast==0 else 0) and event['target_control_union_ticks']==first,'Control must use overlap union')
                    else:require(event['effective_heal']==event['effective_shield']==0 and event['heal_overflow']>0 and event['shield_overflow']>0,'Full caps missing')
    return {'ok':True,'source_sha':expected_source,'native_rows':len(rows),'native_events':events,'render_executed':False,'full_experiment':False}


def main():
    p=argparse.ArgumentParser();p.add_argument('--input',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--expected-source',required=True);p.add_argument('--controls',action='store_true');p.add_argument('--boundaries',type=Path);args=p.parse_args();require(not args.output.exists(),'New evidence output required')
    result,rows=validate(args.input,args.expected_source)
    if args.controls:result['corruption_controls']=corruption_controls(rows,args.input)
    if args.boundaries:result['boundaries']=validate_boundaries(args.boundaries,args.expected_source)
    args.output.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))


if __name__=='__main__':main()
