from pathlib import Path
import datetime, gzip, hashlib, json, shutil, xml.etree.ElementTree as ET

repo=Path.cwd(); base=Path(__file__).parent; docs=repo/'docs/season-balance-20261102'
out=docs/'evidence/C16-final-r1'; assert not out.exists()
audit=json.loads((base/'c16-candidate15-final-inspection-r2.derived.json').read_bytes())
assert audit['new_wins']==81 and audit['independently_checked_new_casts']==10115
assert audit['boss_relaxation_applied'] and not audit['original_15_percent_bosses_all_passed']
budget=json.loads((docs/'C16-BUDGET.json').read_bytes())
assert budget['used']==298 and budget['remaining']==2 and budget['current_handle'] is None
pin=json.loads((base/'c16-candidate15-preflight-r2/source-pin.json').read_bytes())
assert all(hashlib.sha256((repo/name).read_bytes()).hexdigest()==h for name,h in pin.items())
stages=['c16-candidate15-preflight-r1','c16-candidate15-preflight-r2','c16-candidate15-elites-r1','c16-candidate15-bosses-r1','c16-candidate15-builds-r1']
for stage in stages[1:]:
    root=base/stage; trx=root/'results'/('contracts.trx' if 'preflight' in stage else 'cases.trx')
    counters=next(e.attrib for e in ET.fromstring(trx.read_bytes()).iter() if e.tag.endswith('Counters'))
    assert counters['passed']=='1' and counters['failed']=='0' and counters['notExecuted']=='0'
files=[]
for stage in stages:
    files.extend(f for f in (base/stage).rglob('*') if f.is_file() and 'build' not in f.relative_to(base/stage).parts)
names=['run-c16-candidate15-preflight-r1.py','run-c16-candidate15-preflight-r2.py','run-c16-frozen-roster-r3.py',
       'c16-candidate15-acceptance-policy.before-timing.json','derive-c16-candidate15-reuse-r1.py',
       'c16-candidate15-reused-observations.derived.json','inspect-c16-candidate15-final-r1.py',
       'inspect-c16-candidate15-final-r2.py','c16-candidate15-final-inspection-r2.derived.json','record-c16-final-r1.py']
for label in ['elites','bosses','builds']:
    names += ['c16-candidate15-'+label+'-control-r1.json','c16-candidate15-'+label+'-roster-r1.original.json']
files.extend(base/name for name in names)
out.mkdir(parents=True); source_manifest={}
for source in files:
    relative=source.relative_to(base).as_posix(); data=source.read_bytes()
    compressed=source.suffix=='.jsonl' or (source.suffix=='.json' and len(data)>200000)
    archived=relative+('.gz' if compressed else '')
    target=out/archived;target.parent.mkdir(parents=True,exist_ok=True)
    target.write_bytes(gzip.compress(data,mtime=0) if compressed else data)
    restored=gzip.decompress(target.read_bytes()) if compressed else target.read_bytes()
    assert restored==data
    source_manifest[relative]={'sha256':hashlib.sha256(data).hexdigest(),'bytes':len(data),'archive':archived,'gzip':compressed}
(out/'source-byte-manifest.json').write_text(json.dumps(source_manifest,indent=2)+'\n')
result=dict(audit,completed_items=26,total_items=35,C16_complete=True,whole_goal_complete=False,
            local_reserve_GiB=2,startup_GiB=1,three_sample_admission_GiB=3,continuous_reserve_GiB=2,
            runtime_mode='one hidden BelowNormal process at a time',cloud_modified=False,
            capacity100_retest=False,C15_UI_retest=False,original_failures_retained=True,
            formal_config='season-v1-config-15',formal_hash='2bc11db4b287055d119aceda45deeeb6fb00c3df524b3acad9887deaa04d9d8a',
            full_binary_originals=[str(base/stage/'build') for stage in stages[:2]],
            immutable_prior_evidence=['../C16-themes','../C16-calibration-r1','../C16-expansion-r1','../C01-monster-tuning-r1'],
            scope='Independent domain encounters and matched-theme timing, not natural routes, population P50/P90, PVP, network capacity or process recovery.')
