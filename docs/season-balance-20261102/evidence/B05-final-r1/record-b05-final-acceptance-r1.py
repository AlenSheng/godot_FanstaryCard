from pathlib import Path
import json,hashlib,shutil,subprocess,xml.etree.ElementTree as E

repo=Path.cwd();base=Path(__file__).parent;p=repo/'docs/season-balance-20261102';out=p/'evidence/B05-final-r1';assert not out.exists()
analysis=json.loads((base/'b05-final-inspection.derived.json').read_bytes());assert analysis['independently_checked_casts']==2214 and analysis['resource_contract_violations']==0 and analysis['total_budget_used']==300
for batch,expected,code in [('r1',2,1),('r2',7,0)]:
 root=base/('b05-final-published-'+batch);r=json.loads((root/'result.json').read_bytes());assert r['new_started_routes']==expected and r['exit']==code and r['source_unchanged'] and r['binary_unchanged']
 tree=E.fromstring((root/'results/final-nine.trx').read_bytes());counts=next(x.attrib for x in tree.iter() if x.tag.endswith('Counters'));assert counts['notExecuted']=='0' and counts['failed']==str(code)
pin=json.loads((base/'b05-final-local-build-r3/source-pin.json').read_bytes());assert all(hashlib.sha256((repo/n).read_bytes()).hexdigest()==h for n,h in pin.items())
out.mkdir(parents=True)
for stage in ['b05-final-local-build-r1','b05-final-local-build-r2','b05-final-local-build-r3','b05-final-published-r1','b05-final-published-r2']:
 source=base/stage
 for file in source.rglob('*'):
  if file.is_file() and 'build' not in file.relative_to(source).parts:
   target=out/stage/file.relative_to(source);target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(file,target)
for name in ['run-b05-final-build-r1.py','run-b05-final-build-r2.py','run-b05-final-build-r3.py','run-b05-final-published-r1.py','run-b05-final-published-r2.py',
             'inspect-b05-final-resources-r1.py','capture-b05-frozen-inputs-r1.py','record-b05-final-acceptance-r1.py','b05-final-inspection.derived.json',
             'b05-frozen-input-capture.derived.json','b05-budget-after-final-r1.original.json','b05-final-contract-before-remaining-seven.original.json']:
 shutil.copyfile(base/name,out/name)
budget=dict(item='B05',maximum=300,old_routes=288,old_boundary_fixtures=3,old_total=291,current_first_batch_started=2,current_second_batch_started=7,
            used=300,remaining=0,repeat_any_B05_match_forbidden=True,old_budget_immutable='evidence/B05/test-budget.json',actual_new_terminal_routes=8,partial_after_actual_Boss_kill=1)
(p/'B05-BUDGET.json').write_text(json.dumps(budget,indent=2)+'\n',encoding='utf-8');(out/'budget.json').write_text(json.dumps(budget,indent=2)+'\n',encoding='utf-8')
result=dict(status='B05_resource_contract_verified',completed_items=24,total_items=35,actual_new_attempts=9,complete_terminal_routes=8,extracted=3,dead=5,post_Boss_red_tail_failure=1,
            independently_checked_casts=2214,resource_contract_violations=0,old_fullhand_fixtures_reused=3,budget=budget,
            original_r25_full_scan_failed=True,original_42_timeouts_not_reclassified=True,current_r1_TRX_failed=True,current_r2_TRX_passed=True,
            current_r2_actual_routes=7,all9_one_green_batch_claimed=False,full_population_win_rate_claimed=False,
            semantic_reuse_proof='b05-final-inspection.derived.json',frozen_inputs='b05-frozen-input-capture.derived.json',
            full_original_binary_directories=[str(base/'b05-final-local-build-r1/build'),str(base/'b05-final-local-build-r3/build')],
            local_reserve_GiB=2,local_startup_GiB=1,compiled_source_unchanged=True,production_sources_changed=False,
            cloud_modified=False,capacity100_retest=False,C16_encounters=121,C16_new_comparison_encounters=0,
            D01_complete=False,D02_complete=False,D03_complete=False,F02_complete=False,whole_goal_complete=False,
            remaining_items=['C01','C16','D01','D02','D03','D04','E01','E02','F01','F02','F03'])
