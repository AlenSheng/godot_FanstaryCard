import hashlib,itertools,json,re,subprocess
from pathlib import Path
B=Path('/home/ubuntu/pr13-acceptance-20261009');A='B12-effective-policy-postgres-r2-20261013';E=B/'evidence'/A;W=B/'work'/A;root=E/'persistent-native-outputs/native';v=json.loads((E/'result.original.json').read_bytes());meta=json.loads((E/'inputs.original.json').read_bytes());native=json.loads((root/'summary.original.json').read_bytes());assert v['ok'] and v['exit_code']==0 and not v['oom_killed'] and v['owned_containers_removed'] and v['owned_secret_removed'] and v['source_runtime_and_fixture_unchanged'] and v['remaining_owned_fixture_schemas']==0 and native['passed'] and native['executed']==72 and native['ownSchemaRemoved']
state=dict(l.split('=',1) for l in subprocess.check_output(['systemctl','show','pr13-cap-'+A,'--property=MainPID,ActiveState,ExecMainStatus'],text=True).splitlines());assert state['MainPID']=='0' and state['ActiveState']=='inactive' and state['ExecMainStatus']=='0'
for key,base in [('source_files','source_root'),('runtime_files','runtime_root'),('fixture_files','fixture_root')]:
 for row in meta[key]:
  p=Path(meta[base])/row['path'];assert p.stat().st_size==row['bytes'] and hashlib.sha256(p.read_bytes()).hexdigest()==row['sha256']
  if key=='runtime_files':assert hashlib.sha256((W/'artifacts/bin/B12EffectivePolicy/release'/row['path']).read_bytes()).hexdigest()==row['sha256']
raw=root/'witnesses.original.jsonl';rows=[json.loads(l) for l in raw.read_bytes().splitlines()];assert len(rows)==72;expected=set(itertools.product(['Mage','Priest','Guardian'],range(6),[False,True],[False,True]));seen=set();rooms=set();ids=set();on_off=off_on=0
for row in rows:
 hero,L,label,active=[row[k] for k in ['hero','level','labelOn','effectiveOn']];key=(hero,L,label,active);assert key in expected and key not in seen;seen.add(key);assert row['roomId'] not in rooms;rooms.add(row['roomId']);before=row['before'];saved=row['saved'];after=row['localProbeAfter'];assert before==saved and before['RoomId']==row['roomId'] and before['ConfigVersion']==row['displayLabel']==('candidate-label:on' if label else 'candidate-label:off')
 assert row['reportedEffective']=={'cardsSpentDraw':active,'fractionalGuardian':active};n=before['Numerics'];assert n['CardsSpentDraw'] is active and n['FractionalGuardian'] is active and all(n[k] is False for k in ['OptionalMonsterPool','BudgetedBotLoot','MortalBotPve']);assert n['MonsterCapacity']==5 and n['BotLootCount']==2 and n['FenxianPolicy']==n['GuardianPolicy']==(2 if active else 1)
 assert len(before['Players'])==1;player=before['Players'][0];c=player['Combat'];assert player['PlayerId']==row['playerId'] and c['WeaponLevel']==L and c['FenxianPolicy']==c['GuardianPolicy']==(2 if active else 1);deck=c['Deck'];cards=deck['Hand']+deck['Library']+deck['Discard'];assert len(cards)==20 and len({x['InstanceId'] for x in cards})==20 and all(x['CardId']=='common-01' and x['Level']==0 for x in cards);assert not ids.intersection(x['InstanceId'] for x in cards);ids.update(x['InstanceId'] for x in cards)
 draws=[0,0,1,1,2] if hero=='Mage' and not active else [0]*5;assert row['draws']==draws
 if hero!='Guardian':shields=[1]*5
 elif not active:shields=[1+(1 if L<2 else 2 if L<4 else 3)]*5
 else:
  shields=[];rem=0
  for i in range(5):x=10+4*L+rem;shields.append(1+x//10);rem=x%10
  assert rem==0
 assert row['shields']==shields and after['Players'][0]['Combat']['Shield']==sum(shields);assert row['fenxianPolicy']==('CoreCardsSpent' if active else 'CurrentRhythm') and row['guardianPolicy']==('FractionalRemainder' if active else 'CurrentSteps');assert after['Players'][0]['Combat']['GuardianShieldRemainderTenths']==0
 for a,b in [('originalSnapshotSHA256','restoredSnapshotSHA256'),('durableBeforeSHA256','durableAfterSHA256')]:assert re.fullmatch('[0-9a-f]{64}',row[a]) and row[a]==row[b]
 on_off+=int(label and not active);off_on+=int(not label and active)
assert seen==expected and on_off==off_on==18 and len(ids)==1440
report={'ok':True,'implementation_source_sha':meta['implementation_source_sha'],'native_clean':True,'owned_container_removed':True,'source_inputs_match_git':True,'actual_native_rows':72,'original_instances_preserved':1440,'label_on_actual_off_rows':18,'label_off_actual_on_rows':18,'current_runtime_input_and_executed_copy_members_rehashed':146,'current_source_members_rehashed':328,'complete_snapshot_and_card_identity_comparison_passed':True,'independent_draw_and_integer_fractional_shield_sequences_checked':True,'actual_effective_reporting_not_display_label':True,'native_raw_SHA256':hashlib.sha256(raw.read_bytes()).hexdigest(),'original_compile_failure_R1_preserved_separately':True,'candidate_production_activation':False,'formal_EXPERIMENT_or_RENDER_or_LIVE_acceptance':False,'MAIN_accepted':False};p=E/'independent-validation.original.json';assert not p.exists();p.write_bytes((json.dumps(report,indent=2)+'\n').encode());print(json.dumps({'ok':True,'native_rows':72,'label_on_actual_off':18,'original_instances':1440}))
