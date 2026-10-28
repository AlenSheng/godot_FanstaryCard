"""Cloud-only independent byte, card-identity and diagnostic ledger verification."""
import gzip,hashlib,json,math
from collections import Counter
from pathlib import Path

SPECIES={'fire-bat':'FireBat','thorn-mite':'ThornMite','murk-snail':'MudHydra','sand-lizard':'SandLizard','rust-rat':'RustRat','box-spirit':'BoxSpirit','metal-guard':'GoldGuard','fire-herald':'FireReaver','marsh-mother':'SwampMother','stone-guard':'StoneGuard','thorn-guard':'ThornGuard','annihilation-core':'VoidCore'}
def require(value,reason):
 if not value:raise ValueError(reason)
def read_gzip(path,stored_bytes,stored_sha,raw_bytes,raw_sha):
 h=hashlib.sha256()
 with path.open('rb') as f:
  for chunk in iter(lambda:f.read(1024**2),b''):h.update(chunk)
 require(path.stat().st_size==stored_bytes and h.hexdigest()==stored_sha,'Original stored bytes differ');h=hashlib.sha256();n=0
 with gzip.open(path,'rb') as f:
  for raw in f:
   h.update(raw);n+=len(raw);yield json.loads(raw)
 require(n==raw_bytes and h.hexdigest()==raw_sha,'Original raw bytes differ')
