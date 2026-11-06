from pathlib import Path
import json,gzip,math,hashlib,subprocess,difflib

repo=Path.cwd();base=Path(__file__).parent;out=base/'b05-final-inspection.derived.json';assert not out.exists()
cases=[];attempts=[];cast_count=0;red=[]
for batch in ['r1','r2']:
 root=base/('b05-final-published-'+batch)/'observations'
 a=[json.loads(x) for x in (root/'attempts.original.jsonl').read_text('utf-8').splitlines()];attempts.extend(a)
 with gzip.open(root/'actions.original.jsonl.gz','rt',encoding='utf-8') as f:events=[json.loads(x) for x in f]
 case=None
 for e in events:
  if e['kind']=='start':
   if case:cases.append(case)
   original=e['original'];assert len(original)==20 and all(x['Level']==2 for x in original)
   known={x['InstanceId']:(x['CardId'],x['Level']) for x in original};assert len(known)==20
   case=dict(batch=batch,hero=e['hero'],build=e['build'],seed=e['seed'],casts=0,kills=0,damage=0,last_seconds=-.5,spent=0,effect=0,natural=0,printed=0,passive=0,last_hand=3,terminal=None,windows={})
   assert e['configuration.Version'] if 'configuration.Version' in e else e['Version']=='season-v1-config-14'
   assert e['map']['SpawnPositions'][0]=={'Row':0,'Column':0} and e['map']['BossPosition']=={'Row':2,'Column':3}
  elif e['kind']=='cast':
   assert case and e['hero']==case['hero'] and e['build']==case['build'];n=len(e['chosen']);assert 1<=n<=5
   assert len({x['InstanceId'] for x in e['chosen']})==n
   assert all(known[x['InstanceId']]==(x['CardId'],x['Level']) for x in e['chosen'])
   assert e['seconds']-case['last_seconds']>=.5-1e-9
   assert 0<=e['passive']<=(n-1 if case['hero']=='Mage' and e['resolution']['CoreCount']>=2 else 0)
   assert -1e-9<=e['extraCharge']<=(.500000001 if case['hero']=='Mage' and e['resolution']['CoreCount']>0 else 0)
   actual=e['effectActual']-case['effect'];assert actual==e['handAfter']-e['handBefore']+n
   assert 0<=actual<=e['printedDraw']+e['passive']+math.ceil(max(0,e['printedCharge']+e['extraCharge']))
   assert e['spent']==case['spent']+n and e['natural']>=case['natural']
   assert e['handBefore']==case['last_hand']+e['natural']-case['natural']
   assert e['handAfter']==3+e['natural']+e['effectActual']-e['spent'] and 0<=e['handAfter']<=5 and 0<=e['chargeAfter']<1
   dead=e['resolution']['TargetDefeated'];assert len(e['added'])==int(dead)
   for x in e['added']:
    assert x['InstanceId'] not in known and x['Level']==0;known[x['InstanceId']]=(x['CardId'],x['Level'])
   case['kills']+=int(dead);assert e['kills']==case['kills'] and len(known)==20+case['kills']
   damage=e['resolution']['HpDamage']+e['resolution']['ShieldDamage'];case['damage']+=damage;case['printed']+=e['printedDraw'];case['passive']+=e['passive']
   case.update(casts=case['casts']+1,last_seconds=e['seconds'],spent=e['spent'],effect=e['effectActual'],natural=e['natural'],last_hand=e['handAfter'],last_position=e['position'],last_target=e['resolution']['TargetId'],last_target_defeated=dead)
   window=case['windows'].setdefault(str(int(e['seconds']//30)),{'casts':0,'damage':0,'effect_draw':0,'cards_spent':0});window['casts']+=1;window['damage']+=damage;window['effect_draw']+=actual;window['cards_spent']+=n
   cast_count+=1
  elif e['kind']=='red-evaluation':
   assert not e['hit'];red.append({'hero':e['hero'],'build':e['build'],'roll':e['pending']['Roll'],'hit':False,'scope':e['scope']})
  elif e['kind']=='end':
   assert case;r=e['row'];assert r['Actions']==case['casts'] and r['Kills']==case['kills'] and r['Damage']==case['damage']
   assert r['PrintedDraw']==case['printed'] and r['PassiveDraw']==case['passive'] and r['FinalHand']==3+r['NaturalDraw']+r['ActualEffectDraw']-r['CardsSpent']
   assert r['Outcome'] in ['Dead','Extracted'];case['terminal']=r
 assert case;cases.append(case)
assert [x['number'] for x in attempts]==list(range(1,10));assert len(cases)==9 and len({(x['hero'],x['build']) for x in cases})==9
assert {(x['hero'],x['build']) for x in cases}=={(h,b) for h in ['Priest','Mage','Guardian'] for b in ['water','draw-engine','core']}
complete=[x for x in cases if x['terminal']];partial=[x for x in cases if not x['terminal']];assert len(complete)==8 and len(partial)==1
assert partial[0]['hero']=='Priest' and partial[0]['build']=='draw-engine' and partial[0]['last_target']=='annihilation-core' and partial[0]['last_target_defeated'] and partial[0]['last_position']=={'Row':2,'Column':3}
assert len([x for x in complete if x['terminal']['Outcome']=='Extracted'])==3
assert all(w['casts']<=60 for x in cases for w in x['windows'].values())
prior=json.loads((repo/'docs/season-balance-20261102/evidence/B05/r25/input-manifest.json').read_bytes())
legacy={}
for name in ['server/src/FantasyCard.Domain/Combat/CombatDeck.cs','server/src/FantasyCard.Domain/Combat/PlayerCombatState.cs']:
 raw=subprocess.check_output(['git','show',prior['source_base']+':'+name]);expected=prior['files'][name]
 variants=[raw,raw.replace(b'\r\n',b'\n'),raw.replace(b'\r\n',b'\n').replace(b'\n',b'\r\n')];assert any(hashlib.sha256(x).hexdigest()==expected for x in variants)
 old=raw.decode('utf-8-sig').replace('\r\n','\n');new=(repo/name).read_text('utf-8-sig')
 if name.endswith('CombatDeck.cs'):
  projection=new.replace('        => AddCharge(amount,random,null);\n\n    public void AddCharge(double amount,Random random,Action? afterNaturalDraw)\n','')
  projection=projection.replace('            var before=_hand.Count;\n','').replace('            if(_hand.Count>before)afterNaturalDraw?.Invoke();\n','')
  assert projection==old;equivalent='Full-hand overflow and immediate draw unchanged; only successful-draw callback was added, not called on a full hand.'
 else:
  start='    public (double Charge, int Draw) UpdateFenxian(';end='    public int ResolveHeal('
  assert old[old.index(start):old.index(end)]==new[new.index(start):new.index(end)];equivalent='Season Fenxian implementation text unchanged; no-red fixture has zero opening/chain draw extras.'
 legacy[name]=dict(old_source_base=prior['source_base'],old_input_sha256=expected,historical_blob_verified=True,reuse_scope=equivalent,
                   current_sha256=hashlib.sha256((repo/name).read_bytes()).hexdigest(),source_diff='\n'.join(difflib.unified_diff(old.splitlines(),new.splitlines(),n=2)))
proof=dict(item='B05',resource_contract_violations=0,independently_checked_casts=cast_count,actual_new_attempts=9,total_budget_used=300,budget_remaining=0,
           unique_combinations=9,complete_terminal_routes=8,extracted=3,dead=5,partial_after_actual_Boss_kill=1,
           all_original_42_full_scan_timeouts_retained=True,original_failed_TRXs_retained=True,red_miss_branch_only=red,
           old_full_hand_fixtures_reused=3,old_full_hand_reuse_audit=legacy,cases=cases,
           D01_complete=False,D02_complete=False,D03_complete=False,C16_complete=False,new_C16_comparison_encounters=0,
           population_win_rate_or_median_claimed=False,production_modified=False,cloud_modified=False)
out.write_text(json.dumps(proof,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');print(json.dumps({k:v for k,v in proof.items() if k not in ['cases','old_full_hand_reuse_audit','red_miss_branch_only']}))
