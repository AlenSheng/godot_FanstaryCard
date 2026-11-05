from pathlib import Path
import gzip,hashlib,json

repo=Path.cwd();base=Path(__file__).parent;docs=repo/'docs/season-balance-20261102';out=docs/'evidence/D03-efficiency-r1';assert not out.exists()
a=json.loads((base/'d03-efficiency-inspection-r1.derived.json').read_bytes());c=json.loads((base/'d03-counter-inspection-r2.derived.json').read_bytes());assert a['new_encounters']==24 and c['new_encounters']==12 and not a['D03_complete'] and not c['D03_complete']
budget=json.loads((docs/'D03-BUDGET.json').read_bytes());assert budget['used']==36 and budget['remaining']==264 and budget['current_handle'] is None
pin=json.loads((base/'d03-counter-preflight-r2/source-pin.json').read_bytes());assert all(hashlib.sha256((repo/n).read_bytes()).hexdigest()==h for n,h in pin.items())
builds=['d03-efficiency-preflight-r1','d03-efficiency-preflight-r2','d03-efficiency-preflight-r3','d03-counter-preflight-r1','d03-counter-preflight-r2'];files=[]
for label in builds:
    root=base/label;files.extend(p for p in root.iterdir() if p.is_file())
    for name in ['results/contracts.trx','config/FantasyCard_Config.xlsx']:
        p=root/name
        if p.exists():files.append(p)
for label in ['d03-efficiency-pilot-r1','d03-counter-pilot-r1']:files.extend(p for p in (base/label).rglob('*') if p.is_file())
names=['d03-existing-evidence-gap-audit-r1.derived.json','d03-efficiency-roster-r1.original.json','d03-counter-roster-r1.original.json','d03-controller-pre-timing-correction-r1.json','d03-public-state-projection.before-timing-r1.json','d03-counter-controller-equivalence-r1.derived.json','run-d03-efficiency-preflight-r1.py','run-d03-efficiency-preflight-r2.py','run-d03-efficiency-preflight-r3.py','run-d03-efficiency-pilot-r1.py','run-d03-counter-preflight-r1.py','run-d03-counter-preflight-r2.py','run-d03-counter-pilot-r1.py','run-d03-counter-pilot-r2.py','inspect-d03-efficiency-r1.py','inspect-d03-counter-r1.py','inspect-d03-counter-r2.py','d03-efficiency-inspection-r1.derived.json','d03-counter-inspection-r1.derived.json','d03-counter-inspection-r2.derived.json','record-d03-efficiency-progress-r1.py'];files.extend(base/n for n in names)
assert len(files)==len(set(files));out.mkdir(parents=True);source={}
for path in files:
    relative=path.relative_to(base).as_posix();data=path.read_bytes();compressed=path.suffix=='.jsonl' or path.suffix=='.json' and len(data)>200000
    archived=relative+('.gz' if compressed else '');target=out/archived;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(gzip.compress(data,mtime=0) if compressed else data)
    assert (gzip.decompress(target.read_bytes()) if compressed else target.read_bytes())==data;source[relative]={'sha256':hashlib.sha256(data).hexdigest(),'bytes':len(data),'archive':archived,'gzip':compressed}
(out/'source-byte-manifest.json').write_text(json.dumps(source,indent=2)+'\n')
result=dict(status='D03_development_progress_original_class_efficiency_not_accepted',completed_items=28,total_items=35,new_encounters=36,outcomes={'Win':35,'Dead':1},casts=a['independently_checked_casts']+c['independently_checked_casts'],resource_events=a['resource_events']+c['resource_events'],D03_used=36,D03_remaining=264,D03_complete=False,targets_relaxed=False,
    initial4comparisons=a['comparisons'],counter2comparisons=c['comparisons'],all_legal_health=True,actual_readonly_forecast_and_preview_invariants=True,not_final_holdouts=True,population_P50_P90_not_measured=True,long_run_three_ledger_sustainability_not_proven=True,
    original_D02_mature_noRed_D5_evidence_retained=True,production_or_workbook_modified=False,cloud_modified=False,B05_C16_D01_D02_new_attempts=0,local_reserve_GiB=2,startup_GiB=1,
    original_failure='D03-DEV-031Priest universal-tempo/counter-offense seed73 died130.5s, boss51HPleft, notclear; kept in outcomes and censoring.',derived_audit_history='Firstcounterderivedscript included failure elapsed in conditional median. Correctedr2excludesdeathfromcleartimes and requires allmatchedWin before efficiency/rangepass; rawlogs untouched.',
    full_binaries_preserved=[str(base/x/'build') for x in builds],whole_goal_complete=False)