(out/'result.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
m={'files':{f.relative_to(out).as_posix():hashlib.sha256(f.read_bytes()).hexdigest() for f in out.rglob('*') if f.is_file()}}
(out/'manifest.json').write_text(json.dumps(m,indent=2)+'\n',encoding='utf-8')
report=p/'B05-RESOURCE-ACCEPTANCE.md';assert not report.exists();report.write_text('''# B05 完整卡组与资源返牌验收

B05的资源机制契约通过，整体24/35。当前正式配置14新增9次尝试，逐施法2214条独立复核无资源契约违例；保留旧288路线和3项满手/印刷抽牌边界原件。完整职业效率、路线胜率、六难度平衡与持久化不由本项代替，D01/D02/D03、C16和F02继续未通过。证据见[evidence/B05-final-r1/result.json](evidence/B05-final-r1/result.json)。

## 当前输入和真实过程

三职业各运行water/draw-engine/core合法20张图鉴卡组。永久卡/专武输入假定+5，D2实际只生效+2，季装为一橙四紫+3、三件主题主抗两件副抗；不穿红装、不改怪物、不回满血或重置牌库。构筑标签是本项资源压力控制，不能据此宣称C16已有三类有效流派；祭司water/core在本目录下可选择相同卡表。

从73150开始只按原生出生(0,0)与Boss(2,3)条件找种子，首个73179；不编辑格、出生或Boss。实际路线为原提案八格R1，四邻且不向外，五外层/一中层小怪/一精英/一Boss。保留完整原地图和输入卡实例。这是明确条件图，不是随机地图平均路线。

全部施法调用实际BattleRoom、Resolver和100ms意图时钟。独立读原JSON逐条检查：实耗手牌实例唯一；总池恰为20加实际击杀；每次击杀加入原怪物卡+0至弃牌且不复造；实际瞬抽/蓄能和自然抽牌与手牌账相等；手牌不超过5、蓄能不囤到1；印刷返牌加受限法师被动能解释所有效果进手；法师单核不给被动瞬抽、多核被动不超过本次实耗减1；每成功施法至少500ms。30秒窗口最多60次成功执行。原始伤害和进手按窗口保存，不把施法上限冒充职业DPS目标已达标。

## 真实结果和保留失败

旧r25仍是3边界通过/1矩阵门槛失败，288路线中42条在额外1200秒全图扫描观察窗结束时仍活动，不能写成时间不推进、血量异常或已通过终局。其132撤离/114死亡和116426条原施法不改。当前按原提案R1补资源契约证据，完整全图耗时/职业效率仍交D02/D03。

新r1首场祭司water合法死亡，314.6秒、165次施法、10杀；第二场祭司draw-engine已实际击杀Boss并加入第12张怪物卡，398.3秒、427次施法，但普通奖励前缺独立红装裁决，原TRX失败、终态行缺失。该场不补造终态、不算撤离，也未重跑。

只对尚未开始的其余7组合运行r2，1个Fact通过、7条终态记录。合并当前8条终态为3撤离/5死亡，另1条上述Boss后交接失败。不能称9场全绿。法师draw-engine撤离198.5秒、盾draw-engine409.5秒、盾core636.8秒；该单种子条件图不支持群体成功率、P50/P90或约15%职业效率结论。死亡属于正常结果，盾100、牧80、法70及合法生命扩展不据此报异常。

新7场只在实际原骰点使正式SeasonRed.Hits返回false时调用领域Miss分支；已到Boss的三例原骰均8423。命中会明确停止，不能伪造未掉落。该领域分支不代表真实数据库周配额、红装发放或持久化已重测；C11原PG证据独立保留。r2的int.Parse区域性分析错误发生在构建阶段、零新增场，已加InvariantCulture后重新构建成功，原失败保留。

## 证据复用和预算

旧3项满手/印刷抽牌边界不重跑。原冻结输入中的CombatDeck与PlayerCombatState已用历史Git原件逐字节验SHA：满手溢出/瞬抽逻辑只多了成功自然抽牌回调，满手分支不调用；UpdateFenxian方法文本未变。本项非红装配置无开场/连锁红特性，当前15个实际满手tick也保持蓄能小于1。完整源码差异、投影与复用范围在派生检查中记录，不把整个文件描述成未变。

账本为288旧路线+3旧边界+2新首批+7新续批=300，余0。当前权威预算为[B05-BUDGET.json](B05-BUDGET.json)，旧evidence/B05/test-budget.json保留为291历史快照。所有B05场次禁止再追加，也不通过改名或重置计数重跑；后续D项有自己的真实领域范围和预算，不能冒用它来替换本项失败。

原始TRX、压缩逐施法、逐尝试、终态、输入SHA和构建日志均保留。前两版夹具源码按记录编辑逆向恢复后，逐字节匹配原冻结SHA；归档明确注明是运行后恢复，不伪称初始抓取时间。完整编译二进制原件仍在G:/PR13Evidence/season-balance-20261102-r1，当前源码/程序集前后SHA一致。资源守卫沿2GiB保留加1GiB启动，进程无窗口/BelowNormal且顺序运行；云端未修改，未补测100人或重跑C15界面。

下一步C16剩余179遭遇内处理主题/职业/有效构筑校准，再冻结C01和推进D/E/F。生产未激活/部署/重启，目标仍继续。
''',encoding='utf-8')
data=json.loads((p/'PROGRESS.json').read_bytes());assert sum(x['status']=='complete' for x in data['items'])==23
for item in data['items']:
 if item['id']=='B05':
  assert item['status']=='in_progress';item['status']='complete';item['note']+=' 当前资源契约收口：正式14条件R1新增9尝试，2214原施法独立核对零资源违例；旧3满手控制按已验旧Git原件和精确逻辑差异复用。旧42全图超时及新首批红裁决衔接失败不追认为通过；8实际终态3撤离/5死亡，1祭司draw-engine打完Boss后缺终态。只续跑未开始7组合通过，原骰8423按真实Hits=false处理领域Miss，不冒称PG配额。账本现300/300余0，权威B05-BUDGET.json，禁止追加或用D项换名重跑。职业效率/完整路线/群体平衡仍D02/D03及C16，整体24/35。'
  item['evidence']+=['B05-RESOURCE-ACCEPTANCE.md','B05-BUDGET.json','evidence/B05-final-r1/result.json','evidence/B05-final-r1/b05-final-inspection.derived.json']
assert sum(x['status']=='complete' for x in data['items'])==24;(p/'PROGRESS.json').write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
readme=p/'README.md';text=readme.read_text('utf-8').replace('当前完成A01至A05、B01至B04、C02至C15，共23/35项','当前完成A01至A05、B01至B05、C02至C15，共24/35项')
text=text.replace('接续B05剩余合法路线/循环证据、C16平衡及其余C/D/E/F共12项。','接续C16平衡、C01冻结及其余D/E/F共11项。').replace('B05仍291/300、余9，C16仍121/300。','B05已收口且300/300余0，C16仍121/300。')
text+='\n\n## 当前接续：B05资源契约通过，整体24/35\n\n当前正式14自然条件R1新增9尝试，2214施法独立核对零资源违例；8条终态3撤离/5死亡，1祭司draw-engine实际打完Boss但红裁决衔接失败，原TRX与缺终态保留，不重跑。只续跑尚未开始7组合通过；旧3满手控制经原Git哈希/逻辑复用，旧42全图观察窗超时不追认为通过。权威预算[B05-BUDGET.json](B05-BUDGET.json)为300/300、余0，后续禁止新增B05，详见[B05验收](B05-RESOURCE-ACCEPTANCE.md)。\n\n当前无存活测试句柄，源/程序集SHA一致，本机2GiB/1GiB启动保留；云端未修改。C16仍121/300余179，继续主题/职业/有效构筑校准，完整D/E/F与C01仍未通过。未补测100人、重跑C15 UI或部署/重启生产。\n'
readme.write_text(text,encoding='utf-8')
print(json.dumps({'files':len(m['files']),'new_attempts':9,'casts_checked':2214,'B05_budget':300,'remaining_budget':0,'overall':'24/35'}))
