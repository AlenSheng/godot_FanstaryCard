from pathlib import Path
import json,hashlib,shutil,xml.etree.ElementTree as E

repo=Path.cwd();base=Path(__file__).parent;p=repo/'docs/season-balance-20261102';out=p/'evidence/C16-expansion-r1';assert not out.exists()
a=json.loads((base/'c16-expansion-inspection-r1.derived.json').read_bytes());assert a['new_encounters']==78 and a['outcomes']=={'Win':78} and a['resource_conservation_verified']
pin=json.loads((base/'c16-remaining-build-r1/source-pin.json').read_bytes());assert all(hashlib.sha256((repo/n).read_bytes()).hexdigest()==h for n,h in pin.items())
budget=json.loads((p/'C16-BUDGET.json').read_bytes());assert budget['used']==217 and budget['remaining']==83 and budget['current_handle'] is None
for stage in ['c16-expansion-fire-r1','c16-expansion-wood-r1','c16-counter-probe-r1','c16-remaining-r1']:
 tree=E.fromstring((base/stage/'results/cases.trx').read_bytes());counts=next(x.attrib for x in tree.iter() if x.tag.endswith('Counters'));assert counts['passed']=='1' and counts['failed']=='0' and counts['notExecuted']=='0'
extract=json.loads((base/'monster-base-extractor-r1/result.json').read_bytes());assert extract['exit']==0 and extract['profiles']==35 and extract['intents']==58 and extract['new_encounters']==0
out.mkdir(parents=True)
stages=['c16-expansion-build-r1','c16-expansion-build-r2','c16-counter-preflight-r1','c16-remaining-build-r1','c16-expansion-fire-r1','c16-expansion-wood-r1','c16-counter-probe-r1','c16-remaining-r1','monster-base-extractor-r1']
for stage in stages:
 for file in (base/stage).rglob('*'):
  if file.is_file() and 'build' not in file.relative_to(base/stage).parts:
   target=out/stage/file.relative_to(base/stage);target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(file,target)
for name in ['run-c16-expansion-build-r1.py','run-c16-expansion-build-r2.py','run-c16-counter-preflight-r1.py','run-c16-remaining-build-r1.py','run-c16-frozen-roster.py','run-c16-frozen-roster-r2.py',
             'c16-expansion-fire-roster-r1.original.json','c16-expansion-wood-roster-r1.original.json','c16-counter-probe-roster-r1.original.json','c16-remaining-roster-r1.original.json',
             'c16-expansion-fire-control-r1.json','c16-expansion-wood-control-r1.json','c16-counter-probe-control-r1.json','c16-remaining-control-r1.json','c16-expansion-preflight-reuse.derived.json',
             'inspect-c16-expansion-r1.py','c16-expansion-inspection-r1.derived.json','extract-monster-base-r1.py','season-monster-tuning-proposal-r1.json','record-c16-expansion-progress-r1.py']:
 shutil.copyfile(base/name,out/name)
result=dict(status='three_archetype_and_five_theme_observations_recorded_not_accepted',completed_items=24,total_items=35,current_new_encounters=78,current_outcomes={'Win':78},
            current_casts=8406,resource_change_events=192,independent_resource_conservation=True,legal_health_verified=True,total_C16_used=217,C16_remaining=83,
            current_dataset_including_prior18=96,three_archetypes_verified_in_Fire_Wood=True,other_three_themes_direct_engine_only=True,
            offensive_counter_variant_is_not_a_fourth_archetype=True,paired_counter_decks_and_initial_monsters_equal=True,
            single_seed_only=True,C16_complete=False,D03_complete=False,ordinary_monster_values_still_fixed_in_factory=True,
            frozen_base_profiles=35,frozen_base_intents=58,base_extraction_encounters=0,workbook_modified=False,numeric_calibration_proposal_unimplemented=True,
            original_binary_directories=[str(base/stage/'build') for stage in stages[:4]],local_reserve_GiB=2,startup_GiB=1,
            B05_new_attempts=0,B05_budget=300,capacity100_retest=False,C15_UI_retest=False,cloud_modified=False,production_restarted=False,whole_goal_complete=False)
