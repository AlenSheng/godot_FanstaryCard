from pathlib import Path
import gzip,hashlib,json,tarfile,re

repo=Path.cwd();base=Path(__file__).parent;docs=repo/'docs/season-balance-20261102';out=docs/'evidence/D03-cohort-r1';assert not out.exists()
audit=json.loads((base/'d03-cohort-inspection-r1.derived.json').read_bytes());assert audit['new_routes']==9 and audit['outcomes']=={'Dead':5,'Extracted':4} and not audit['D03_complete']
budget=json.loads((docs/'D03-BUDGET.json').read_bytes());assert budget['used']==45 and budget['remaining']==255 and budget['current_handle'] is None
pin=json.loads((base/'d03-cohort-preflight-r1/source-pin.json').read_bytes());assert all(hashlib.sha256((repo/n).read_bytes()).hexdigest()==h for n,h in pin.items())
name='server/tests/FantasyCard.Server.Tests/Config/SeasonClassEfficiencyPilotTests.cs'
with tarfile.open(base/'d03-counter-preflight-r2/source-snapshot.original.tar.gz') as t:old=t.extractfile(name).read().decode('utf-8-sig').replace('\r\n','\n')
current=(repo/name).read_text('utf-8-sig');assert old.replace('private static CombatCardInstance[] Choose','internal static CombatCardInstance[] Choose').replace('private static string[] Deck','internal static string[] Deck')==current
files=[];root=base/'d03-cohort-preflight-r1';files.extend(p for p in root.iterdir() if p.is_file());files.extend(root/n for n in ['results/contracts.trx','config/FantasyCard_Config.xlsx']);files.extend(p for p in (base/'d03-cohort-r1').rglob('*') if p.is_file())
for n in ['d03-cohort-r1-roster-r1.original.json','run-d03-cohort-preflight-r1.py','run-d03-cohort-r1.py','inspect-d03-cohort-r1.py','d03-cohort-inspection-r1.derived.json','record-d03-cohort-progress-r1.py']:files.append(base/n)
assert len(files)==len(set(files));out.mkdir(parents=True);source={}
for p in files:
    relative=p.relative_to(base).as_posix();data=p.read_bytes();compressed=p.suffix=='.jsonl' or p.suffix=='.json' and len(data)>200000;archived=relative+('.gz' if compressed else '');target=out/archived;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(gzip.compress(data,mtime=0) if compressed else data)
    assert (gzip.decompress(target.read_bytes()) if compressed else target.read_bytes())==data;source[relative]={'sha256':hashlib.sha256(data).hexdigest(),'bytes':len(data),'archive':archived,'gzip':compressed}
