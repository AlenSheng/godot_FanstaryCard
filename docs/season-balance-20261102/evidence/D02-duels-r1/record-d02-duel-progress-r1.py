from pathlib import Path
import gzip,hashlib,json,xml.etree.ElementTree as ET

repo=Path.cwd();base=Path(__file__).parent;docs=repo/'docs/season-balance-20261102';out=docs/'evidence/D02-duels-r1';assert not out.exists()
audit=json.loads((base/'d02-duels-inspection-r2.derived.json').read_bytes());assert audit['unique_completed_scenarios']==72 and audit['actual_attempts']==73 and not audit['D02_complete']
budget=json.loads((docs/'D02-BUDGET.json').read_bytes());assert budget['used']==73 and budget['remaining']==227 and budget['current_handle'] is None
pin=json.loads((base/'d02-duel-preflight-r3/source-pin.json').read_bytes());assert all(hashlib.sha256((repo/n).read_bytes()).hexdigest()==h for n,h in pin.items())
files=[];builds=['d02-duel-preflight-r1','d02-duel-preflight-r2','d02-duel-preflight-r3']
for label in builds:
    root=base/label
    files.extend(p for p in root.iterdir() if p.is_file())
    for relative in ['config/FantasyCard_Config.xlsx','results/contracts.trx']:
        path=root/relative
        if path.exists():files.append(path)
for label in ['d02-duels-pilot-r1','d02-duels-expiry-followup-r1','d02-duels-unstarted-r1']:
    files.extend(p for p in (base/label).rglob('*') if p.is_file())
for name in ['d02-duels-roster-r1.original.json','d02-duels-pilot-roster-r1.original.json','d02-duels-remaining-roster-r1.original.json','d02-duels-expiry-followup-roster-r1.original.json','d02-duels-unstarted-roster-r1.original.json','d02-expiry-tick-contract.before-retest-r1.json','run-d02-duel-preflight-r1.py','run-d02-duel-preflight-r2.py','run-d02-duel-preflight-r3.py','run-d02-duel-roster-r1.py','run-d02-duel-roster-r2.py','inspect-d02-duels-r1.py','inspect-d02-duels-r2.py','d02-duels-inspection-r2.derived.json','record-d02-duel-progress-r1.py']:
    files.append(base/name)
assert len(files)==len(set(files));out.mkdir(parents=True);source={}
for path in files:
    relative=path.relative_to(base).as_posix();data=path.read_bytes();compressed=path.suffix=='.jsonl' or path.suffix=='.json' and len(data)>200000
    archived=relative+('.gz' if compressed else '');target=out/archived;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(gzip.compress(data,mtime=0) if compressed else data)
    assert (gzip.decompress(target.read_bytes()) if compressed else target.read_bytes())==data
    source[relative]={'sha256':hashlib.sha256(data).hexdigest(),'bytes':len(data),'archive':archived,'gzip':compressed}
(out/'source-byte-manifest.json').write_text(json.dumps(source,indent=2)+'\n')
result=dict(audit,completed_items=27,total_items=35,whole_goal_complete=False,PVP_subscope_verified=True,
    local_reserve_GiB=2,startup_GiB=1,admission_GiB=3,one_hidden_BelowNormal_process=True,all_handles_terminal=True,
    source_and_binary_pins_unchanged_in_each_run=True,production_modified=False,cloud_modified=False,capacity100_retest=False,C15_UI_retest=False,
    original_compile_failure='preflight r1 CS8602 on nullable WornArmor in test fixture, no new duel. r2 correct explicit known fixture reference; monster snapshot compare uses full serialized structure.',
    original_timed_failure='pilot actual2starts, only001complete;004failed because original frozen state was compared after legal one100ms resumed PVE tick. No production rule change. Same failed case targeted once, original retained.',
    derived_audit_failure='r1 Python fromisoformat did not accept .NET one-digit fractional UTC timestamp; no result written. r2 pads only parsing representation, originals untouched, no new test.',
    scope_limits=['Domain authoritative StartDuel, not automatic matching/WSS or native capacity','Actual immutable fixture inputs, not player winrates/population','Current source specific control-return edge evidence audit and full legal route/extraction/death storage-backed rebuild still pending'],
    full_binaries_preserved=[str(base/x/'build') for x in builds])
