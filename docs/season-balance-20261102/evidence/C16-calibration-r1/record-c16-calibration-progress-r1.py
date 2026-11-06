from pathlib import Path
import json,hashlib,shutil,xml.etree.ElementTree as E,math

repo=Path.cwd();base=Path(__file__).parent;p=repo/'docs/season-balance-20261102';out=p/'evidence/C16-calibration-r1';assert not out.exists()
analysis=json.loads((base/'c16-calibration-inspection-r2.derived.json').read_bytes());assert analysis['actual_encounters']==18 and analysis['damage_resource_conservation_verified'] and not analysis['C16_complete']
run=json.loads((base/'c16-calibration-pilot-r2/result.json').read_bytes());assert run['exit']==0 and run['new_started_encounters']==18 and run['source_unchanged'] and run['binary_unchanged']
pin=json.loads((base/'c16-calibration-build-r4/source-pin.json').read_bytes());assert all(hashlib.sha256((repo/n).read_bytes()).hexdigest()==h for n,h in pin.items())
tree=E.fromstring((base/'c16-calibration-pilot-r2/results/pilot.trx').read_bytes());counts=next(x.attrib for x in tree.iter() if x.tag.endswith('Counters'));assert counts['passed']=='1' and counts['failed']=='0' and counts['notExecuted']=='0'
budget=json.loads((p/'C16-BUDGET.json').read_bytes());assert budget['used']==139 and budget['remaining']==161 and budget['current_handle'] is None
events=[json.loads(l) for l in (base/'c16-calibration-pilot-r2/observations/monster-resources.original.jsonl').read_text().splitlines()];health=[]
for row in analysis['rows']:
 start=next(e for e in events if e['kind']=='start' and e['difficulty']==row['difficulty'] and e['hero']==row['hero']);original={'Mage':70,'Priest':80,'Guardian':100}[row['hero']];bonus=start['actualEquipment']['VitalityOvercapBonus'];limit=original+math.floor(original*bonus)
 assert 0<row['ending_hp']<=limit;health.append(dict(difficulty=row['difficulty'],hero=row['hero'],base_hp=original,vitality_overcap_bonus=bonus,effective_max_hp=limit,ending_hp=row['ending_hp'],legal=True))
out.mkdir(parents=True)
for stage in ['c16-calibration-preflight-r1','c16-calibration-preflight-r2','c16-calibration-preflight-r3','c16-calibration-build-r4','c16-calibration-pilot-r1','c16-calibration-pilot-r2']:
 root=base/stage
 for f in root.rglob('*'):
  if f.is_file() and 'build' not in f.relative_to(root).parts:
   target=out/stage/f.relative_to(root);target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(f,target)
for name in ['diagnose-c16-baseline-r1.py','c16-baseline-diagnosis-r1.derived.json','run-c16-calibration-preflight-r1.py','run-c16-calibration-preflight-r2.py','run-c16-calibration-preflight-r3.py','run-c16-calibration-build-r4.py',
             'run-c16-calibration-pilot-r1.py','run-c16-calibration-pilot-r2.py','inspect-c16-calibration-r2.py','c16-calibration-inspection-r2.derived.json','c16-preflight-reuse-r3-to-r4.derived.json','record-c16-calibration-progress-r1.py']:
 shutil.copyfile(base/name,out/name)
(out/'legal-health.derived.json').write_text(json.dumps(health,indent=2)+'\n')
(out/'input-plan-label-erratum.derived.json').write_text(json.dumps(dict(field='minimum_observation_seconds_limit',actual_meaning='maximum observation window, 600 virtual seconds',basis='while(room.Elapsed.TotalSeconds<600)',original_plans_preserved=True,no_numeric_or_guard_changes=True),indent=2)+'\n')
result=dict(status='same_formal_theme_six_difficulty_pilot_recorded_not_C16_accepted',completed_items=24,total_items=35,actual_encounters=18,wins=18,casts=1385,read_only_previews=1847,resource_events=50,
            current_theme='Fire',formal_config='season-v1-config-14',seed=73,actual_build='direct-engine',other_two_archetypes_static_preflight_only=True,
            source_unchanged=True,binary_unchanged=True,production_numeric_changes=False,full_original_binary_directory=str(base/'c16-calibration-build-r4/build'),
            original_r5_combat_tables_unchanged=11,new_monster_resources_include_ordinary_shields=True,resource_conservation_verified=True,
            old_preflight_bad_Blue_effect_affixes_retained=True,old_wrong_default_Wood_assertion_retained=True,all_preflight_and_admission_failures_new_encounters=0,
            C16_complete=False,D03_complete=False,current_same_seed_class_ratios=analysis['groups'],budget=budget,local_reserve_GiB=2,startup_GiB=1,
            B05_budget=300,B05_new_attempts=0,capacity100_retest=False,C15_UI_retest=False,cloud_modified=False,production_restarted=False,whole_goal_complete=False)
