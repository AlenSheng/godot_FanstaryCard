from pathlib import Path
import datetime, hashlib, json, shutil

b=Path(__file__).parent;repo=Path.cwd();out=b/'d03-final-bounded-review-r1';assert not out.exists();out.mkdir()
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
paths={
 'paired_D2':b/'d03-paired-d2-audit-r1/result.json',
 'paired_budget':repo/'docs/season-balance-20261102/D03-BUDGET.json',
 'cohort_quantiles':b/'d03-existing-quantiles-r1/result.json',
 'D5_matched':b/'d03-approved-matched-audit-r1.derived.json',
 'F01_calendar':repo/'docs/season-balance-20261102/evidence/F01-calendar-final-r1/result.json',
 'phase1_correction':repo/'docs/season-balance-20261102/F01-PHASE1-CRITERION-CORRECTION.md',
 'skill_policy_correction':repo/'docs/season-balance-20261102/F01-SKILLED-POLICY-CORRECTION.md',
 'D0_same_tier':b/'f01-existing-same-tier-efficiency-r2.derived.json'}
assert all(p.is_file() for p in paths.values())
d2=json.loads(paths['paired_D2'].read_bytes());q=json.loads(paths['cohort_quantiles'].read_bytes());budget=json.loads(paths['paired_budget'].read_bytes())
assert d2['extracted']==9 and d2['class_efficiency_passed'] and d2['carried_income_efficiency_passed']
assert d2['class_median_time_ratio']<=1.15 and max(d2['income_per_domain_hour_ratios'].values())<=1.15
assert all(r['time_ratio']<=1.15 for r in d2['paired_seed_results'])
assert budget['used']==budget['maximum']==317 and budget['remaining']==0 and budget['current_handle'] is None
assert q['total_physical_IDs']==549 and q['new_gameplay_starts']==0
result=dict(item='D03',status='AcceptedWithinBoundedSimulationWithDeclaredPacingException',
 authority=dict(original_user_instruction='如果遇见多次周期测试有部分失败整体验收不通过，多次可以放宽限制，并在报告中重点说明',
 latest_class_criterion='保留15%目标',latest_nine_authorization='call_4d670ef99a7b4b1babd43b2d87c7be95',
 interpretation='Use the standing multi-cycle relaxation only for the lower time target of mature D2 farming; never relax class15percent or call original pacing targets passed'),
 class_time_ratio=d2['class_median_time_ratio'],income_per_domain_hour_ratios=d2['income_per_domain_hour_ratios'],
 matched_D2_three_maps_all_within15=True,matched_D5_no_red_evidence_retained=True,
 original_pacing_targets_all_met=False,declared_exception=dict(scope='MatureD2 low-difficulty farming lower-time targets only',
 observed=d2['pacing'],upper_targets_retained=True,class_ratio_limit=1.15,stats_changed=False,reason='Across317historical attempts and repeated calibration, mature D2 is faster, not slower. Keep observed early-tier throughput without inflating enemies just to meet a lower-time target. D5 benchmark and all old deviations remain separately reported.'),
 cohort_scope='Three named trajectories per cohort; historical mixed versions, censored values and raw events retained. Percentiles are descriptive,not population guarantees.',
 economy_scope='Finite original route/account histories plus conditional model; not a guarantee of infinite-horizon profitability. Bank gold is gross,real costs use F01. Cheap/adaptive gear at lower survival rates; learned-template target-kit model needs stated extraction assumptions.',
 first_season_highest_open_recommendation='D2; does not activate a season or rewrite production definitions',
 D03_used=317,D03_maximum=317,F01_used=300,B05_used=330,new_gameplay_starts=0,
 evidence={name:dict(path=str(p),sha256=sha(p)) for name,p in paths.items()},
 all_original_failures_retained=True,no_new_budget_requested=True,production_changed=False,
 limitations=['Humanexperience excluded by user','No100person capacity rerun','PVE-only paired route does not replace F01 real account settlement','Original pacing failures stay failures;exception is explicit','Censored novice/strict-target tails stay unresolved observations,not fabricated events'],
 reviewed_at_utc=datetime.datetime.now(datetime.timezone.utc).isoformat())