(out/'result.json').write_text(json.dumps(result,indent=2)+'\n')
manifest={'files':{f.relative_to(out).as_posix():hashlib.sha256(f.read_bytes()).hexdigest() for f in out.rglob('*') if f.is_file()}}
(out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
report='''# C16 最终验收：Boss时长按预登记条件放宽

本项按用户允许重复测试后放宽并重点披露的口径验收，整体26/35。**Boss跨主题中位时长未达到原约15%目标，实际为16.1%至21.8%；采用本轮计时前登记的25%上限通过。** 精英仍按原15%目标通过，没有使用预留20%上限。该放宽仅适用于C16匹配主题时长，不适用于D03职业效率、人群P50/P90或容量。

证据为[evidence/C16-final-r1/result.json](evidence/C16-final-r1/result.json)、[独立对账](evidence/C16-final-r1/c16-candidate15-final-inspection-r2.derived.json)和[计时前验收政策](evidence/C16-final-r1/c16-candidate15-acceptance-policy.before-timing.json)。旧失败与原15%判定全部保留，未将虚拟战斗时间差归因于本地或云端硬件。

## 样本与覆盖

候选15新增81个互异遭遇，81胜：D5直伤精英五主题/三职业/种子73与137共30场；D5直伤Boss第二种子137共15场；土/金/水反打及堡垒、三职业、精英/Boss种子73共36场。三个批次各一次执行，终态均0，输入、程序集、运行工作簿SHA前后一致；没有重开旧队列。

另外复用54个原14及其隔离主题对照的原始观察。复用前以原冻结工作簿重新编译，逐主题核对原完整哈希、卡牌/卡级/数值/难度/季装/主题、同卡组装备及所有六难度Boss与未改E2/E5工厂快照，并核对实际控制器后半段源码。只有依赖等价的Boss与火木原精英可复用；E1/E3/E4/E6已改精英全部使用候选15新场次。原日志保留原版本/哈希，不改写为15。这是81个新样本加54个等价原样本的135样本联合，**不是135场重新执行**。

联合证据中，全部五主题×三职业×直伤/反打/堡垒三流派×精英/Boss的D5种子73覆盖90个实胜案例；正式火主题直伤Boss另覆盖六难度三职业。跨主题时长基准固定为匹配的direct-engine，在两个种子下先求各主题中位数，再算五主题最大/最小比。两种子仅是有界可复现样本，不宣称真实玩家人群统计。

## 时长结果

精英法师/祭司/盾职业的最大与最小中位时长比依次为1.098795、1.093936、1.071747，全部达到原1.15目标。Boss依次1.206355、1.160656、1.218013，三者均未达到原1.15，但均低于预登记1.25。每主题秒数及原判定保留在独立对账JSON，功能与资源守恒条件没有放宽。

81场共10,115次成功施法、355条实际HP/盾资源变化及13,439次只读预览独立对账通过。伤害计入初始HP/盾、再生/增盾、其他损失及剩余值；施法间隔至少500ms，无动作回放，预览快照不变。木Boss再生不超过初始最大HP5%。职业原始70/80/100与生息实际上限按装备计算，未误报合法85等生命。

卡组合法20张、每次至多3张，D0蓝装无效果词条，D1及以上按合法品质帽；D5一橙四紫+3，无红装、战中药、生命/牌库重置。未更改候选15数值、旧版本常量、Boss策略或当前工作簿。这里验证独立遭遇清除，不冒称完整自然路线、正常结算、真人体验、进程恢复或100人容量。

## 原始失败与计数

旧初始卡组25胜/22死亡/13超时、成熟先导、旧单种子精英与Boss超过15%的结果均保留。当前预检r1缺ConfigExporter命名空间而编译失败，零新遭遇；r2补正确引用后1项契约通过。首次派生审计错误地将无seed的动作默认73，混入双种子动作，断言失败且未写结果。r2按唯一连续BattleId组与顺序start/end、原结果、attempt及冻结roster一致匹配，全部81场通过；没有补造seed原字段或重跑战斗。此前派生复用清单的计数/主题键草稿错误发生在结果写入前，最终54条逐原版本哈希核对。

累计原217加新81＝298/300，余2不因通过而补跑；所有历史计数不重置。B05仍300/300封账，禁止再跑。原始JSONL采用无损gzip入库，source-byte-manifest逐文件核对解压SHA，编译二进制全件仍留G:/PR13Evidence/season-balance-20261102-r1并保留manifest及源码快照。

本机保留2GiB，原1GiB启动预算不变，三点均达到3GiB后才启动；运行持续守2GiB、无窗口/BelowNormal、单重进程顺序执行。没有停止其他项目、修改云端或重跑已验收C15 UI/100人容量。全部本批句柄终态，生产未部署/激活/重启。接续D01至D04、E01/E02、F01至F03九项，完整目标保持进行中。
'''
(docs/'C16-FINAL-ACCEPTANCE.md').write_text(report,encoding='utf-8')
progress=json.loads((docs/'PROGRESS.json').read_bytes());assert sum(x['status']=='complete' for x in progress['items'])==25
for item in progress['items']:
    if item['id']=='C16':
        item['status']='complete'
        item['note']+=' 当前最终验收：候选15新增81/81胜，联合54个原依赖等价样本，覆盖五主题三职业三流派精英/Boss；10115施法及355资源变化独立对账。精英双种子跨主题中位比1.072至1.099按原15%通过；Boss1.161至1.218原15%未达标，按计时前登记并获用户原则授权的25%上限放宽验收，报告重点披露。D03职业效率/人群口径未放宽。C16累计298/300余2，B05封账不重跑；2GiB保留加1GiB启动、云端不变，生产未部署。整体26/35，原失败/原始数据/版本哈希保留。'
        item['evidence']+=['C16-FINAL-ACCEPTANCE.md','evidence/C16-final-r1/result.json','evidence/C16-final-r1/manifest.json','evidence/C16-final-r1/source-byte-manifest.json','evidence/C16-final-r1/c16-candidate15-final-inspection-r2.derived.json','evidence/C16-final-r1/c16-candidate15-acceptance-policy.before-timing.json']
(docs/'PROGRESS.json').write_text(json.dumps(progress,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
readme=docs/'README.md';text=readme.read_text('utf-8')
text=text.replace('当前完成A01至A05、B01至B05、C01至C15，共25/35项','当前完成A01至A05、B01至B05、C01至C16，共26/35项',1)
text=text.replace('C16候选12主题机制与330帧多语言界面已验证，战斗平衡仍未验收。','C16主题机制与330帧多语言界面已验证，候选15战斗按预登记的Boss时长25%上限放宽验收；原15%未达标记录保留，见[C16最终验收](C16-FINAL-ACCEPTANCE.md)。',1)
text=text.replace('接续C16平衡、C01冻结及其余D/E/F共11项。','接续D01至D04、E01/E02及F01至F03，共9项。',1)
text=text.replace('C16仍121/300。','C16已298/300余2，依赖等价原样本不计为新场次。',1)
text+='\n\n## 最新接续：C16按预登记时长放宽验收，26/35\n\n候选15新增81场全胜、10115施法与355资源变化独立对账；经原完整版本哈希/配置/工厂/控制器等价核对复用54条旧观察。五主题三职业三流派的精英和Boss覆盖完成。精英原15%目标通过；**Boss实际16.1%至21.8%差异，原15%未达标，按计时前登记25%上限放宽通过**。不豁免D03职业效率或人群统计。详见[C16最终验收](C16-FINAL-ACCEPTANCE.md)。\n\n本机2GiB保留和1GiB启动预算已核对，三点准入3GiB；所有本批句柄终态，C16累计298/300余2、B05封账。历史失败和原始证据不覆盖，不补测100人、不重跑C15界面。剩余D/E/F九项，整体目标继续；未部署、激活或重启生产。\n'
readme.write_text(text,encoding='utf-8')
theme=docs/'C16-THEMES.md';text=theme.read_text('utf-8');lines=text.splitlines();lines[2]='状态：按预登记的Boss时长放宽条件验收，整体26/35，累计298/300余2。精英原15%目标通过，Boss实际16.1%至21.8%未达原15%，按25%上限通过。详见[C16最终验收](C16-FINAL-ACCEPTANCE.md)。以下为各阶段历史，不覆盖原失败或把旧版本原件改称候选15。';theme.write_text('\n'.join(lines)+'\n',encoding='utf-8')
with (docs/'C16-EXPANSION-PROGRESS.md').open('a',encoding='utf-8') as f:
    f.write('\n\n## 后续最终状态\n\n上述217场为历史阶段。C01候选15来源链已完成，后续新增81场全胜并验证原依赖等价样本，C16现298/300余2，按计时前登记的Boss25%上限放宽验收；原15%未达标保留。整体26/35，D03及其余D/E/F不据此豁免，见[C16最终验收](C16-FINAL-ACCEPTANCE.md)。\n')
with (docs/'RESOURCE-POLICY-20261105.md').open('a',encoding='utf-8') as f:
    f.write('\n\n2026-11-06再次核对：client/tests/fixture_runtime.py为2GiB持续保留加1GiB启动，tools/validate_ui_hidden.py的RESERVE=2*GIB、START_BUDGET=GIB；当前C16三个批次均沿用该保护，无需重复降低。外部接续JSON中早期resource_rules字符串已与当前2/1/3GiB字段对齐，原6GiB记录先完整归档保留。\n')
print(json.dumps({'archived_files':len(manifest['files']),'original_files_verified':len(source_manifest),'completed':'26/35','C16':298,'remaining':2,'new_casts':10115,'boss_original15_passed':False,'authorized25_passed':True}))
