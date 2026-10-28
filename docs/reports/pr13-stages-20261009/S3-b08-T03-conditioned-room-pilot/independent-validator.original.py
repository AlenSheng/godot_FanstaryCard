import gzip,hashlib,json
from collections import Counter
from pathlib import Path
def validate(root,samples,block,expected_strata=120):
 root=Path(root);states={}
 with gzip.open(root/'states.original.jsonl.gz','rt',encoding='utf-8') as f:
  for line in f:
   row=json.loads(line);text=row['original_state_json'];h=row['sha256'];assert h not in states and hashlib.sha256(text.encode()).hexdigest()==h;s=json.loads(text);p=s['Players'][0];c=p['Combat'];deck=c['Deck'];cards=deck['Hand']+deck['Library']+deck['Discard'];assert len(cards)==20 and len({x['InstanceId'] for x in cards})==20 and all(x['Level']==0 for x in cards);states[h]={'revision':s['Revision'],'policy':s['Numerics'],'hp':c['Hp'],'max_hp':c['MaximumHp'],'shield':c['Shield'],'weapon':c['WeaponLevel'],'remainder':c['GuardianShieldRemainderTenths'],'guardian_policy':c['GuardianPolicy'],'fenxian_policy':c['FenxianPolicy'],'cards':{x['InstanceId']:(x['CardId'],x['Level']) for x in cards},'hand':[x['InstanceId'] for x in deck['Hand']],'discard':[x['InstanceId'] for x in deck['Discard']],'battle_id':p['Pve']['BattleId']}
 seen=set();pairs={};by_condition=Counter();strata=set()
 with gzip.open(root/'witnesses.original.jsonl.gz','rt',encoding='utf-8') as f:
  for line in f:
   w=json.loads(line);key=tuple(w[k] for k in ('hero','group','element','level','block','seed','arm','condition'));assert key not in seen;seen.add(key);assert w['block']==block and 440001+block*1000<=w['seed']<440001+block*1000+samples and not w['candidate_activation'];strata.add(key[:4]);by_condition[w['condition']]+=1;a=states[w['before']];b=states[w['after']];maximum=a['max_hp']//2;assert maximum==w['shield_cap'] and a['shield']==w['initial_shield'] and a['hp']==a['max_hp'];assert b['revision']==a['revision']+1 and a['policy']==b['policy'] and not any(a['policy'][k] for k in ('CardsSpentDraw','FractionalGuardian','OptionalMonsterPool'));assert a['cards']==b['cards'] and w['selected'] in a['hand'] and w['selected'] not in b['hand'] and b['discard'].count(w['selected'])==1;assert a['remainder']==b['remainder']==0 and a['guardian_policy']==b['guardian_policy']==1 and a['fenxian_policy']==b['fenxian_policy']==1
   requested=w['requested'];effective=min(requested,maximum-a['shield']);overflow=requested-effective;assert requested>=0 and effective==w['effective']==w['resolution']['ShieldGain'] and overflow==w['overflow'] and b['shield']==a['shield']+effective;preview=dict(w['preview']);preview['RoomRevision']=w['resolution']['RoomRevision'];assert preview==w['resolution']
   if w['condition']=='zero-printed-full':assert w['card_id']=='C01' and w['printed_shield']==requested==effective==overflow==0 and a['shield']==maximum
   else:
    assert w['card_id']=='C17' and w['printed_shield']>0 and requested>0
    if w['condition']=='full':assert a['shield']==maximum and effective==0 and overflow==requested
    elif w['condition']=='one-capacity':assert a['shield']==maximum-1 and effective==1 and overflow==requested-1
    elif w['condition']=='empty':assert a['shield']==0 and effective>0
    else:raise ValueError('Unknown frozen condition')
   pairkey=tuple(w[k] for k in ('hero','group','element','level','block','seed','condition'));arms=pairs.setdefault(pairkey,{})
   assert w['arm'] not in arms;arms[w['arm']]={'items':w['items'],'cards':a['cards'],'battle_id':a['battle_id']}
 for arms in pairs.values():
  assert set(arms)=={'BaselinePurple','SingleOrangeHead'};a=arms['BaselinePurple'];b=arms['SingleOrangeHead'];assert a['cards']==b['cards'] and a['battle_id']==b['battle_id'];changes=[]
  for x,y in zip(a['items'],b['items']):
   assert x['ItemId']==y['ItemId'] and x['Slot']==y['Slot'];different={k for k in x if x[k]!=y[k]}
   if different:assert different=={'Quality'} and x['Slot']=='Head' and x['Quality']=='Purple' and y['Quality']=='Orange';changes.append(x['Slot'])
  assert changes==['Head']
 expected=expected_strata*samples*2*4;assert len(seen)==expected and len(strata)==expected_strata and set(by_condition)=={'full','one-capacity','empty','zero-printed-full'} and all(n==expected_strata*samples*2 for n in by_condition.values());return {'ok':True,'samples':samples,'block':block,'strata':len(strata),'actual_witnesses':len(seen),'original_state_count':len(states),'paired_unchanged_instance_and_one_quality_change_checks':len(pairs),'condition_counts':dict(by_condition),'formal_EXPERIMENT_accepted':False,'MAIN_accepted':False}