(out/'result.json').write_text(json.dumps(result,indent=2)+'\n')
m={'files':{f.relative_to(out).as_posix():hashlib.sha256(f.read_bytes()).hexdigest() for f in out.rglob('*') if f.is_file()}}
(out/'manifest.json').write_text(json.dumps(m,indent=2)+'\n')
report=p/'C16-CALIBRATION-PROGRESS.md';assert not report.exists();report.write_text('''# C16 校准接续：先核对输入和资源账

整体仍24/35，C16未通过。当前已实际完成同一正式火主题的六档难度×三职业18场，18胜、1385次实际施法、1847次只读预览，新增18场后累计139/300、余161。证据见[evidence/C16-calibration-r1/result.json](evidence/C16-calibration-r1/result.json)，现行预算为[C16-BUDGET.json](C16-BUDGET.json)。旧121场及失败原件不改。

## 旧记录诊断

复核r5的60场和7610条原动作，发现主题精英比较同时改变怪物种类与基础HP/盾，职业比较同时改变效果套，不能只把耗时差归因于主题或职业本命。旧GeneratedShield仅记ThemeShieldGenerated，普通精英循环盾虽已包含在实际伤害中，却未单列；D5祭司土/金/水精英分别有784/672/640吸收量未被旧基础HP/初始盾/主题盾字段解释。没有把它们写成伤害错误或据此降低怪物血量。

旧r5与当前公开目录的11张相关战斗表逐行一致；本轮没有修改配置数值、怪物、职业生命或本命公式。先完善构筑/行动控制与观测，再判断是否需要新的数值候选。

## 新控制和真实范围

三个候选卡组direct-engine、counter-combo、fortress-control均按五主题三职业静态验证：合法且20张互异，通用/职业橙上限分别遵守，卡组间至少4张集合差异；六档装备均通过实际装备规则。D0蓝+3无效果词缀，D1全紫+3，D2及以上一橙四紫+3。静态验证不计遭遇，也不等于三种流派已经实战通过。

本次只实测direct-engine。永久卡/专武假定+5，实际生效级为难度0至5；D2及以上用含橙的两件破击加三件生息，D0/D1仅合法品质能提供其真实效果，不补造套装。采用自然生成Boss所在格作为独立遭遇起点，明确不声称合法移动路线或完整结算。

行动只使用当前手牌、可见目标/意图和实际只读PreviewCards；没有用后续牌序或未来随机结果。计入实际护盾/治疗余量、印刷返牌、抽牌加速、当前蓄盾/再生意图可打断价值以及生命代价。每次选择前后完整原房间快照必须一致，避免把会消费蓄力状态的ResolveIntentValue当查询；读取当前意图采用只读PublishedIntentValue。所有攻击仍由真实BattleRoom/Resolver与100ms时钟执行，成功施法间隔至少500ms，不重置血量、牌库或怪物。

新增观察器在每个实际施法及tick后核对所有怪物HP/盾，记录正向新增与非伤害移除，包含普通循环盾。独立重读原事件验证18场资源守恒：初始HP/盾加实际再生/加盾，扣除非伤害移除与剩余资源，恰等于实际HP伤害加盾伤。没有用只记主题盾的旧口径替代总量。

## 结果与尚未通过项

18场均胜，但仅单种子、单主题、一个实战流派。D5 Boss法师143.4秒、祭司200.8秒、盾228.9秒；本组最长/最短约1.596。跨主题中位数、至少三类有效构筑和D03的对应人群/清格目标仍无完整证明，不能因18/18获胜就计C16验收。

三职业基础生命仍70/80/100；生息使实际有效上限增加，已按每场真实装备属性检查85、97、122等合法上限及结束生命，没有将其当超血异常。该检查不替代D01的60%/25%入战矩阵。

预检首版给蓝装写了紫装及以上才允许的效果词缀，被现有规则拒绝，0新增遭遇；按GDD纠正后通过。首轮启动把控制目录木主题误当正式默认，但正式14明确为Fire，在首场前断言停止，0新增遭遇；现改为读取真实发布主题，未改正式选择。输入计划minimum_observation_seconds_limit字段名应为最大600秒观察窗，原件保留并单列更正，不改变实际窗口。全部原TRX/日志、零场失败及源码快照保留。

## 后续准入

预算139/300、剩161，每批先冻结具体清单并按真实启动数累加，不重跑旧60或本18整队。接续其余两类构筑与精英控制，扩主题时同时统计基础HP、普通循环盾、主题盾/再生和实际卡组，必要的数值修改须走正式Excel/原编译器、新版本和旧包归档，不能改旧房含义。三种流派、主题约15%目标与D03时长/效率逐项验收，当前均不放宽成已通过。

本机仍2GiB保留加1GiB启动，隐藏/BelowNormal顺序执行；云端未改。B05已300/300封账，没有新增B05、100人容量或C15 UI重跑，生产未部署/激活/重启。
''',encoding='utf-8')
data=json.loads((p/'PROGRESS.json').read_bytes());assert sum(x['status']=='complete' for x in data['items'])==24
for item in data['items']:
 if item['id']=='C16':
  assert item['status']=='in_progress';item['note']+=' 当前实际目录为Fire，完成同图六档×三职业direct-engine18/18胜，1385施法/1847只读预览及全部净HP/盾变化独立对账；累计139/300余161。旧精英盾字段漏列普通循环盾、职业效果套混杂已定位，11战斗表与原r5一致，未改数值。D5 Boss143.4/200.8/228.9秒，仍不通过时长/效率；另两类流派仅静态合法，尚未实战。蓝装非法效果及Wood默认误认均在0场预检/准入阶段拒绝，原件保留；B05已300/300禁止新增。整体24/35，继续其余构筑/主题，不补测100或重启生产。'
  item['evidence']+=['C16-BUDGET.json','C16-CALIBRATION-PROGRESS.md','evidence/C16-calibration-r1/result.json','evidence/C16-calibration-r1/c16-calibration-inspection-r2.derived.json']
