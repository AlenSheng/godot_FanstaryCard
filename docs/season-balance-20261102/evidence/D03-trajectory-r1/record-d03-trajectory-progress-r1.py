from pathlib import Path
import gzip,hashlib,json

repo=Path.cwd();base=Path(__file__).parent;docs=repo/'docs/season-balance-20261102';out=docs/'evidence/D03-trajectory-r1';assert not out.exists()
a=json.loads((base/'d03-trajectory-inspection-r1.derived.json').read_bytes());s=json.loads((base/'d03-salvage-inspection-r1.derived.json').read_bytes());assert a['new_matches']==9 and s['new_matches']==18 and not s['D03_complete']
budget=json.loads((docs/'D03-BUDGET.json').read_bytes());assert budget['used']==72 and budget['remaining']==228 and budget['current_handle'] is None
pin=json.loads((base/'d03-trajectory-salvage-preflight-r1/source-pin.json').read_bytes());assert all(hashlib.sha256((repo/n).read_bytes()).hexdigest()==h for n,h in pin.items())
builds=['d03-trajectory-preflight-r1','d03-trajectory-preflight-r2','d03-trajectory-preflight-r3','d03-trajectory-salvage-preflight-r1'];files=[]
for label in builds:
    root=base/label;files.extend(p for p in root.iterdir() if p.is_file())
    for n in ['results/contracts.trx','config/FantasyCard_Config.xlsx']:
        p=root/n
        if p.exists():files.append(p)
for label in ['d03-trajectory-r1','d03-trajectory-salvage-r1']:files.extend(p for p in (base/label).rglob('*') if p.is_file())
names=['d03-trajectory-roster-r1.original.json','d03-trajectory-salvage-roster-r1.original.json','run-d03-trajectory-preflight-r1.py','run-d03-trajectory-preflight-r2.py','run-d03-trajectory-preflight-r3.py','run-d03-trajectory-r1.py','run-d03-trajectory-r2.py','run-d03-trajectory-salvage-preflight-r1.py','run-d03-trajectory-salvage-r1.py','inspect-d03-trajectory-r1.py','inspect-d03-salvage-r1.py','d03-trajectory-inspection-r1.derived.json','d03-salvage-inspection-r1.derived.json','record-d03-trajectory-progress-r1.py'];files.extend(base/n for n in names);assert len(files)==len(set(files));out.mkdir(parents=True);source={}
for p in files:
    relative=p.relative_to(base).as_posix();data=p.read_bytes();compressed=p.suffix=='.jsonl' or p.suffix=='.json' and len(data)>200000;archived=relative+('.gz' if compressed else '');target=out/archived;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(gzip.compress(data,mtime=0) if compressed else data)
    assert (gzip.decompress(target.read_bytes()) if compressed else target.read_bytes())==data;source[relative]={'sha256':hashlib.sha256(data).hexdigest(),'bytes':len(data),'archive':archived,'gzip':compressed}
(out/'source-byte-manifest.json').write_text(json.dumps(source,indent=2)+'\n')
result=dict(status='D03_persistent_capital_trajectories_verified_not_accepted',completed_items=28,total_items=35,new_continuation_matches=27,outcomes={'Extracted':18,'Dead':9},original_9_initial_attempts_not_replayed=True,tracks=9,observed_attempts_each_including_original=4,lobby_fragments_paid=44,actual_mark_crafts=2,actual_reward_equips=19,
    nine_first_basic_ready_target_sets_all_right_censored_beyond4=True,novice_all3_zero_capital_after4_deaths=True,D03_used=72,D03_remaining=228,D03_complete=False,original_class15_still_not_passed=True,longrun_sustainable_three_ledgers_not_proven=True,
    bank_model='Test-only persistent state coupled to actual domain outcomes, typed prices/payment/wish and PG66 contract controls; not a new PG population execution.',controls='No-body bank with recipes/funds cannot createequipment; five realbodyGUIDs rebuild+3 exact66; costs validatedpreflight0matches.',
    initialkit_grants_afterdeath=False,no_double_debit_of_historical_loss=True,source_corrections='CA1507 nameof compilefailure0matches retained; alloriginals/versionedsource snapshots kept. Capacity/nonterminal censored checkpoints do not launch anothermatch.',
    local_reserve_GiB=2,startup_GiB=1,production_or_workbook_modified=False,cloud_modified=False,whole_goal_complete=False,full_binary_originals=[str(base/x/'build') for x in builds],profiles=s['profiles'])