(out/'result.json').write_text(json.dumps(result,indent=2)+'\n')
m={'files':{f.relative_to(out).as_posix():hashlib.sha256(f.read_bytes()).hexdigest() for f in out.rglob('*') if f.is_file()}};(out/'manifest.json').write_text(json.dumps(m,indent=2)+'\n')
report=p/'C16-EXPANSION-PROGRESS.md';assert not report.exists();report.write_text('''# C16 扩展构筑与五主题对照

整体仍24/35，C16未验收。本轮新增78场均获胜，8406次施法和192条资源变化独立对账通过；累计217/300、余83。与上一批18场合并为96个当前配置下互异样本，旧121场及失败原件完整保留。证据见[evidence/C16-expansion-r1/result.json](evidence/C16-expansion-r1/result.json)，现行预算仍[C16-BUDGET.json](C16-BUDGET.json)。

## 实测范围与实际差异

先补火主题D2/D5三职业三构筑的精英与其他构筑Boss30场，跳过前18中的6个已测直伤Boss。再测木主题D5三职业三构筑精英/Boss18场；火、木三构筑均真实获胜。补齐精英无ThemeProfile时的可见意图路径，仍通过只读PublishedIntentValue及实际PreviewCards选牌，原房间快照必须保持不变。

木主题反打卡组所需金/土增伤在原防御型护甲中均为0。增加12场同卡组、同原始怪物、同种子、同非元素装备属性的进攻型护甲对照，只改变护甲元素及其带来的控制器响应，不把它计成第四种流派。所有对照获胜但差异未消失：法师反打精英火52.9秒/木77.2秒，祭司72.8/111.1，盾81.1/112.2；Boss火93.6/121.7/157.9，木124.1/167.8/178.2。该结果不支持把所有耗时差都归因于循环盾。

最后补土/金/水D5三职业直伤精英/Boss18场，使直伤基准覆盖全部五主题。当前单种子中，精英最长/最短约为法师1.683、祭司1.614、盾1.708；Boss约为1.226、1.153、1.207，未通过约15%目标。土精英实际循环盾为法师560、祭司672、盾784；金为288/480/672，水为320/320/560。全部盾伤纳入实际总量，不误报为伤害不守恒。

本轮同样维持合法20张卡、难度投影、D2/D5一橙四紫+3、无红装、无血量/牌库重置。只读预览不推进实际时钟；成功施法仍至少500ms。独立对账检查伤害、HP/盾新增/移除/剩余及结束生命有效上限，没有把生息上限当异常。打断日志补入了意图索引、前摇、眩晕及阶段前后值，可区分非致死打断；旧未记录这些字段的样本不补造数据。

## 校准前的来源约束

实际新生怪物基础值仍由PveBattleFactory的固定19组和Boss/匣灵分支产生，两个示例Monsters/MonsterIntents表不驱动该工厂。若直接改C#常量，会让旧配置包的后续新格遭遇一起变化。进行数值校准前，需先为新赛季增加从锁定配置包读取的组/成员覆盖值；旧包无该能力时继续使用冻结旧基准，不从当前大厅包猜数。

已用锁定的原Domain程序集，只读导出26种组/匣灵元素条件、35个成员与58条意图；未创建玩家、房间actor、Resolver执行或时钟推进，新增遭遇0。源码/程序集/输出SHA完整保留。四组精英的调参草案见[版本化校准前置](C01-MONSTER-TUNING-PLAN.md)；它尚未写入工作簿、未导出版本15，也未用于任何实测，不能称已实现或已通过。

## 还缺什么

需落实正式工作簿与原编译器中的季赛校准覆盖表及强校验，验证旧14包的怪组和后续移动保持原行为，再用剩余83场做有明确预算的校准后验证。当前跨主题只有单种子，其他三主题的反打/堡垒流派尚未实测，两种子中位数和约15%目标仍未完成。没有把全胜当成整个C16验收，也未擅自放宽时长门槛。

本机仍2GiB保留加1GiB启动、无窗口/BelowNormal单重进程。B05维持300/300封账，云端、100人容量和已验收C15 UI均未修改或重跑，生产未部署/激活/重启。
''',encoding='utf-8')
plan=p/'C01-MONSTER-TUNING-PLAN.md';assert not plan.exists();plan.write_text('''# C01 怪组版本化校准前置

状态：待实现；没有改生产代码、正式数值或工作簿。此项为C16实际盾量/耗时差的校准前置，不撤销原14固定基准下的既有证据。原数据冻结在[evidence/C16-expansion-r1/monster-base-extractor-r1/legacy-base.original.json](evidence/C16-expansion-r1/monster-base-extractor-r1/legacy-base.original.json)，35成员/58意图及原工厂、程序集、输出SHA均可核验。

## 最小实现边界

保留原PveBattleFactory固定基准，禁止直接改它的旧数值。新增可选season-only的SeasonMonsterTuning配置，按原组ID/成员顺序而非仅怪物名定位，因为E1/E6的metal-guard基础HP不同。新覆盖值进入正式FantasyCard_Config.xlsx五行元数据表，使用原ConfigExporter/Protobuf/哈希/版本流程；不另起运行时JSON配置源，不复制整套不可变旧意图表。

初始v1只覆盖E1:1、E3:1、E4:1、E6:1四个有循环盾成员。字段需明确原monster_id、基础HP、初始盾、Shield意图值以及基准/规则标识；组与成员引用、正HP、盾边界、唯一键、已知种类和完整四行在编译和加载时校验。保留意图顺序、元素、伤害、间隔和增幅，只对当前明确校准列覆盖。

调用必须从房间锁定的catalog显式传入；旧14包不存在该表时保持旧固定基准，不能读GameConfigCatalog.Current回填。只在season-v1且实际发布目录启用；未分季旧模式也继续原基准。初始化与移动新格两个实际消费点均要接入，恢复已保存PVE状态不重造。完整旧房进程恢复仍另归F02。

## 数值草案，尚未采用

草案原件：[season-monster-tuning-proposal-r1.json](evidence/C16-expansion-r1/season-monster-tuning-proposal-r1.json)。E1候选HP180/初盾8/循环盾2，E3为172/4/2，E4为168/12/2，E6保持HP160/初盾10、循环盾2。它依据当前单种子有效血量和盾工作量提出，尚未验证，不预设验收。Boss策略、玩家70/80/100、卡牌、本命、概率和费用不在本草案修改范围。

正式修改前先备份并核对工作簿14、客户端/服务端三件套与原包；以新候选版本发布，旧14原件及本轮失败/超目标记录不变。不可用或损坏的新目录必须拒绝，不把缺覆盖误当已完成校准。

## 验证要求

用冻结35成员/58意图做旧基准快照对照，覆盖普通组、双怪与匣灵六元素；旧包各档缩放、新目录四行覆盖、其余成员不变、旧房在新大厅下移动仍取旧包均需证明。数据/工厂快照是静态契约，不冒称已跑真实战斗。之后在C16剩余83场内冻结具体清单，按真实启动数记账；B05不得重开。

表格技能已经开始读取但尚未进行XLSX编辑；真正编辑前需读完该技能、使用工作区依赖加载器和受支持运行时，并在首次编辑前执行规定的操作标记。保留原工作簿值、公式、样式、布局、原生表与校验；只增本项需要的数据，验证导出和旧包兼容。新候选尚未满足这些要求，不能部署。
''',encoding='utf-8')
data=json.loads((p/'PROGRESS.json').read_bytes());assert sum(x['status']=='complete' for x in data['items'])==24
for item in data['items']:
 if item['id']=='C16':
  item['note']+=' 本轮火扩展30、木对照18、同卡组进攻护甲12及余三主题直伤18，共78/78胜，8406施法及192资源变化独立对账；累计217/300余83。火木三流派实测、五主题直伤已覆盖，但单种子精英跨主题比1.614至1.708、Boss1.153至1.226仍未过约15%；其他三主题另两流派和两种子中位数待补。工厂基础值仍固定代码，调参前先落实C01版本化组/成员覆盖；已冻结35成员58意图，0新遭遇。四精英数值仅草案，未改工作簿/运行值，整体24/35。'
  item['evidence']+=['C16-EXPANSION-PROGRESS.md','C01-MONSTER-TUNING-PLAN.md','evidence/C16-expansion-r1/result.json','evidence/C16-expansion-r1/c16-expansion-inspection-r1.derived.json']
 if item['id']=='C01':
  item['note']=item.get('note','')+' C16校准核对确认PveBattleFactory基础怪组未由锁定表读取；在改参数前，需可选季赛组/成员覆盖表与编译/加载强校验，旧14固定基准保持。35成员58意图已从原程序集冻结，四精英覆盖值仅待验证草案，未写工作簿/导出候选15。'
  item.setdefault('evidence',[]).append('C01-MONSTER-TUNING-PLAN.md')
