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


def main():
    p=argparse.ArgumentParser();p.add_argument('--input',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--expected-source',required=True);p.add_argument('--controls',action='store_true');args=p.parse_args();require(not args.output.exists(),'New evidence output required')
    result,rows=validate(args.input,args.expected_source)
    if args.controls:result['corruption_controls']=corruption_controls(rows,args.input)
    args.output.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))


if __name__=='__main__':main()