(out/'result.json').write_text(json.dumps(result,indent=2)+'\n');manifest={'files':{p.relative_to(out).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in out.rglob('*') if p.is_file()}};(out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
report='''# D02 正式目录PVP与断线恢复子项

状态：PVP恢复子范围已验证，**D02整体未完成，整体仍27/35**。后续还须验证当前版本下的合法自然路线与完整撤离、死亡结算后用真实本体/配方/钱包重建并再次进入游戏，以及其余控制/返牌边界的证据复核。这里没有将局部PVP结果替代完整路线、PostgreSQL、WSS、原生容量或人群效率。

## 实际覆盖与结果

固定候选15正式目录、SeasonContext及合法装备，三职业有序组合9组×D0/D5×恢复互退/到期死亡×断线为先手/后手，共72个互异场景全部有完整成功终态。D0穿蓝装+3无效果，D5一橙四紫+3，卡/专武实际0或5，非机器人、无怪物削弱。权威StartDuel模拟已触发双人战斗，不冒称本批重新实测自动匹配、同格进入或网络往返。

实际施法144次，其中30次正眩晕、7次正抽牌阻断、45次明确即时抽牌。开场各抽3、蓄能清0；后手开场命令被拒绝，存储期限为0.8秒，实际后手出牌不早于该期限。同刻先手重复执行拒绝，接受的动作序列各从1到2，JSON恢复后同ID回放返回原结果且不改变快照。这里只按本批真实单牌及已发生控制/返牌报告，不据此冒称所有多牌连携和完整递减窗口已重验。

36例断线后JSON重建、重新连接并由双方在8秒窗口内请求互退，Combat和PVE与原冻结快照精确一致。另36例在断线14.9秒仍保留冻结工作副本，15秒到期只将断线者标为死亡，幸存者恢复原PVE并在当前tick继续100ms；死者不恢复PVE，五部位装备按原物品ID与属性全部进入原遗物堆。职业70/80/100、生息有效生命与护盾半基础上限在各关键快照独立核对，未把合法生命范围误报。

原件和独立结果见[evidence/D02-duels-r1/result.json](evidence/D02-duels-r1/result.json)与[独立审计](evidence/D02-duels-r1/d02-duels-inspection-r2.derived.json)。源码、TRX、逐尝试、完整关键快照、回放结果和二进制清单保留；JSONL无损gzip并核对解压前原字节SHA。完整编译二进制及未重复入库的共享输入继续保留G:/PR13Evidence/season-balance-20261102-r1，各源SHA可核验。

## 原失败与合法100ms续时

首个编译r1因夹具WornArmor可空引用被CS8602拒绝，零新场次；修正已知夹具的明确引用后r2输入合法性通过。运行先导原计划4例，在实际开始2例后因首个失败停止：001恢复互退成功，004到期死亡后的幸存者蓄能与原冻结值差一个100ms tick。原失败TRX与源快照保留，未补造004终态。

查阅GDD主卷0.2/基础卷2.2与服务器10Hz时钟：存活恢复快照后“未打完的怪接着打”。BattleRoom.Advance先处理断线到期/EndDuelWithDeath，再执行活跃PVE的本tick。因此首次比较在该时点仍要求完全冻结是不正确的夹具预期，不能据此报告恢复丢状态或异常蓄能。

修正仅影响到期分支的严格对照：从开打前的原完整快照恢复一个对照分支，恰好推进一个100ms tick，再精确比较幸存者Combat/PVE；恢复互退分支仍要求原快照精确相等。新增对照快照写入原日志。生产源、规则、阈值与资产路径均未改，213个领域源文件在先导与修正构建之间SHA相同。

只对失败004针对复验一次通过，再运行原72清单中尚未开始的70例全部通过；001沿其未改的恢复互退分支及原完整结果复用。联合72个完成场景，**不是一次72例全绿**。累计2+1+70＝73次实际尝试、余227，不重置场次；旧“其余68例”草稿从未执行，不应重新启动。Python派生审计首版不接受.NET一位小数的ISO时间而未写结果；第二版仅规范解析小数位，原日志不改、没有重跑战斗。

## 接续约束

D02仍进行中，下一步先核对当前控制/返牌的原合同证据，再冻结有恢复点的新自然路线/撤离与死亡重建链路。原B05 Boss交接失败不补造终态、不更名为本项已通过；禁止重开B05全扫描或借D02消耗其预算。完整进程/PG并发恢复仍归F02，D03效率/人群目标不放宽。

本机2GiB持续保留、1GiB启动预算及三点3GiB准入，单重进程无窗口/BelowNormal。全部本批句柄已终态；B05 300、C16 298、D01 297均未增加。不补100人、不重跑已验收UI/正常结算，云端和其他项目未改，生产未部署、激活或重启。完整目标保持进行中。
'''
(docs/'D02-DUEL-RECOVERY-PROGRESS.md').write_text(report,encoding='utf-8')
progress=json.loads((docs/'PROGRESS.json').read_bytes());assert sum(x['status']=='complete' for x in progress['items'])==27
item=next(x for x in progress['items'] if x['id']=='D02');assert item['status']=='pending';item['status']='in_progress'
item['note']='正式候选15 PVP断线恢复子范围联合72场景完成，实际73尝试：9职业有序组合×D0/D5×恢复/到期×断线先/后手；144施法、30正眩晕/7阻断/45即时抽牌。JSON恢复、原PVE、动作回放/序列、15秒死亡及原5件装备遗物身份独立核对。原先导004因到期同tick恢复后合法100ms续时的夹具预期失败，按GDD/Advance顺序改严格一tick对照；原213领域源不变。001复用、004仅复验1、未开始70通过，不称一次全绿；原失败/TRX/源码保留。累计73/300余227。合法自然路线/完整撤离、实际存储死亡重建及其余控制/返牌边界证据仍待，不计D02整体通过；整体仍27/35。本机2GiB+1GiB启动，旧矩阵与云端/生产不改。'
item['evidence']=['D02-DUEL-RECOVERY-PROGRESS.md','D02-BUDGET.json','evidence/D02-duels-r1/result.json','evidence/D02-duels-r1/manifest.json','evidence/D02-duels-r1/source-byte-manifest.json','evidence/D02-duels-r1/d02-duels-inspection-r2.derived.json','evidence/D02-duels-r1/d02-expiry-tick-contract.before-retest-r1.json']
(docs/'PROGRESS.json').write_text(json.dumps(progress,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
with (docs/'README.md').open('a',encoding='utf-8') as f:f.write('\n\n## 当前接续：D02正式目录PVP恢复子项，仍27/35\n\n72个当前季赛PVP场景分批联合完成，144施法，累计73尝试/余227。36恢复互退与36到期死亡的原PVE、JSON、动作回放和死者装备身份独立对账；原先导失败保留，按GDD核对断线到期同tick的合法100ms续时后做严格对照，未改生产或放宽阈值。D02完整路线/撤离与实际存储重建等仍待，见[D02接续](D02-DUEL-RECOVERY-PROGRESS.md)。\n\n本批句柄终态，本机2GiB/1GiB启动；B05/C16/D01不再跑，100人和已验收UI/正常结算不重测。整体目标及其余D/E/F继续，生产未部署/重启。\n')
print(json.dumps({'files':len(manifest['files']),'original_files_verified':len(source),'completed':'27/35','D02_status':'in_progress','attempts':73,'completed_unique_PVP':72,'remaining':227}))
