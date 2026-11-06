from pathlib import Path
import gzip,hashlib,json,shutil,xml.etree.ElementTree as ET

repo=Path.cwd();base=Path(__file__).parent;docs=repo/'docs/season-balance-20261102';out=docs/'evidence/D01-boundaries-r1';assert not out.exists()
inspection=json.loads((base/'d01-inspection-growth-groups-effects-boxelements-r2.derived.json').read_bytes());coverage=json.loads((base/'d01-coverage-inspection-r1.derived.json').read_bytes())
assert inspection['encounters']==297 and inspection['outcomes']=={'Win':289,'Dead':8} and not inspection['no_terminal_evidence_for_timeouts'] and coverage['accepted']
budget=json.loads((docs/'D01-BUDGET.json').read_bytes());assert budget['used']==297 and budget['remaining']==3 and budget['current_handle'] is None
pin=json.loads((base/'d01-preflight-r2/source-pin.json').read_bytes());assert all(hashlib.sha256((repo/n).read_bytes()).hexdigest()==h for n,h in pin.items())
stages=['d01-preflight-r1','d01-preflight-r2','d01-growth-r1','d01-groups-r1','d01-effects-r1','d01-boxelements-preflight-r1','d01-boxelements-r1']
for stage in stages[1:]:
    root=base/stage;trx=root/'contracts.trx' if stage=='d01-boxelements-preflight-r1' else root/'results'/('contracts.trx' if 'preflight' in stage else 'cases.trx')
    counters=next(e.attrib for e in ET.fromstring(trx.read_bytes()).iter() if e.tag.endswith('Counters'));assert counters['passed']=='1' and counters['failed']=='0' and counters['notExecuted']=='0'
files=[]
for stage in stages:
    files.extend(p for p in (base/stage).rglob('*') if p.is_file() and 'build' not in p.relative_to(base/stage).parts)
names=['d01-plan-r1.original.json','d01-boxcoverage-addendum.before-timing-r1.json','run-d01-preflight-r1.py','run-d01-preflight-r2.py','run-d01-roster-r1.py','run-d01-roster-r2.py','run-d01-roster-r3.py','run-d01-box-preflight-r1.py','inspect-d01-r1.py','inspect-d01-r2.py','d01-coverage-inspection-r1.derived.json','d01-affix-overflow-inspection-r1.derived.json','record-d01-acceptance-r1.py']
names += ['d01-'+x+'-roster-r1.original.json' for x in ['growth','groups','effects','boxelements']]
names += [p.name for p in base.glob('d01-inspection-*.derived.json')]
files.extend(base/name for name in names);assert len(files)==len(set(files));out.mkdir(parents=True);source={}
for path in files:
    relative=path.relative_to(base).as_posix();data=path.read_bytes();compressed=path.suffix=='.jsonl' or path.suffix=='.json' and len(data)>200000
    archived=relative+('.gz' if compressed else '');target=out/archived;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(gzip.compress(data,mtime=0) if compressed else data)
    assert (gzip.decompress(target.read_bytes()) if compressed else target.read_bytes())==data
    source[relative]={'sha256':hashlib.sha256(data).hexdigest(),'bytes':len(data),'archive':archived,'gzip':compressed}
(out/'source-byte-manifest.json').write_text(json.dumps(source,indent=2)+'\n')
result=dict(status='D01_bounded_domain_combat_matrix_accepted',completed_items=27,total_items=35,encounters=297,outcomes=inspection['outcomes'],casts=inspection['independently_checked_casts'],actual_species_kills=428,resource_changes=529,
    growth_class_difficulty=108,group_difficulty=126,effect_class_health=45,box_element_class=18,original_plan=279,before_timing_added_box_cases=18,D01_used=297,D01_remaining=3,D01_complete=True,D02_complete=False,D03_complete=False,
    functional_thresholds_relaxed=False,death_observations_preserved=8,monster_pool_setup='Reconstructed prior0/5/10/15 cards, not claimed previous route kills; actual428kills add exact base0 species cards into discard.',
    local_reserve_GiB=2,startup_GiB=1,admission_GiB=3,one_hidden_BelowNormal_heavy_process=True,
    B05_used=300,B05_new_encounters=0,C16_used=298,C16_new_encounters=0,capacity100_retest=False,C15_UI_retest=False,production_modified=False,cloud_modified=False,whole_goal_complete=False,
    compile_failure='r1 CA1859 on returning an anonymous result asobject. No timed encounter. r2 writes its concrete serialized output in the runner; no rules weakened.',
    full_binary_originals=[str(base/x/'build') for x in stages[:2]],formal_config='season-v1-config-15',formal_hash='2bc11db4b287055d119aceda45deeeb6fb00c3df524b3acad9887deaa04d9d8a')