(p/'PROGRESS.json').write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
with (p/'README.md').open('a',encoding='utf-8') as f:f.write('\n\n## 当前接续：C16累计217/300，先补版本化校准来源\n\n本轮78场全部胜出、8406施法与192资源变化独立对账，火木三流派及全部五主题直伤基准已记录；约15%时长目标仍未达到，C16不验收，整体24/35。当前预算217/300余83。已从原程序集冻结35成员/58意图，发现改工厂常量会影响旧包后续新格，故先落实正式工作簿中的季赛组/成员覆盖及旧包不漂移验证，再用剩余预算校准。四精英参数仅草案，未改运行值或工作簿。见[C16扩展结果](C16-EXPANSION-PROGRESS.md)与[C01前置](C01-MONSTER-TUNING-PLAN.md)。\n\n本轮所有句柄终态，源/程序集/运行工作簿SHA保持，原件保留。本机2GiB/1GiB启动保留；B05 300/300、容量100人与C15 UI不重跑，云端未改，生产未部署/重启。\n')
theme=p/'C16-THEMES.md';text=theme.read_text('utf-8');text=text.replace(text.splitlines()[2],'状态：进行中，整体24/35。当前累计217/300、余83；火木三流派与五主题直伤已记录，时长目标仍未通过。下一步先补[C01怪组版本化校准](C01-MONSTER-TUNING-PLAN.md)，最新结果见[C16扩展](C16-EXPANSION-PROGRESS.md)。以下历史原件与失败保留，不部署/激活生产或补测100人。',1);theme.write_text(text,encoding='utf-8')
print(json.dumps({'files':len(m['files']),'new_fights':78,'casts_checked':8406,'C16_used':217,'remaining':83,'overall':'24/35','numeric_proposal_not_implemented':True}))