(out/'result.json').write_text(json.dumps(result,indent=2)+'\n');manifest={'files':{p.relative_to(out).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in out.rglob('*') if p.is_file()}};(out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
(docs/'D03-EFFICIENCY-PROGRESS.md').write_text('''# D03 职业效率开发先导与未验收缺口

状态：进行中，**D03不验收，整体仍28/35**。累计36/300场、余264：35胜、1死亡，4401次施法与153条HP/盾变化独立对账通过；不是36胜，更不等于职业效率或人群/经济通过。正式配置仍15，未改生产数值、工作簿、职业本命、UI、协议或云端。

## 先用已有证据识别缺口

当前D02三职业相同短路线在D0至D5单种子中，最大/最小耗时比分别约1.329、1.366、1.394、1.366、1.356、1.486，原约15%目标均未满足。它们是已有成熟诊断卡组、原4/5格短路径与全部存活样本，不是新手初始卡组、条件八格R1或人群分布；不能由此算首套P50/P90或长期三账。D5卡/武器5、橙紫装+3无红可撤离的三职业证据已存在，不重复刷该矩阵。实际PG66片/五本体重建证明费用，不证明收入可持续。

旧选择器给显式加速估值，但未计PVE阻断转临时双倍抽牌的收益；祭司PRI09因此可能被低估。本轮只改测试控制器：按公开手牌和当前敌人状态枚举可能的首个合资格核，隔离副本调用真实UpdateFenxian/ApplyDrawSpeed/ApplyDrawBlockSpeed，12秒有限未来进手只是决策近似；前3候选调用真实只读预览，不看实际牌库顺序或私有RNG、不故意等待/放慢法师。真实施法仍经原Resolver/100ms时钟/500ms门禁。

计时前核对了真实接口的两处语义：draft阻断已经乘职业控制，转换估计应按原牌面一半再ResolveControl一次，不能重复乘；速度覆盖条件为更长或更强，直接在隔离副本调用原接口。另把副本牌库/RNG换为自有已知副本，仅复制公开计数器。三个输入/数学预检原件保留，均没有计时场次；不是三轮实战通过。

## 实际两组开发结果

首24场：三职业×GO03/GO04×两破击三生息/五破击×种子73/137，全部获胜。所有装备+3、一橙四紫、无红，最初火3金2配装固定。四组职业中位耗时比约1.502、1.406、1.553、1.510，原15%均未达到。最快共同方案GO04+五破击的法/祭/盾中位时长111.9/149.4/168.95秒，亦未使三职业都进入Boss75至120秒目标。

再12场：仅扩展声明的合法卡组及水3火2反向元素五破击配装，实际Run/Choose/FutureDraws文本与首组相同，未换模拟规则。保留职业紫/橙关键牌的counter-tempo六场全胜，法/祭/盾中位76.1/97.65/117.6秒，三者进入Boss目标区间；但比值1.545，职业15%仍未通过。该结果支持配套构筑能解决部分清格时长，不支持把差异说成硬件造成。

不保留职业关键牌的universal-tempo为5胜1死亡。D03-DEV-031祭司在130.5秒死亡，Boss尚余51HP；失败不算清格。仅胜例的法/祭/盾条件中位为99.2/128.9/135.55秒，祭司只有一个胜样本，必须同时报告删失/死亡，不能拿它与双胜样本当完整成功匹配。所有比较均为用于选开发候选的两个种子，不是独立留出检验或人群中位数。

独立审计见[首24](evidence/D03-efficiency-r1/d03-efficiency-inspection-r1.derived.json)及[后12修正统计](evidence/D03-efficiency-r1/d03-counter-inspection-r2.derived.json)。后12首版派生脚本曾混入死亡耗时，原脚本/结果保留；r2明确排除死亡于清格中位、并要求全部匹配场胜利才能判效率/范围通过。原逐施法、资源、结果不改，没有为统计修正重跑。

后12第一次预检因CA1861常量数组未缓存而编译失败，0新场；移到static readonly后合法性通过再实际执行12。没有降低功能断言、重置预算、改怪物、战中用药、回满血或重置实战牌库。全部HP按70/80/100与当前生息上限核对，未误报合法超基础生命。

## 下一实际缺口

职业耗时与同档带出收益约15%仍失败；需要进一步核对职业配套构筑与本命/牌面收益，而不是刻意放慢最快职业。若要改平衡，只在明确版本/原包隔离及同步说明下实施；当前没有更改数值，也没有将C16主题25%放宽用于D03。

还需独立留出种子、普通/双怪/精英对应成长清格目标和真实路线验证；首套成型需先冻结新手/回归/熟练模拟人群的起始卡/装备/模板/备用库存、选择策略、死亡与删失规则，再在剩余预算内用真实领域输出和实际费用建立联合首套P50/P90及碎片/本体印记/金币三账。真人体验按用户范围排除，模拟分布不得写成人类实测。D2/更高档撤离率和局时不能套固定70%/18分钟，不能只看胜者、给死亡后补免费本体或把短路线当R1。

所有原始失败、旧预算和对照完整保留，证据[结果](evidence/D03-efficiency-r1/result.json)与逐源字节清单可核验，完整二进制仍在G:/PR13Evidence/season-balance-20261102-r1。全部本批句柄真实终态；本机持续2GiB、1GiB启动、三点3GiB准入，单重进程隐藏/BelowNormal。B05/C16/D01/D02、100人容量和已验收UI/原正常结算均未重跑；生产未部署、激活或重启，完整目标继续。
''',encoding='utf-8')
progress=json.loads((docs/'PROGRESS.json').read_bytes());assert sum(x['status']=='complete' for x in progress['items'])==28
item=next(x for x in progress['items'] if x['id']=='D03');assert item['status']=='pending';item['status']='in_progress';item['note']='现有D02单种子同路线职业比1.329至1.486均未达原15%，不当人群/R1/长期经济证据。新开发24+12共36场：35胜1死亡，4401施法/153资源变化独立核对；真实克隆本命/速度API、公开状态估值、3次只读预览、实际Resolver/时钟，未改游戏规则。counter-tempo水3火2五破击+3的Boss法/祭/盾中位76.1/97.65/117.6秒，进入75-120但职业比1.545仍失败。universal祭司130.5秒死亡且Boss余51HP，删失保留；派生r1误混失败耗时后r2修正，不重跑/改原件。候选仅开发种子，未留出验收。D03仍不通过，需职业效率/收益、对应成长清格、模拟人群首套P50/P90与可持续三账；不继承C16主题时长放宽。累计36/300余264；CA1861编译0场失败与全部旧证据保留。本机2GiB+1GiB启动，旧矩阵/容量/UI不重跑，生产/云端不改，整体仍28/35。'
item['evidence']=['D03-EFFICIENCY-PROGRESS.md','D03-BUDGET.json','evidence/D03-efficiency-r1/result.json','evidence/D03-efficiency-r1/manifest.json','evidence/D03-efficiency-r1/source-byte-manifest.json','evidence/D03-efficiency-r1/d03-existing-evidence-gap-audit-r1.derived.json','evidence/D03-efficiency-r1/d03-efficiency-inspection-r1.derived.json','evidence/D03-efficiency-r1/d03-counter-inspection-r2.derived.json']
(docs/'PROGRESS.json').write_text(json.dumps(progress,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
with (docs/'README.md').open('a',encoding='utf-8') as f:f.write('\n\n## 当前接续：D03开发36场，效率未验收，仍28/35\n\n新控制器按真实本命/双层抽牌速度及公开状态决策，24+12开发场35胜1死亡，4401施法/153资源变化独立对账。反向元素职业配套方案把D5 Boss中位压到76.1/97.65/117.6秒，但职业比1.545未达约15%，D03不验收；死亡及统计删失、原CA1861/派生修正全部保留。余264/300，尚需独立留出、对应成长清格及模拟人群/三账，见[D03进展](D03-EFFICIENCY-PROGRESS.md)。未改生产数值、工作簿或云端，不重跑旧矩阵/100人/UI；完整目标继续，发布与重启仍待F03。\n')
print(json.dumps(dict(evidence_manifest_files=len(manifest['files']),original_files=len(source),D03='not_accepted',used=36,remaining=264,progress='28/35')))
