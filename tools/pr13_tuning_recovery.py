"""Validate bounded native tuning/recovery matrix and export original client wires."""
import argparse
from collections import Counter
import copy
import gzip
import hashlib
import itertools
import json
from pathlib import Path

def require(value, message):
    if not value: raise ValueError(message)

def identity(row):
    return tuple(row[k] for k in ('case_id','hero','seed','group','weapon_level','hp_boundary','equipment_profile','recipe'))

def validate_row(row, plan, source):
    require(row['passed'] is True and row['schema']=='actual_tuning_recovery_v1' and row['source_sha']==source,'Native source/status differs')
    recipe=next((r for r in plan['recipes'] if r['id']==row['recipe']),None)
    require(recipe and row['case_id']==recipe['case_id'] and row['selected_cards']==recipe['selection'],'Original frozen order differs')
    require(len(row['deck'])==len(set(row['deck']))==20 and len(row['ids'])==len(set(row['ids']))==len(row['selected_cards']),'Legal pool/selection differs')
    hand=row['input_room']['player']['hand'];by_id={c['card_id']:c['instance_id'] for c in hand}
    require([by_id[c] for c in row['selected_cards']]==row['ids'],'Original owned instance order differs')
    require(row['input_room']['player']['hero_class']==row['hero'] and row['input_room']['player']['weapon_level']==row['weapon_level'],'Player projection differs')
    oracle=row['oracle'];draft=row['draft'];actual=row['actual'];expected=row['expected']
    require(oracle['OrdinaryHeal']+oracle['ConflictHeal']==draft['Heal']==row['requested_heal'],'Separate recovery sum differs')
    require(row['requested_heal']==row['effective_heal']+row['heal_overflow'] and row['effective_heal']==actual['Heal']==expected['heal'] and row['heal_overflow']>=0,'Effective recovery ledger differs')
    require((oracle['R'],oracle['P'],oracle['K'],oracle['D'],oracle['Damage'])==(draft['CoreCount'],draft['ConflictPairCount'],draft['ResonanceMultiplier'],draft['ConflictCancellation'],draft['Damage']),'Native contract oracle differs')
    for key,attribute in [('core_count','CoreCount'),('conflict_pair_count','ConflictPairCount'),('resonance_multiplier','ResonanceMultiplier'),('conflict_cancellation','ConflictCancellation'),('damage','Damage')]:
        require(expected[key]==actual[attribute],'Expected actual result differs: '+key)
    if row['recipe']=='same-core-no-counter':require(oracle['R']==3 and oracle['P']==0 and abs(oracle['K']-1.4)<1e-9,'Unopposed tuning resonance differs')
    if row['recipe']=='same-core-with-counter':require(oracle['R']==3 and oracle['P']==1 and abs(oracle['K']-1.2)<1e-9,'Indirect tuning reduction differs')
    if row['recipe']=='non-core-tuning':require(oracle['P']==0 and oracle['RawConflictHeal']==0,'Tuning incorrectly adds P')
    for name in ['before','after']:
        if name+'_state' not in row:continue
        text=row[name+'_state'];require(hashlib.sha256(text.encode()).hexdigest()==row[name+'_state_sha256'],'Original room state hash differs')
        player=json.loads(text)['Players'][0];pool=sum([player['Combat']['Deck'][n] for n in ('Hand','Library','Discard')],[])
        require(len(pool)==len({c['InstanceId'] for c in pool})==20 and {c['CardId'] for c in pool}==set(row['deck']),'Owned room pool conservation differs')

def validate(directory, plan_path, source, output):
    directory=Path(directory);output=Path(output);require(not output.exists(),'New output required');output.mkdir()
    plan=json.loads(Path(plan_path).read_text());seen=set();counts=Counter();summaries=[];vectors=[];raw_bytes=0;counterexamples=0
    with (output/'client-vectors.jsonl').open('wb') as exported:
        for path in sorted(directory.glob('*.jsonl.gz')):
            summary=json.loads(path.with_name(path.name.replace('.jsonl.gz','.summary.json')).read_text());require(summary['passed'] and summary['source_sha']==source,'Native summary differs')
            digest=hashlib.sha256();size=0;count=0
            with gzip.open(path,'rb') as stream:
                for text in stream:
                    size+=len(text);raw_bytes+=len(text);require(raw_bytes<=plan['budgets']['raw_evidence_bytes'],'Raw evidence budget exceeded');digest.update(text);row=json.loads(text);validate_row(row,plan,source)
                    key=identity(row);require(key not in seen,'Duplicate native identity');seen.add(key);counts[row['case_id']]+=1;count+=1
                    counterexamples+=int(row['oracle']['IncorrectPriestConflictHeal']!=row['oracle']['ConflictHeal'])
                    if 'before_state' in row:vectors.append(row)
                    client={k:row[k] for k in ['schema','source_sha','case_id','hero','seed','group','weapon_level','hp_boundary','equipment_profile','recipe','passed','input_room','ids','command_wire','response_wire','expected','heal_overflow']};exported.write((json.dumps(client,separators=(',',':'))+'\n').encode())
            require((count,size,digest.hexdigest())==(summary['rows'],summary['raw_bytes'],summary['raw_sha256']),'Original row count/hash differs')
            summaries.append({'path':path.name,'bytes':path.stat().st_size,'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'rows':count})
    expected={(r['case_id'],hero,seed,group,level,hp,equip['id'],r['id']) for r,hero,seed,group,level,hp,equip in itertools.product(plan['recipes'],plan['heroes'],plan['seed_blocks'],plan['encounter_groups'],plan['weapon_levels'],plan['hp_boundaries'],plan['equipment_profiles'])}
    require(seen==expected and len(seen)==plan['expected_native_rows'],'Full frozen matrix coverage differs');require(len(vectors)==96 and counterexamples>0,'Render witnesses or separate Priest recovery counterexamples missing')
    controls=[]
    mutations={'selection-order':lambda r:r['selected_cards'].reverse(),'heal-merge':lambda r:r['oracle'].update(ConflictHeal=r['oracle']['ConflictHeal']+1),'tuning-counts-as-counter':lambda r:r['oracle'].update(P=r['oracle']['P']+1),'room-state-hash':lambda r:r.update(before_state_sha256='0'*64)}
    for name,mutate in mutations.items():
        row=copy.deepcopy(vectors[0]);mutate(row)
        try:validate_row(row,plan,source)
        except ValueError:controls.append({'name':name,'rejected':True})
        else:raise ValueError('Corrupt evidence accepted: '+name)
    render={'schema':'actual_tuning_recovery_render_v1','source_sha':source,'fixture_only':True,'vectors':vectors};(output/'render-vectors.json').write_text(json.dumps(render,separators=(',',':')))
    report={'ok':True,'source_sha':source,'native_rows':len(seen),'case_rows':dict(counts),'raw_bytes_verified':raw_bytes,'native_files':summaries,'render_witnesses':len(vectors),'incorrect_priest_multiplier_counterexamples':counterexamples,'corruption_controls':controls,'integration_promotion_allowed':False,'main_acceptance_granted':False}
    (output/'validation.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({k:v for k,v in report.items() if k!='native_files'}))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--input',required=True);p.add_argument('--plan',required=True);p.add_argument('--source-sha',required=True);p.add_argument('--output',required=True);a=p.parse_args();validate(a.input,a.plan,a.source_sha,a.output)