(out/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
doc=repo/'docs/season-balance-20261102/D03-FINAL-BOUNDED-ACCEPTANCE.md';assert not doc.exists()
doc.write_text('''# D03 最终有界验收与节奏例外

2026-11-07。D03按用户允许的有限模拟/历史证据/多轮后说明限制放宽范围收口，状态AcceptedWithinBoundedSimulationWithDeclaredPacingException。累计317/317封账，整体34/35，剩F03正式发布与重启。**原清格目标没有全部通过；只放宽成熟D2刷取的时间下界，职业15%保持严格，不改数值、不洗掉失败。**

## 已证明的核心范围

批准的D2三原图×三职业完整路线9/9清8格撤离，中位时间比1.0263158，逐图最多1.1188175，金币/碎片每领域小时比1.0635047，全部≤1.15；准确带出与72场资源工作量闭合。D5对应成熟无红装9场三职业中位75.2/77/76.1、逐种子最多1.13076，其已声明出生夹具及单场低于原75秒记录保留，不扩大为完整多人路线。

原D0同档84场、D01/D02/C16及B05按原范围组成边界矩阵，不用其中不同牌组/不同药剂/独立地图总体统计伪装严格配对。旧D2单种子1.161及所有较差构筑/旧版本失败保持；新配对证据不是修改旧结果。

## 重点：放宽的仅是成熟D2节奏下界

用户原指令允许“多次可以放宽限制，并在报告中重点说明”，后来明确职业目标15%不放宽。本次仅对成熟D2低难刷取的原时间下界使用该授权：普通54场中位11.85秒，精英9场38秒，Boss9场53.7秒，分别有50/9/9场低于25/50/75秒。没有原上界违例。原25–40/50–80/75–120目标仍作为设计基准和未全达标记录，不改成另一组假绿数字。

经历多轮至317场后，接受此处偏快的成熟低难刷取体验，不单为填满时间下界继续膨胀怪血或重开B05/F01；D5后期Boss基准和初始最高D2分开判断。此例外不放宽职业时间/带出15%、怪物资源守恒、合法输入、动作时钟、HP70/80/100及合法生息超帽、资产来源或恢复门禁。

## 首套和三账按证据本身验收

9条资本轨迹每人群仅3条，完整观察字段已报告经验P50/P90；含删失的字段保留null和随访，不只挑成功者。新手20次未观察品质套、部分严格目标未成型，不能称已保证人群P90。原阶段1只要求获得可用绿蓝而非三日五槽，首周支持策略及原熟练账户策略纠正按原报告保留，不倒填旧日历。

549实物ID在库/溢出/回收/丢失集合互斥且完备，碎片收入减实际记录支出闭合；资本银行金币是带出总量。经营费用、实际强化/打造/重铸/购买、死亡和来源回收另由F01真实账户逐场前后及8币流水闭合，不能由银行非负断言替代。原14日191撤离/61死亡与后续首周/策略纠正保留全部结果。

原独立模型是明确条件算术：R1成功40碎片、五模板已学、重建66碎片、假设70%撤离时净8.2/次，碎片平衡约62.264%、本体章约68.966%。低于这些生存率的目标套并非自动可持续，应按原设计降低投入、使用便宜过渡装和重建方案；不把有限正余额外推为所有真人、所有地图、无限期稳态。此为本轮有界模拟评审的限制，未伪造新事件或预算。

初始最高开放仍建议D2，后续难度代码和证据保留，不因本轮范围删除D3–D5。此建议本身不创建/激活新赛季或改生产定义。

原首套长尾、低存活目标套风险、偏快节奏及历史错误均作为上线后遥测重点保留。本轮按用户排除真人体验和允许多轮放宽的范围完成评审，不以“原全部目标全绿”宣传。

## 发布边界

317场原件及原300/308授权、保护包79项声明限制均保留。无新增对局或产品改动，B05330/F01300不追加，不重跑100人/旧正常结算/最终UI。F03仍须准确保护产物的正式分支同步、切换前新备份、旧版本恢复/配置保留、实际部署重启和公网核验；本报告不等于生产已上线。
''',encoding='utf-8')
dest=repo/'docs/season-balance-20261102/evidence/D03-final-bounded-r1';assert not dest.exists();dest.mkdir(parents=True)
for p in [out/'result.json',Path(__file__)]:shutil.copyfile(p,dest/p.name)
(dest/'manifest.json').write_text(json.dumps([dict(path=p.name,sha256=sha(p),bytes=p.stat().st_size) for p in dest.iterdir()],indent=2)+'\n')
p=repo/'docs/season-balance-20261102/PROGRESS.json';shutil.copyfile(p,b/'progress-before-d03-final-r1.original.json');d=json.loads(p.read_bytes());item=next(x for x in d['items'] if x['id']=='D03');assert item['status']=='in_progress';item['status']='complete';item['note']+=' 最终按用户有限模拟/多轮可放宽授权有界验收通过：317封账，配对D2时间/带出及D5无红成熟职业严格15%通过。仅明确放宽成熟D2刷取时间下界，原普通/精英/Boss中位11.85/38/53.7偏快及原目标未全达标保留，不改数值/上界/15%。首套P50/P90按具名小样本及删失报告，549ID/真实F01费用与8币流水闭合、条件模型不伪装无限稳态；长期风险及新手尾部保持上线遥测限制。初始最高建议D2，不自动激活赛季。整体34/35，剩F03。';item['evidence']+=['D03-FINAL-BOUNDED-ACCEPTANCE.md','evidence/D03-final-bounded-r1/result.json'];p.write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
p=repo/'docs/season-balance-20261102/README.md';s=p.read_text('utf-8');s+='''
## 当前接续：D03有界验收收口，34/35

D03累计317封账，严格职业15%由D2完整配对及D5成熟证据通过。只按原用户允许的多轮放宽处理成熟D2偏快时间下界，原目标未全过、首套删失/低生存目标套风险/有限长期证据均保留，不改游戏数值。见[最终有界评审](D03-FINAL-BOUNDED-ACCEPTANCE.md)。初始最高仍建议D2，不自动激活；仅F03正式分支/备份/准确产物部署重启/公网核验未完成。
''';p.write_text(s,encoding='utf-8')
p=repo/'.gitattributes';s=p.read_text('utf-8');line='docs/season-balance-20261102/evidence/D03-final-bounded-r1/** -text -whitespace';assert line not in s;p.write_text(s.rstrip()+'\n'+line+'\n',encoding='utf-8')
p=b/'current-journey-client-continuation-20261105.json';c=json.loads(p.read_bytes());c.update(progress='34/35',remaining_items=['F03'],D03_status=result['status'],D03_complete=True,worktree_clean=False,all_own_test_handles_terminal=True,pending_test_handles=[],updated_at_utc=datetime.datetime.now(datetime.timezone.utc).isoformat());c['D03_final_review']=str(out/'result.json');c['next_independent_action']='Commit D03 bounded acceptance with explicit original-user-authorized pacing lower-bound exception, no class15 relaxation. Then F03: inspect actual active versions/old archive retention and current resources, fresh private backup/isolated current-package restore compatibility before any production action; use prebuilt artifact, no cloudSDK. Formal branch merge/push preserving exclusives, final restart/health. Do not activate a season or guess dates; initial highest recommendationD2 only.';p.write_text(json.dumps(c,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps(dict(D03=result['status'],original_pacing_targets_all_met=False,strict_class15=True,progress='34/35',remaining=['F03'],production_changed=False)))
