"""Reconcile original legal room kills and native recycle observations."""
import argparse
from collections import Counter,defaultdict
import copy
import gzip
import hashlib
import json
from pathlib import Path

SEEDS=(450001,451001,452001)
SPECIES={'fire-bat':'FireBat','thorn-mite':'ThornMite','murk-snail':'MudHydra','sand-lizard':'SandLizard','rust-rat':'RustRat','box-spirit':'BoxSpirit','metal-guard':'GoldGuard','fire-herald':'FireReaver','marsh-mother':'SwampMother','stone-guard':'StoneGuard','thorn-guard':'ThornGuard','annihilation-core':'VoidCore'}
def require(ok,message):
    if not ok:raise ValueError(message)
def all_cards(state):
    d=state['Combat']['Deck'];return d['Hand']+d['Library']+d['Discard']
def legal(hero):
    prefix={'Mage':'MAG','Priest':'PRI','Guardian':'GUA'}[hero]
    return [f'C{i:02}' for i in range(1,14)]+[f'{prefix}-{i:02}' for i in range(1,8)]
def kill_contract(kill,catalog):
    source=kill['source_monster_id'];species=source[:-2] if source.endswith(('-a','-b')) else source
    card=kill['granted'];definition=catalog[card['CardId']];actual=kill['actual_resolution']
    require(species in SPECIES and definition['monster_type']==SPECIES[species]==kill['monster_type'] and card['Level']==0,'Actual monster/card provenance differs')
    require(actual['AttackerId']==kill['actor_id'] and actual['BattleId']==kill['battle_id'] and actual['TargetId']==source and actual['TargetDefeated'],'Actual finishing resolution differs')
    require(kill['after_pool']==kill['before_pool']+1 and sum(c['InstanceId']==card['InstanceId'] for c in kill['after_discard'])==1,'Actual discard entry/count differs')
    if species!='box-spirit':require(card['ElementOverride'] is None,'Non-BOX element override differs')
def row_contract(row,source,catalog):
    require(row['source_sha']==source,'Original source differs');a=row['actual'];hero=a['hero'];case=row['case_id']
    require(hero in ['Mage','Priest','Guardian'],'Declared hero differs')
    if case.endswith('T01'):
        require(not a['effective_optional_policy'] and a['disabled_choice_rejected_without_mutation'],'Default policy or disabled mutation differs')
        before=a['before_base'];state=a['after_state'];player=state['Players'][0];after=all_cards(player);kills=a['actual_kills']
        require(len(before)==20 and set(c['CardId'] for c in before)==set(legal(hero)) and len({c['InstanceId'] for c in before})==20,'Original legal base differs')
        require(state['Numerics']['OptionalMonsterPool'] is False and not player['MonsterPool']['Active'] and not player['MonsterPool']['Pending'],'Actual current pool policy differs')
        require(len(after)==20+len(kills) and len({c['InstanceId'] for c in after})==len(after) and {c['InstanceId'] for c in before}<={c['InstanceId'] for c in after},'Base instance conservation differs')
        for k in kills:kill_contract(k,catalog);require(k['actor_id']==player['PlayerId'],'Kill belongs to another actor')
    elif case.endswith('T02'):kill_contract(a['actual'],catalog)
    else:
        require(case.endswith('T03') and a['baseline_pool']==20 and a['expanded_pool']==22 and a['no_balance_candidate'],'Recycle budget or candidate differs')
        for prefix,n in [('baseline',20),('expanded',22)]:
            require(1<=a[prefix+'_key_ordinal']<=n and 2<=a[prefix+'_second_fire_ordinal']<=n,'Original draw ordinal differs')
        damage=lambda card:sum(catalog[card][key] for key in ['elemental_damage','secondary_elemental_damage','direct_damage'])
        base=sum(damage(card) for card in legal(hero));expanded=base+2*damage('M-FIREBAT')
        require(a['baseline_printed_damage']==base and a['expanded_printed_damage']==expanded>base,'Printed card damage differs')
        require(len(a['kill_sources'])==2,'Actual expansion sources missing')
        for k in a['kill_sources']:kill_contract(k,catalog)