(out/'source-byte-manifest.json').write_text(json.dumps(source,indent=2)+'\n');(out/'controller-reuse.derived.json').write_text(json.dumps(dict(old_controller_code_unchanged_except_test_internal_visibility=True,old_archive=str(base/'d03-counter-preflight-r2/source-snapshot.original.tar.gz'),new_game_rule_changes=False,old_36_not_replayed=True),indent=2)+'\n')
(out/'result.json').write_text(json.dumps(dict(audit,completed_items=28,total_items=35,whole_goal_complete=False,local_reserve_GiB=2,startup_GiB=1,production_or_cloud_modified=False,full_binary_original=str(base/'d03-cohort-preflight-r1/build')),indent=2)+'\n')
manifest={'files':{p.relative_to(out).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in out.rglob('*') if p.is_file()}};(out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
(docs/'D03-COHORT-STREAM-PROGRESS.md').write_text('''# D03 D2入门模拟策略与R1三账输入先导

状态：进行中，**D03仍不验收，整体28/35**。本批9场为4撤离/5死亡，1634次施法、88实际击杀和23条HP/盾资源变化独立核对；累计D03从36到45/300、余255。框架无错误不等于9场通关或经济健康。

## 冻结输入与样本范围

三种明确的模拟策略×三职业，各一次独立D2入门尝试，共9例。都持有五蓝+1初始套、免费20格包/0安全格、无药、背包金币0、无已学配方；五蓝+1是测试开始前已有的明确资本，不是死亡后补送。本批不跨场携带银行或假造重新置办，尚未构成长期轨迹。

novice拥有初始白卡20张、永久卡/武器+2；returning/skilled拥有已解锁成熟counter-tempo卡组、永久+5。D2实际均按+2投影。三组共用真实公开状态控制器，每组对所有职业分别使用1秒/0.7秒/0.5秒决策间隔，不专门放慢某职业。novice优先任意装备，returning按独立策略随机流75%选装备，skilled选新部位的紫以上装备否则碎片；生命不超过基础60%时走真实回血选项。它们是可复现假设，不是人类行为或新账号日1实测。

只复用原已知73179的R1几何：真实出生(0,0)、原Boss(2,3)，沿八个固定原格、四邻不向外，没有改地图/怪物或挑选胜负。该当前15、五蓝+1/卡组/策略/经济目的与旧B05的P5+3资源组合不同，不重开B05队列，也不拿本批替换旧失败。只有一张生成地图、每策略三职业各一例，不能估计泛化撤离率。

原D03控制器仅把测试内Choose/Deck改internal供同测试程序集复用，完整代码除此访问修饰符外逐字节对照一致。新夹具走实际Resolver/100ms时钟、资源约束、500ms门禁及本组决策间隔；保留每格、每次施法、选择和最终原件。没有战中药、HP/牌库重置、免费补本体或跳过真实撤离读条。

## 原始结果与三账事实

novice三职业全部死亡，分别清1/4/6格、约93/468.2/707秒。带出金币/碎片/印记均0，合计丢15个蓝本体及其30片历史强化投入。此结果不支持默认把该入门套送进D2，更不支持强行套70%撤离率。

returning法师/盾职业撤离、祭司死亡：合计带出446金、80片、6橙图章以及7蓝/4紫/2绿本体，损失5蓝本体及10片历史强化投入。skilled祭司/盾职业撤离、法师死亡：带出446金、154片、6橙图章和4紫本体，同样损失5蓝及10片历史投入。每次成功原R1带出223金，碎片40至90；失败不给印记或带出收入。

三组将所有失败时间计入模拟小时分母，不只挑幸存者。扣历史强化损失的条件碎片差额分别为-30、+70、+144；这**不是实际已支付的死亡重建费或长期净收益**，因为本体/槽位/模板不足时不能凭差额空造装备。skilled即使碎片差额大，只有4个紫本体和6章对照5蓝本体损失，能否按真实部位/效果与下一场成本补齐仍要状态化验证，不能据此宣布三账都正。

原件、逐源字节清单与独立核查见[evidence/D03-cohort-r1/result.json](evidence/D03-cohort-r1/result.json)。死亡中的物品进入本局原遗物堆，不描述为已在全世界销毁；个人损失与全局新增/转移/销毁的区分仍另归D04。

## 接续缺口

首套成型P50/P90明确保持空值，本批没有跨次保留银行、配方、稀缺部位、心愿和实际强化/重铸支出的轨迹。不能拿单次会话时长、3个职业或幸存者中位数替代它。下一步需冻结可持续轨迹：装备只能来自真实带出/打造/交易供给，死亡后用现有库存与真实成本重建，缺资本时退D0/D1或裸装过渡，不能重新送五件蓝装；同时跟踪基本可用套和指定部位/元素/效果目标套，未成型轨迹按删失报告。

职业效率约15%仍未通过，不能继承C16的主题时长放宽。D2适配的低风险起步与长尾成型、三账缺口应先从真实策略和资本闭环改进，而不是放宽断言或把未到达目标记录删掉。D03后续预算255场，不重跑已完成B05/C16/D01/D02/36开发场/本9场，新的对照须针对明确新条件。

本批全部真实句柄终态；本机2GiB持续保护、原1GiB启动预算和三点3GiB准入，单重进程无窗口/BelowNormal。未修改正式工作簿、游戏规则、协议、UI、云端或生产，未补100人或已验收正常结算/界面。完整目标继续。
''',encoding='utf-8')
progress=json.loads((docs/'PROGRESS.json').read_bytes());assert sum(x['status']=='complete' for x in progress['items'])==28;item=next(x for x in progress['items'] if x['id']=='D03');assert item['status']=='in_progress'
item['note']+=' 后续新增9次D2入门策略/职业原R1尝试：4撤离5死、1634施法88杀23资源变化独立对账，累计45/300余255。novice白卡2/五蓝1三职业全死且带出0；return/skilled按定义分别2撤1死，实际金币/碎片/印记/本体与历史装备损失分开记录，不以碎片差额当完整净利。仅访问修饰符复用原控制器，无规则/工作簿/云端修改。明确不是跨场银行轨迹，首套P50/P90空值、长期三账及职业15%仍未完成；需真实资本/本体重建与D0/D1低风险回退，不能死亡后补免费套装。'
item['evidence']+=['D03-COHORT-STREAM-PROGRESS.md','evidence/D03-cohort-r1/result.json','evidence/D03-cohort-r1/manifest.json','evidence/D03-cohort-r1/source-byte-manifest.json','evidence/D03-cohort-r1/d03-cohort-inspection-r1.derived.json']
(docs/'PROGRESS.json').write_text(json.dumps(progress,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
with (docs/'README.md').open('a',encoding='utf-8') as f:f.write('\n\n## 当前接续：D03累计45/300，先补资本/本体闭环\n\n新9场D2模拟入门策略R1为4撤5死，全部失败和时长保留；novice三职业均未完成。1634施法/88杀/23资源变化对账通过，真实金币/碎片/印记/本体来源与蓝装历史投入损失分账；不是跨次轨迹，首套P50/P90及长期可持续三账仍未证明，不能死亡后补免费装或只看幸存者。D03继续不验收，整体28/35，余255场，见[策略/三账先导](D03-COHORT-STREAM-PROGRESS.md)。未改生产/工作簿/云端，旧已验矩阵/100人/UI不重跑，完整目标继续。\n')
print(json.dumps({'original_files':len(source),'manifest_files':len(manifest['files']),'D03_used':45,'remaining':255,'D03_accepted':False,'progress':'28/35'}))