(out/'result.json').write_text(json.dumps(result,indent=2)+'\n');manifest={'files':{p.relative_to(out).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in out.rglob('*') if p.is_file()}};(out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
(docs/'D03-PERSISTENT-CAPITAL-PROGRESS.md').write_text('''# D03 跨场银行、回退与删失轨迹

状态：继续未验收，整体28/35。原9次D2先导终态按SHA导入，**没有重跑原9次或补发初始装备**；新增27次实际领域接续为18撤离/9死亡。每条轨迹现包含原初始尝试共4次，D03累计72/300、余228。

## 资本不重置的实现与控制

已撤离四条保留原穿戴/背包物品ID、金币/碎片与实际印记；原五条死亡者导入为空仓库，原遗物ID记为丢失，不能重新穿戴。战斗使用原Resolver/时钟和新生成地图；每次开始前从实际仓库选择合法品质，装备送入本场在途，终态后才决定带回或丢失。银行未投放物品保持，记录每步导入、局前大厅、在途和检查点。

测试银行复用真实SeasonCrafting.Payment/Wish、SeasonEnhancementRules.ArmorCost，登记真实自然/印记实物模板，只有同品质已有本体才能重铸为模板+0并保留GUID，再逐级付费强化。钱包按已带出收入减实际大厅支出核对；历史强化投入随装备丢失单独记账，**不会在死亡时再从钱包扣一次**。金币无药/付费包/市场支出时与真实累计带出相等，印记两币按真实消耗与只在撤离时的收入分别核对，不凭碎片正余额补本体。

零场次控制另验证五个真实本体在已有模板/66片条件下重建到+3，原GUID不变且余额0；有模板和66片但没有本体时仍无装备、余额不变。它们是状态模型控制，不冒称新执行数据库事务；真实PG重建合同已由D02独立保留。本批最早CA1507属性名应使用nameof的编译失败0场，修正后的源码、前后版本和原日志均保留。

## 回退策略与实际结果

第一步9次接续为6撤/3死。原五个死亡者均未补套，其中回归祭司与熟练法师实际裸装D0撤离并取得收入；新手三职业继续死亡。原控制器和状态预测不变，这不是为让最快职业变慢而改时钟。

随后在下一轮运行前登记回收策略：低资本D0只在当前格已实际发现撤离点时提前撤离，不提前读取隐藏点位；低档缺装时保留补位装备，更好的真实奖励通过ClaimReward的合法装备入口换上。银行同时核对穿戴与背包，换下旧件保持ID并只入库一次；死亡则原在途与新获得而丢失的实物均保留丢失身份。仓库满或非终态会留删失检查点并停止该轨迹，不伪造销毁或继续用锁定资产。

新增两步18次为12撤/6死，实际换装19次、消耗蓝图章打造2次，逐笔强化/重铸与印记支付对账。三次新增步骤总计实际大厅碎片支出44；末状态金币、碎片、两种图章、物品及配方逐项留原件。没有把本金或丢失旧投入再当本轮实际支出。

到第4次，新手三职业各4次死亡，均仍零资本/空仓库；回归三职业分别保有835/484/729金与208/117/181片、24/13/19件；熟练为400/749/793金、101/253/219片、5/13/15件。幸存轨迹的正余额不能掩盖新手资本陷阱，也不证明长期可持续。

## 首套与未达门槛

分别记录：五部位至少紫且含一橙的基本品质套；上述全+3且实际效果套激活的可用套；头橙/其余紫、水3火2/两破击三生息全+3的严格目标套。九条到第4次均未形成任何一种，P50/P90保持右删失，下界超过观察到的4次，**不能写成4局成型或从幸存者推断P90**。每种模拟策略只有3职业各一轨迹，当前样本不是人类总体或可泛化分布。

新手默认/借用模板在已验证配置中是C01至C13加7职业白卡；C01至C13均为伤害，默认法师7张职业白卡没有回血。初始实际上有C01至C30等51张已解锁卡，回复/盾/蓄能/加速的C15至C18未进入默认20。这给出下一具体调查：在不赠送资本、修改生命或私自改本命公式的前提下，先验证更可用的初始/借用配套和公开泉水/低风险撤离策略，再继续耗费轨迹预算；当前没有更改已发布模板或工作簿。

职业效率约15%仍失败，尚需独立留出与适配清格目标；首套长尾、负资本和三账也未达验收。不能继承C16的主题25%放宽，不能只放大有钱轨迹继续宣布总体通过。后续需从真实库存检查点继续，不重置银行或重复已运行27次。

证据：[结果与最终银行](evidence/D03-trajectory-r1/result.json)、[首步审计](evidence/D03-trajectory-r1/d03-trajectory-inspection-r1.derived.json)、[回收两步审计](evidence/D03-trajectory-r1/d03-salvage-inspection-r1.derived.json)。原JSONL无损压缩并逐SHA验证，完整二进制在G:/PR13Evidence/season-balance-20261102-r1。全部句柄真实终态；本机持续2GiB/原1GiB启动/三点3GiB，隐藏BelowNormal单重进程。云端、游戏正式源/配置/工作簿/协议/UI未改；B05/C16/D01/D02、100人及已验收UI/原正常结算不重跑。完整目标继续。
''',encoding='utf-8')
progress=json.loads((docs/'PROGRESS.json').read_bytes());assert sum(x['status']=='complete' for x in progress['items'])==28;item=next(x for x in progress['items'] if x['id']=='D03');assert item['status']=='in_progress'
item['note']+=' 已把原9终态接成银行轨迹，新增9+18实际接续为18撤9死，累计72/300余228；不重跑原先导、不重置本金或补装。真实带出/在途/旧件换下/遗物丢失ID保持，模型按真实Payment/Wish/ArmorCost付费并留检查点，零场次66片/缺本体控制通过；首步实际付16片、后两步28片，2次印记打造/19次真实换装，未重复扣旧历史投入。九条到第4次基本/可用/严格套均未形成，P50/P90右删失，新手三职4死仍0资本，不能判可持续。发现默认/借用白20缺C15-C18等基础支持，需验证初始可用配套/低风险策略后再继续，不改生命或本命。原CA1507编译0场失败/全部银行源件保留，游戏/工作簿/云端不改，D03仍不验收，整体28/35。'
item['evidence']+=['D03-PERSISTENT-CAPITAL-PROGRESS.md','evidence/D03-trajectory-r1/result.json','evidence/D03-trajectory-r1/manifest.json','evidence/D03-trajectory-r1/source-byte-manifest.json','evidence/D03-trajectory-r1/d03-trajectory-inspection-r1.derived.json','evidence/D03-trajectory-r1/d03-salvage-inspection-r1.derived.json'];(docs/'PROGRESS.json').write_text(json.dumps(progress,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
with (docs/'README.md').open('a',encoding='utf-8') as f:f.write('\n\n## 当前接续：D03资本接续72/300，首套仍删失\n\n原9终态银行不重置，新增27次为18撤9死，逐步核对真实收入/物品/印记/实际支出，不在死亡时重复扣旧投入，也不补免费装。9轨迹到第4次均未成套，新手三职业仍零资本，D03不验收；下一调查初始/借用支持配套和低风险策略，再从既有检查点继续。原错误/源码/银行原件保留，余228，见[跨场资本进展](D03-PERSISTENT-CAPITAL-PROGRESS.md)。整体28/35；正式规则、工作簿、UI/云端不改，旧矩阵/100人不补，完整目标继续。\n')
print(json.dumps({'original_files':len(source),'manifest_files':len(manifest['files']),'D03_used':72,'remaining':228,'D03_accepted':False,'progress':'28/35'}))