(out/'result.json').write_text(json.dumps(result,indent=2)+'\n')
manifest={'files':{p.relative_to(out).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in out.rglob('*') if p.is_file()}};(out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
report='''# D01 真实领域战斗边界矩阵验收

状态：通过本项边界矩阵，整体27/35。正式候选15固定输入下实际执行297场，289胜、8次死亡、0超时；未把Fact成功解释为297胜。D01预算297/300余3，不因通过消耗余量。D02完整路线/PVP/重建、D03职业效率与人群P50/P90仍独立待验，没有按本项豁免。

依据原文第13章“可先选择边界集合，不必机械重复所有无关笛卡尔积”，冻结清单先安排279场，覆盖审计再从21场余量中、在新增计时前登记18场匣灵六变体×三职业。没有重复旧B05/C16队列或把它们改名计入本项。实际新场次均由运行前已flush的attempt原件记账。

## 范围与证据

- 108场：三职业×P0至P5六成长×D0至D5六难度，确定性分布五元素装备偏好及混色、0/5/10/15张怪物卡、100%/60%/25%基础生命开战。P0是已拥有合法诊断卡组的裸装锚，不冒称新号初始卡组或新手人群。
- 126场：21个原怪组×六难度，包括双怪、六精英、Boss与匣灵。再加18场专门覆盖三职业与匣灵None/五元素六意图变体。
- 45场：三职业×三生命边界×五装备效果组合，包含橙加紫的2件激活、3紫生息、三破击、五载壁溢出、载壁/生息、单红RapidDraw的1.8秒地板。红仅用于明确的极限属性边界，不作为D5常规通关必需品。

新夹具只在开战前重建累积怪物卡和生命状态；卡入弃牌、0级，不声称先前已合法移动/击杀5至15格。后续428次实际击杀全部由原房间加入精确物种卡到弃牌，包含双怪实例与匣灵元素覆盖。未启用可选吸收或5张上限，原20张底牌实例在战斗中保持。跨格获取和完整自然路线留D02，未伪造结算或PG证明。

卡牌与专武按min(永久成长,D)作为实际生效输入；防具品质帽与等级分别处理，+3/+5不被错误投影到D。成长防具强化档为0/0/1/2/3/5，D0最高蓝且无效果词条、D1最高紫、D2以上至多一件橙/红；三件套、数量、部位和元素均经当前发布目录准入。没有修改正式表、生产规则、怪物HP/意图或旧包。

独立审计原件验证15,640次成功施法、529条怪物HP/盾变化及428次实际击杀。成功施法至少500ms，预览前后完整房间快照一致，实际推进100ms房间时钟；伤害以初始HP/盾、实际新增/移除及剩余精确守恒。手牌、蓄能、职业基础70/80/100、生息有效上限及护盾35/40/50按实际状态核对，不将合法超基础生命误报。

抗性原始值最高71%，实际仍60%上限；五载壁原始减伤61%/盾加成95%，实际分别按40%/45%帽生效。2破击加3生息在准确激活件数下有效，RapidDraw九个职业/生命组合实际沿1.8秒最低自然间隔。额外属性对账只读已执行日志和发布目录，新增场次0。

原始输入与TRX、逐尝试、逐动作/资源变化、终态、程序集清单和源码快照见[evidence/D01-boundaries-r1/result.json](evidence/D01-boundaries-r1/result.json)。[联合独立审计](evidence/D01-boundaries-r1/d01-inspection-growth-groups-effects-boxelements-r2.derived.json)、[覆盖与死亡明细](evidence/D01-boundaries-r1/d01-coverage-inspection-r1.derived.json)、[效果溢出对账](evidence/D01-boundaries-r1/d01-affix-overflow-inspection-r1.derived.json)分别保留证据边界。JSONL无损gzip，逐源字节和解压SHA核对；完整二进制仍在G:/PR13Evidence/season-balance-20261102-r1。

## 死亡、失败与限制

7次成长组死亡全部为P0/P1在D3至D5，实际职业、生命比例、怪组、秒数和剩余敌人血盾保留。效果组另有1次D5成熟属性边界死亡，同样逐例保留，不能掩盖为全胜或直接推断线上缺陷。它们证明合法死亡及资源边界被执行，不证明这些搭配可稳定刷取；适配难度、职业效率与可持续收益继续交给D03审查全部样本，不能只看胜者。

首次r1编译因CA1859拒绝匿名结果返回object，尚未执行任何新遭遇。r2改为在运行方法中直接写序列化结果，279个输入合法性契约通过；追加18个输入使用相同程序集预检通过，四个实际批次各一次执行、全部完整终态，输入/程序集/工作簿SHA一致。没有放宽功能断言或超时条件。

本机持续2GiB保护、原1GiB启动预算及三点3GiB准入保持；无窗口/BelowNormal、单重进程顺序执行。所有本批句柄已终态。B05仍300/300封账、C16仍298/300，不补100人、不重跑已验收C15或正常结算。云端和其他项目未改，生产未部署/激活/重启。剩余D02至D04、E01/E02、F01至F03共8项，完整目标继续。
'''
(docs/'D01-COMBAT-BOUNDARIES.md').write_text(report,encoding='utf-8')
progress=json.loads((docs/'PROGRESS.json').read_bytes());assert sum(x['status']=='complete' for x in progress['items'])==26
item=next(x for x in progress['items'] if x['id']=='D01');assert item['status']=='pending';item['status']='complete'
item['note']='正式候选15在冻结边界矩阵实际297场：289胜/8死亡/0超时。三职业×六成长×六难度108、21怪组×六难度126、效果×职业×生命45及六匣灵变体×三职业18；后18使用原21余量且计时前登记。15640施法/428实际击杀/529资源变化独立对账，HP盾/抽牌/500ms/只读预览/怪物卡0级精确物种通过。原0/5/10/15累积卡为明确先前状态夹具，不冒称之前完整路线；死亡逐例保留供D03，不把本项等同职业效率或人群通过。累计297/300余3，原CA1859编译0场失败保留，未放宽断言。2GiB/1GiB启动；B05/C16/100人/C15UI不重跑，生产未改。整体27/35。'
item['evidence']=['D01-COMBAT-BOUNDARIES.md','D01-BUDGET.json','evidence/D01-boundaries-r1/result.json','evidence/D01-boundaries-r1/manifest.json','evidence/D01-boundaries-r1/source-byte-manifest.json','evidence/D01-boundaries-r1/d01-inspection-growth-groups-effects-boxelements-r2.derived.json','evidence/D01-boundaries-r1/d01-coverage-inspection-r1.derived.json','evidence/D01-boundaries-r1/d01-affix-overflow-inspection-r1.derived.json']
(docs/'PROGRESS.json').write_text(json.dumps(progress,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
readme=docs/'README.md';text=readme.read_text('utf-8').replace('当前完成A01至A05、B01至B05、C01至C16，共26/35项','当前完成A01至A05、B01至B05、C01至C16及D01，共27/35项',1).replace('接续D01至D04、E01/E02及F01至F03，共9项。','接续D02至D04、E01/E02及F01至F03，共8项。',1)
text+='\n\n## 最新接续：D01真实战斗边界矩阵完成，27/35\n\n候选15实际297场289胜/8死亡/0超时；三职业六成长六难度、全部怪组和匣灵变体、0/5/10/15累积怪物卡、三生命边界及激活/溢出/地板已验证。15640施法、428实际击杀、529资源变化独立对账，原8死亡与编译失败保留。累积卡为明确前置状态夹具，不替代D02完整路线；D03效率/人群仍未通过。详见[D01验收](D01-COMBAT-BOUNDARIES.md)。\n\nD01 297/300余3，B05封账、C16不增加，全部句柄终态。本机2GiB保留加1GiB启动，云端未改，不补100人或重跑已验收UI/正常结算。剩余8项继续，生产未部署或重启。\n'
readme.write_text(text,encoding='utf-8')
print(json.dumps({'evidence_files':len(manifest['files']),'original_source_files':len(source),'completed':'27/35','new_encounters':297,'outcomes':inspection['outcomes']}))