def validate(directory,catalog_path,source):
    directory=Path(directory);catalog={c['id']:c for c in json.loads(Path(catalog_path).read_text())['tables']['Cards']};counts=Counter();groups=defaultdict(set);pairs=set();sums=defaultdict(Counter);witnesses={};files=[]
    for p in sorted(directory.glob('*.jsonl.gz')):
        h=hashlib.sha256();size=n=0
        with gzip.open(p,'rb') as f:
            for raw in f:
                h.update(raw);size+=len(raw);n+=1;row=json.loads(raw);row_contract(row,source,catalog);a=row['actual'];case=row['case_id'];counts[case]+=1;witnesses.setdefault(case,row)
                if case.endswith('T01'):groups[a['hero']].add((a['seed'],a['group'],a['box_element']))
                if case.endswith('T03'):
                    key=(a['hero'],a['room_seed'],a['seed']);require(key not in pairs,'Duplicate recycle observation');pairs.add(key);sums[(a['hero'],a['room_seed'])]['baseline_key']+=a['baseline_key_ordinal'];sums[(a['hero'],a['room_seed'])]['expanded_key']+=a['expanded_key_ordinal'];sums[(a['hero'],a['room_seed'])]['rows']+=1
        files.append({'path':p.name,'rows':n,'raw_bytes':size,'raw_sha256':h.hexdigest(),'stored_bytes':p.stat().st_size,'stored_sha256':hashlib.sha256(p.read_bytes()).hexdigest()})
    require(counts['PR13-B09.1-T01']==234 and counts['PR13-B09.1-T03']==27000,'Declared original matrix differs')
    require(all(len(groups[hero])==78 for hero in ['Mage','Priest','Guardian']),'Generated-group/BOX coverage differs')
    require(pairs=={(hero,room_seed,seed) for hero in ['Mage','Priest','Guardian'] for room_seed in SEEDS for start in SEEDS for seed in range(start,start+1000)},'All original recycle seeds required')
    require(all(v['rows']==3000 and v['expanded_key']>v['baseline_key'] for v in sums.values()),'Declared controlled dilution counterexample differs')
    controls=[]
    for name,case,change in [('enabled-default-policy','T01',lambda r:r['actual'].update(effective_optional_policy=True)),('wrong-source','T01',lambda r:r.update(source_sha='0'*40)),('foreign-kill-actor','T02',lambda r:r['actual']['actual'].update(actor_id='00000000-0000-0000-0000-000000000000')),('invalid-key-ordinal','T03',lambda r:r['actual'].update(expanded_key_ordinal=100))]:
        r=copy.deepcopy(witnesses['PR13-B09.1-'+case]);change(r)
        try:row_contract(r,source,catalog)
        except ValueError:controls.append({'name':name,'rejected':True})
        else:raise ValueError('Corrupt baseline evidence accepted: '+name)
    return {'ok':True,'source_sha':source,'case_rows':dict(counts),'original_files':files,'controls':controls,'controlled_recycle_summary':[{'hero':k[0],'room_seed':k[1],'rows':v['rows'],'baseline_mean_key_ordinal':v['baseline_key']/v['rows'],'expanded_mean_key_ordinal':v['expanded_key']/v['rows']} for k,v in sorted(sums.items())],'scope':'OFFLINE finishing/recycle boundaries; no natural encounter, LIVE, route benefit or RENDER acceptance','full_experiment_pending':True,'canonical_render_pending':True,'main_acceptance_granted':False}

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--native',required=True);p.add_argument('--catalog',required=True);p.add_argument('--source-sha',required=True);p.add_argument('--output',required=True);a=p.parse_args();require(not Path(a.output).exists(),'New validation required');r=validate(a.native,a.catalog,a.source_sha);Path(a.output).write_text(json.dumps(r,indent=2)+'\n');print(json.dumps({k:v for k,v in r.items() if k not in ['original_files','controlled_recycle_summary']}))