def pool(snapshot):return snapshot['Hand']+snapshot['Library']+snapshot['Discard']
def validate(directory,expected_source=None,expected_samples=None,expected_config=None):
 d=Path(directory);m=json.loads((d/'manifest.original.json').read_bytes());s=json.loads((d/'summary.original.json').read_bytes());n=m['samples'];require(s['passed'] and s['actual_errors']==0 and s['actual_encounters']==2*n,'Native part incomplete or failed');require(expected_samples is None or n==expected_samples,'Physical sample count differs');require(expected_source is None or m['source_sha']==expected_source,'Source differs');require(m['group'] in ['O1','O6','E1','BOSS'] and m['strategy'] in ['baseline_all_hand','basic','build'],'Stratum differs');require(m['cutoff_seconds']==600 and m['tick_ms']==100 and m['action_interval_seconds']==.4 and m['card_level']==m['weapon_level']==0 and m['equipment']=='Empty','Resource/time conditions differ');require(m['full_required_encounters']==216000 and m['required_paired_seeds_per_stratum']==3000 and m['required_independent_blocks']==3,'Original denominator changed');require(m['seed_start']==450001+1000*m['block']+m['offset'],'Original seed interval changed');require(not any(m['fixed_effective_rules'][k] for k in ['CardsSpentDraw','FractionalGuardian','OptionalMonsterPool','BudgetedBotLoot','MortalBotPve']),'Candidates enabled');cards={c['CardId']:c for c in m['actual_card_definitions']};a=m['baseline_deck'];b=m['candidate_deck'];prefix={'Mage':'MAG','Priest':'PRI','Guardian':'GUA'}[m['hero']];expected=[f'C{i:02}' for i in range(1,14)]+[f'{prefix}-{i:02}' for i in range(1,8)];require(a==expected and b==['C17' if c=='C01' else c for c in a] and len(set(a))==len(set(b))==20,'Actual default or one-card candidate differs')
 if expected_config is not None:
  for field in ['config_version','config_sha256','embedded_resource_bytes','embedded_resource_bytes_sha256','actual_card_definitions','fixed_effective_rules']:require(m[field]==expected_config[field],'Frozen actual config input differs: '+field)
 def budget(ids):return {'Rarity':sum(cards[i]['Rarity'] for i in ids),'UnlockCost':sum(cards[i]['UnlockCost'] for i in ids),'CopyCost':sum(cards[i]['CopyCost'] for i in ids)}
 require(m['baseline_budget']==budget(a)==budget(b)==m['candidate_budget'],'Explicit full budget differs');require(m['embedded_resource_bytes']>0 and len(m['embedded_resource_bytes_sha256'])==64,'Actual embedded input identity absent');keys=set();outcomes=Counter();results={}
 for row in read_gzip(d/'encounters.original.jsonl.gz',s['stored_bytes'],s['stored_sha256'],s['original_raw_bytes'],s['original_raw_sha256']):
  key=(row['Seed'],row['Profile']);require(key not in keys and row['Hero']==m['hero'] and row['Group']==m['group'] and row['Strategy']==m['strategy'] and row['SeedBlock']==m['block'],'Native encounter identity differs');keys.add(key);results[key]=row;require(row['Outcome'] in ['Victory','Death','Censored','Error'] and row['Error'] is None and 0<=row['ObservedSeconds']<=600,'Outcome or cutoff differs');outcomes[row['Outcome']]+=1
 expected_keys={(seed,arm) for seed in range(m['seed_start'],m['seed_start']+n) for arm in ['ActualPublishedDefault','SingleCardCandidate']};require(keys==expected_keys and dict(outcomes)==s['outcomes'],'Full encounter denominator differs');state={};event_counts=Counter();wait_reasons=Counter();total_events=0;exits={};reshuffles=0
 for part in s['observer_parts']:
  count=0
  for r in read_gzip(d/part['file'],part['stored_bytes'],part['stored_sha256'],part['raw_bytes'],part['raw_sha256']):
   count+=1;total_events+=1;kind=r['kind'];event_counts[kind]+=1;ident=r['identity'];key=(ident['Seed'],ident['Profile']);require(key in keys and ident['Hero']==m['hero'] and ident['Group']==m['group'] and ident['Strategy']==m['strategy'],'Event identity differs')
   if kind=='entry':
    require(key not in state,'Duplicate entry');p=r['snapshot']['Players'][0];cs=r['original_instances'];ids={c['InstanceId']:(c['CardId'],c['Level']) for c in cs};require(len(cs)==len(ids)==20 and all(level==0 for _,level in ids.values()),'Original twenty instances differ');require(sorted(c['CardId'] for c in cs)==sorted(a if key[1]=='ActualPublishedDefault' else b),'Entry cards differ');require(len(r['hand'])==3 and len(r['library'])==17 and not r['discard'] and r['Shield']==r['WeaponLevel']==r['DrawCharge']==0 and r['Hp']==r['MaximumHp']=={'Mage':70,'Priest':80,'Guardian':100}[m['hero']],'Opening resources differ');state[key]={'known':ids,'original':set(ids),'player':p['PlayerId'],'entry':r,'cast_count':0}
   else:
    require(key in state,'Event before entry');st=state[key]
    def check_deck(deck):
     cs=pool(deck);actual={c['InstanceId']:(c['CardId'],c['Level']) for c in cs};require(len(cs)==len(actual) and actual==st['known'] and st['original'].issubset(actual),'Original/current pool identity or count differs')
    if kind=='legal_kill_card':
     c=r['card'];require(c['InstanceId'] not in st['known'] and c['Level']==0,'Added card duplicated');old=r['before']['Players'][0]['Pve']['Monsters'];new=r['after']['Players'][0]['Pve']['Monsters'];source=r['source_monster_id'];require(any(x['MonsterId']==source and x['Hp']>0 for x in old) and any(x['MonsterId']==source and x['Hp']<=0 for x in new),'No actual legal kill transition');species=source[:-2] if source.endswith(('-a','-b')) else source;require(SPECIES.get(species)==r['source_monster_type']==cards[c['CardId']]['MonsterType'],'New card species differs');st['known'][c['InstanceId']]=(c['CardId'],c['Level'])
    elif kind=='waiting':
     check_deck(r);reason=r['reason'];wait_reasons[reason]+=1;require(not reason.startswith('strategy_hold') or r['strategy_hold'],'Hold reason conflated');require(reason not in ['empty_hand','empty_hand_recyclable_discard'] or not r['Hand'],'Empty hand reason differs');require(reason!='empty_hand_recyclable_discard' or (not r['Library'] and bool(r['Discard'])),'Recyclable discard reason differs')
    elif kind=='cast':
     st['cast_count']+=1;before=r['before']['Players'][0]['Combat']['Deck'];after=r['after']['Players'][0]['Combat']['Deck'];old={c['InstanceId'] for c in before['Hand']};chosen={c['InstanceId'] for c in r['selected_instances']};require(len(chosen)==len(r['selected_instances']) and chosen.issubset(old),'Selected instances not uniquely in original hand');redistributed=chosen-set(c['InstanceId'] for c in after['Discard']);require(not redistributed or (len(before['Library'])<len(after['Hand']) and len(after['Discard'])<len(before['Discard'])+len(chosen)), 'Played instance outside discard without a real immediate reshuffle boundary');check_deck(after);require(r['actual']['RoomRevision']>r['before']['Revision'] and r['heal_overflow']==max(0,r['requested_heal']-r['effective_heal']),'Actual effect ledger differs')
    elif kind=='natural_draw':require(all(c['InstanceId'] in st['known'] for c in r['drawn_original_instances']),'Unknown natural drawn card')
    elif kind=='reshuffle_draw':
     check_deck(r['after']);require(not r['before']['Library'] and r['before']['Discard'] and all(c['InstanceId'] in {x['InstanceId'] for x in r['before']['Discard']} for c in r['drawn_original_instances']),'Actual reshuffle differs');reshuffles+=1
    elif kind=='exit':require(key not in exits and r['original_twenty_retained'] and r['error'] is None and r['outcome']==results[key]['Outcome'] and r['actual_casts']==st['cast_count'],'Final denominator/identity differs');exits[key]=r
    else:raise ValueError('Unknown diagnostic event')
  require(count==part['rows'],'Part event rows differ')
 require(set(state)==set(exits)==keys and total_events==s['observer_events'],'Event ledger denominator incomplete');return {'ok':True,'source_sha':m['source_sha'],'hero':m['hero'],'group':m['group'],'strategy':m['strategy'],'block':m['block'],'seed_start':m['seed_start'],'samples':n,'encounters':2*n,'outcomes':dict(outcomes),'event_counts':dict(event_counts),'wait_reason_counts':dict(wait_reasons),'actual_reshuffle_witnesses':reshuffles,'embedded_resource_bytes_sha256':m['embedded_resource_bytes_sha256'],'fixed_default_policies_off':True,'actual_twenty_original_instances_and_legal_additions_verified':True,'complete_gzip_SHA_and_CRC_verified':True,'formal_full_denominator_still_required':True,'MAIN_accepted':False}

if __name__=='__main__':
 import sys
 if len(sys.argv)==5:require(sys.argv[2]=='--reference','Frozen reference argument required');reference=json.loads(Path(sys.argv[3]).read_bytes());source=sys.argv[4]
 else:reference=None;source=None
 result=validate(sys.argv[1],expected_source=source,expected_samples=20 if reference is not None else None,expected_config=reference);p=Path(sys.argv[1])/'independent-part-validation.original.json';require(not p.exists(),'Original validation already exists');p.write_bytes((json.dumps(result,indent=2)+'\n').encode());print(json.dumps(result))