(p/'PROGRESS.json').write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
readme=p/'README.md';text=readme.read_text('utf-8');text+='\n\n## 当前接续：C16同图六档18场已记录，整体仍24/35\n\n当前正式Fire主题三职业六档direct-engine18/18胜，1385施法和1847只读预览、所有怪物净HP/盾变化已独立对账；C16累计139/300、余161，现行[C16-BUDGET.json](C16-BUDGET.json)。旧121与失败不改。D5 Boss仍143.4/200.8/228.9秒，另两类流派仅静态合法、跨主题中位数未补齐，C16/D03不计通过。见[C16校准接续](C16-CALIBRATION-PROGRESS.md)。\n\n蓝装非法效果与木主题默认误认均被首场前校验拒绝、0新遭遇，原件保留；默认Fire/正式数值未改。当前无存活测试句柄，编译输入/程序集SHA一致，本机2GiB加1GiB启动保留；B05 300/300不动，云端、100人和C15 UI均未重跑或修改，生产未部署/重启。\n';readme.write_text(text,encoding='utf-8')
theme=p/'C16-THEMES.md';text=theme.read_text('utf-8');old=text.splitlines()[2];text=text.replace(old,'状态：进行中，整体24/35。当前C16累计139/300、余161；正式Fire同图六档18场已记录，尚未通过主题中位时长/三类实战构筑。C15已完成，最新接续见[C16-CALIBRATION-PROGRESS.md](C16-CALIBRATION-PROGRESS.md)。以下为原批次历史快照，原件和失败保留，不部署/激活生产或补测100人。',1);theme.write_text(text,encoding='utf-8')
print(json.dumps({'files':len(m['files']),'new_encounters':18,'C16_used':139,'remaining':161,'C16_complete':False,'overall':'24/35'}))
