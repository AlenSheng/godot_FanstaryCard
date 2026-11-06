from pathlib import Path
import json, hashlib, shutil, xml.etree.ElementTree as E

repo=Path.cwd(); b=Path(__file__).parent
out=repo/'docs/season-balance-20261102/evidence/A03-A04-final-r1'
assert not out.exists()
runtime=b/'runtime-r116'; prior=b/'runtime-r115'; audit=json.loads((runtime/'collection-audit.json').read_bytes())
assert audit['exit_code']==0 and not audit['oom_killed'] and audit['binary_payload_unchanged']
assert audit['counts']['passed']=='5' and audit['counts']['failed']=='0' and audit['counts']['notExecuted']=='0'
assert 'removed_exited_runtime' in (runtime/'cleanup.original.log').read_text('utf-8')
restored=json.loads((b/'isolated-PG-wal-restore-r2.original.json').read_bytes());assert restored['returncode']==0
restored=json.loads(restored['stdout']);assert restored['after']['max_wal_size']=='1GB' and restored['after']['min_wal_size']=='80MB' and restored['durability_settings_unchanged']
pin=json.loads((b/'asset-context-local-r5/source-pin.json').read_bytes())
assert all(hashlib.sha256((repo/n).read_bytes()).hexdigest()==h for n,h in pin.items())
oldpin=json.loads((b/'asset-composite-local-r4/source-pin.json').read_bytes())
changed=[n for n,h in pin.items() if oldpin.get(n)!=h]
assert set(changed)=={'server/tests/FantasyCard.Server.Tests/Config/PublishedConfigTestInputs.cs','server/tests/FantasyCard.Server.Tests/Persistence/PostgresConfigVersionRoomTests.cs'},changed
matrix=json.loads((b/'asset-context-matrix-r1.original.json').read_bytes())
for family in matrix['families']:
 for n,h in family['source_sha256'].items(): assert hashlib.sha256((repo/n).read_bytes()).hexdigest()==h
rows=[json.loads(line) for stage in [runtime,prior] for line in (stage/'public/resource-guard.original.jsonl').read_text('utf-8').splitlines() if line]
assert rows and min(x['available_ram'] for x in rows)>=500*1024**2
assert min(x['free_disk'] for x in rows)>=3*1024**3 and min(x['disk_fraction'] for x in rows)>=.05
counts={};passed=set();failed=set();all_names=set()
for group,expected in [('a',32),('b',40),('c',49)]:
 root=E.fromstring((prior/f'public/results/group-{group}.trx').read_bytes())
 c=next(x.attrib for x in root.iter() if x.tag.endswith('Counters'));assert int(c['total'])==expected and c['notExecuted']=='0';counts[group]=c
 for x in root.iter():
  if x.tag.endswith('UnitTestResult'):
   name=x.attrib['testName'];assert name not in all_names;all_names.add(name)
   (passed if x.attrib['outcome']=='Passed' else failed).add(name)
assert len(passed)==116 and len(failed)==5 and len(all_names)==121
root=E.fromstring((runtime/'public/results/group-a.trx').read_bytes())
retested={x.attrib['testName']:x.attrib['outcome'] for x in root.iter() if x.tag.endswith('UnitTestResult')}
assert set(retested)==failed and set(retested.values())=={'Passed'}
names=sorted(passed|set(retested));assert len(names)==121
local=E.fromstring((b/'asset-composite-local-r4/results/mail-local.trx').read_bytes());c=next(x.attrib for x in local.iter() if x.tag.endswith('Counters'));assert c['passed']=='34' and c['failed']=='0' and c['notExecuted']=='0'
out.mkdir(parents=True)
def copy(source,relative):
 target=out/relative;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source,target)
for stage in ['runtime-r113','runtime-r114','runtime-r115','runtime-r116']:
 source=b/stage
 for p in source.rglob('*'):
  if p.is_file() and ('public' in p.relative_to(source).parts or p.parent==source and p.suffix in ['.json','.log','.py']):
   copy(p,stage+'/'+p.relative_to(source).as_posix())
 # The exact downloaded public archive is retained both locally and in Git.
 copy(source/'public-evidence.tar.gz',stage+'/public-evidence.tar.gz')
for build in ['asset-composite-local-r1','asset-composite-local-r2','asset-composite-local-r3','asset-composite-local-r4','asset-context-local-r5']:
 source=b/build
 if source.exists():
  for p in source.rglob('*'):
   if p.is_file() and 'build' not in p.relative_to(source).parts and p.suffix in ['.json','.log','.trx']:
    copy(p,build+'/'+p.relative_to(source).as_posix())
for name in ['asset-context-matrix-r1.original.json','asset-context-prior-manifest-verification.derived.json',
             'isolated-PG-wal-apply-r1.original.json','isolated-PG-wal-restore-r1.original.json','isolated-PG-wal-apply-r2.original.json','isolated-PG-wal-restore-r2.original.json',
             'control-isolated-PG-wal-budget.py','control-isolated-PG-wal-budget-r2.py',
             'prepare-asset-composite-r115.py','prepare-runtime115-grouped-controls.py','prepare-asset-context-matrix-r1.py',
             'record-asset-context-acceptance-r1.py','collect-runtime113-forensic.py','collect-asset-grouped-r114.py','collect-asset-grouped-r115.py','collect-asset-targeted-r116.py','prepare-runtime116-targeted-controls.py',
             'run-asset-composite-local-r1.py','run-asset-composite-local-r2.py','run-asset-composite-local-r3.py','run-asset-composite-local-r4.py',
             'run-asset-context-local-r5.py','observe-asset-composite-r113.py','observe-asset-composite-r114.py','observe-asset-composite-r115.py','observe-asset-composite-r116.py',
             'setup-asset-runtime115-file-transfer.py','transfer-r115-stream-sftp.py','verify-r115-complete-stream.py','start-r115-from-verified-file.py',
             'setup-asset-runtime116-file-transfer.py','transfer-r116-stream-sftp.py','verify-r116-complete-stream.py','start-r116-from-verified-file.py']:
 copy(b/name,name)
full_inputs={}
for stage in ['runtime-r113','runtime-r114','runtime-r115','runtime-r116']:
 source=b/stage;mf=json.loads((source/'manifest.json').read_bytes())
 full_inputs[stage]=dict(original_directory=str(source),payload_sha256=mf['payload_sha256'],payload_bytes=(source/'payload.tar.gz').stat().st_size)
 assert hashlib.sha256((source/'payload.tar.gz').read_bytes()).hexdigest()==mf['payload_sha256']
local5=E.fromstring((b/'asset-context-local-r5/results/mail-local.trx').read_bytes());c5=next(x.attrib for x in local5.iter() if x.tag.endswith('Counters'));assert c5['failed']=='0' and c5['notExecuted']=='0' and int(c5['passed'])>0
result=dict(status='A03_A04_current_contracts_verified',completed_items=23,total_items=35,
            local_contract_checks=34,current_local_configuration_checks=int(c5['passed']),current_PG_checks=121,prior_r115_original_group_counts=counts,unique_current_test_names=names,
            PG_unique_passed=121,PG_unique_failed=0,PG_unique_skipped=0,
            PG_union_not_one_all_green_run=True,prior_PG_passed_reused=116,latest_targeted_PG_passed=5,latest_targeted_test_names=sorted(retested),
            new_composite_PG_checks=2,product_sources_changed_this_batch=False,current_build_sources_unchanged=True,
            full_original_binary_inputs=full_inputs,matrix_families=9,matrix_source_files=24,
            reused_evidence_roots=23,rechecked_existing_manifest_entries=1493,
            cloud_min_ram=min(x['available_ram'] for x in rows),cloud_min_disk=min(x['free_disk'] for x in rows),cloud_min_disk_fraction=min(x['disk_fraction'] for x in rows),
            local_reserve_GiB=2,local_startup_GiB=1,cloud_reserve_MiB=500,cloud_disk_floor_GiB=3,cloud_disk_floor_fraction=.05,
            runtime_removed=True,private_environment_removed=True,input_tmpfs_unmounted=True,temporary_PG_WAL_restored=restored,
            history=[dict(stage='r113',requested=114,complete_TRX=False,finished_log_entries=87,fail_log_entries=11,exit=143,
                          cause='Current-version room fixtures submitted placeholder hashes; disk guard then stopped the runtime. Original terminal-recording bug left a missing original, explicitly retained.'),
                     dict(stage='r114',executed=32,passed=31,failed=1,later_groups_not_executed=True,
                          cause='New composite fixture used version 0 after ten ownership changes; read actual selection version, with production CAS and assertions unchanged.'),
                     dict(stage='r115',declared=114,executed=121,passed=116,failed=5,skipped=0,
                          cause='Pre-theme numerical fixture removed loot preference but retained dependent theme tables, rejected before room setup. Actual original TRX counts supersede planning estimates, without editing originals.'),
                     dict(stage='r116',executed=5,passed=5,failed=0,skipped=0,
                          cause='Only the five previously failed archive cases rerun using coherent pre-theme controls and actual original hashes/catalogs; other 116 cases reused with production source bytes unchanged.')],
            whole_goal_complete=False,F02_complete=False,E01_complete=False,E02_complete=False,
            production_deployed=False,production_restarted=False,cloud_SDK_started=False,capacity100_retest=False,new_full_routes=0,new_encounters=0,
            B05_total=291,C16_total=121,remaining_items=['B05','C01','C16','D01','D02','D03','D04','E01','E02','F01','F02','F03'])
(out/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
manifest={'files':{p.relative_to(out).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in out.rglob('*') if p.is_file()}}
(out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')
print(json.dumps({'files':len(manifest['files']),'PG_unique':121,'local_prior':34,'local_configuration':int(c5['passed']),'new_composite':2,'prior_failures_retained':True,'candidate_progress':'23/35'}))

report=repo/'docs/season-balance-20261102/A03-A04-ASSET-CONTEXT-ACCEPTANCE.md'
assert not report.exists()
report.write_text('''# A03/A04 当前资产域与原版本上下文验收

A03、A04当前契约验收通过，整体23/35。证据见[evidence/A03-A04-final-r1/result.json](evidence/A03-A04-final-r1/result.json)和[九类来源矩阵](evidence/A03-A04-final-r1/asset-context-matrix-r1.original.json)。本机完整构建及原34项针对检查、随后受影响配置14项均通过；实际PostgreSQL按原testName去重联合121项通过、零跳过。r115三组实际32/40/49共121项，其中116通过/5失败；只对失败的5项定点r116复验通过，原116项按产品源码字节未变复用。该联合结果不描述为一次全绿运行。最初预估32/36/46共114遗漏7个实际用例，现按原TRX更正，原预估与失败均保留。

## 永久资产和选定钱包

卡牌解锁、实际副本与储备、等级、模式、卡组及专武均为账号永久资产；魂、钻石、已领外观与选择不因归档清零。新综合控制以明确声明的等级30已赚经验聚合为输入，实际解锁并逐项领取30级奖励，再实际换季和执行归档页；比对钱包、材料、消耗品、卡牌、储备、模式、专武、卡组、卡组槽、外观与选择的完整JSON。10个外观及已选头像框/卡背/称号全部保留，旧强化装备保持ID和+3归档，新季装备仍在新域。该种子经验不是完整实战路线或真人体验证据。

旧永久金币/碎片与各季钱包分别保留，不相加、不自动兑换。第二综合控制从旧季实际30级领取所得80碎片出发：新季0碎片且旧永久池1000时，新防具强化拒绝；明确选旧季钱包可支付8碎片永久强化法师专武，旧季余72，新季仍0，永久池仍1000，同键重放不重复扣费。+5上限、专武总费用248及C06防具费用均不改。

## 季装、来源和历史字段

季装、金币、碎片、印记、配方、保底、挑战和活动/季程状态沿原季保存。C04至C15现有专项证据与当前综合检查按资产类别关联，23个证据根中已有的1493项清单哈希复核一致。没有根清单的历史报告明确只登记当前文件哈希，不虚构当时原件完整性证明。

装备原GUID、来源季、所在域、生成难度、属性版本和生成凭据沿掉落、打造、强化、死亡遗物、市场、托管、结算及归档传递。历史无副属性保留null/零加成；新铸造校验仍严格。防具+5不受卡牌/专武难度投影帽影响。市场和管理员的账号级移动D0只是流水分类，原物生成难度不重写。

邮件与管理员本就无版本的历史数据继续保留NULL；新记录使用准确来源及原业务请求。邮件原mailId副本聚合、七币实际余额链、装备移动，管理员永久副本、精确三职业魂撤销和逐件新装备GUID已由先前r109至r112专项证据覆盖。本批没有新增生产写入或迁移。

## 消耗品、借用和机器人

药剂/付费背包的账号计数和父级来源凭据保留。原准备冻结数量；实际开局只扣原准备药剂；结算按原托管返回未用药或扣实际消耗背包，重复请求由原唯一凭据保护。综合归档控制确认这些账号行整体未变，不为已有非GUID数量资产另造物品身份。

借用卡/专武和机器人战斗投影不写回永久副本、配方或材料。真实物品经过机器人保管仍保持原ID和来源；自然三选一、配方样本和红装周唯一额度继续由各自已验收规则限制。市场移动不新造红装、不退周配额。

## 原包上下文与归档

准备、匹配分组、开局、房间检查点、恢复、掉落、托管、结算及相关流水保留赛季/难度/规则/配置/属性五维上下文和原配置内容哈希。当前测试覆盖异版目录、不可用或坏原包、上下文更改拒绝、仅隔离坏房、跨季旧房恢复、旧季晚结算和新季配装保护。CurrentConfigVersion在匹配SQL中的用途已按分支核对：旧模式准入与季赛原定义分别判断，季赛不借新大厅目录重解释旧准备。客户端原准备目录、原刷新报价与付款域复用其实际PG、原生互操作和多语言三宽专项证据。

分页归档只移动原季安全物品并原子保存游标/流水，未结算旧房或托管继续等待。满仓旧物仍有原物凭据，不占新季仓位；晚入账只进原季。数据库页中注入故障、重建Repository、HostedWorker以及当前原包恢复属于本项已验证范围。完整操作系统进程崩溃、损坏Launching与运行中故障矩阵继续独立归F02，归档界面及广泛UI继续归E01/E02。

## 必须保留的失败与资源条件

r113请求114项，但没有完整TRX；日志有87个FINISHED与11个FAIL。11个失败在房间夹具发布占位a/b哈希时被既有内容校验拒绝，尚未执行各自目标断言。随后云端可用磁盘3216244736字节低于3GiB，原保护停止容器，退出143。停止后终态记录器因重复state关键字出错，原终态文件缺失；缺失清单、stderr和全部原件保留，不补造“原始”文件。

r114首组32项中31通过/1失败，后两组未执行。新增综合夹具领取10个外观后仍发版本0，被现有选择并发保护拒绝；修正为读取真实所有权/选择版本。五个房间发布占位哈希改为真实Current.ContentHash。r115前两组32/40全过，第三组49项中44通过/5失败，均在旧数值夹具生成包时被主题/寻宝偏好一致性校验拒绝。该夹具原先移除了偏好表，却保留后来新增的依赖主题三表；改为一致的旧配置，三个发布调用也使用各自真实原哈希与目录。受影响配置14项通过；r116仅复验原失败5项，全过且原包不同伤害172/345和背包21/22断言保留。产品校验、业务断言、怪物/职业数值和门槛均未放宽。所有失败、原本机准入拒绝、编译日志与历史程序集继续保留。

按用户最新要求，本机持续保留2GiB，启动预算仍1GiB且需三点达到3GiB；本机重进程顺序、无窗口、BelowNormal。云端RAM500MiB、磁盘3GiB和5%保护不变，当前运行时1200MiB/1CPU/只读输入，不调用SDK。只对自有隔离PG暂设max_wal_size=128MB/min_wal_size=32MB以控制测试WAL占用，fsync/synchronous_commit/full_page_writes均保持on。每轮终态后已恢复原1GB/80MB，原值和恢复证据单列；这不改变保护下限。

各批公共原件已取回并逐成员验SHA后，已退出容器、私有env和64MiB输入tmpfs均已清理。完整原始二进制包仍在G:/PR13Evidence/season-balance-20261102-r1各runtime目录，文件名、大小和SHA在当前result登记；Git保存公共原件、源码快照、输入清单和失败索引。原PG及r109只读基底保留。

## 下一步

剩余B05、C01、C16、D01至D04、E01/E02、F01至F03共12项。B05仍291/300、C16仍121/300；本批新增完整路线和比较遭遇均为0。C15已验收396帧/原生17不重跑，100人不补测。当前配置仍14，UI、协议与正式数值未变，生产未部署/激活/重启。继续从B05剩余合法循环/路线证据与C16平衡缺口推进，最终集成、备份和服务器重启在F03办理。
''',encoding='utf-8')
progress=repo/'docs/season-balance-20261102/PROGRESS.json'; data=json.loads(progress.read_bytes())
assert sum(x['status']=='complete' for x in data['items'])==21
for item in data['items']:
 if item['id'] in ['A03','A04']:
  assert item['status']=='in_progress';item['status']='complete'
  item['note']=item.get('note','')+' 当前综合验收通过：九类来源/24源码审计，本机原34与配置14全过，隔离PG按testName联合121通过（r115原116通过及r116仅复验原5失败，不称一次全绿）。实际30次领取后归档永久账号完整相等，旧季/永久碎片不入新防具而可明确支付永久专武。r113占位哈希/磁盘保护/缺终态原件、r114实际外观版本和r115旧主题夹具失败均保留；原预估114按TRX实际121更正，不改断言。旧专项按原范围复用，23证据根1493项已有清单复核一致；完整进程F02及广泛E01/E02仍独立未完成。临时PG WAL已恢复1GB/80MB，本机2GiB+1GiB启动、云端原保护不变。整体23/35，无新路线/遭遇/100人或生产重启。'
  for name in ['A03-A04-ASSET-CONTEXT-ACCEPTANCE.md','evidence/A03-A04-final-r1/result.json','evidence/A03-A04-final-r1/asset-context-matrix-r1.original.json']:
   if name not in item['evidence']:item['evidence'].append(name)
assert sum(x['status']=='complete' for x in data['items'])==23
progress.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
readme=repo/'docs/season-balance-20261102/README.md';text=readme.read_text('utf-8')
text=text.replace('当前完成A01、A02、A05、B01至B04、C02至C15，共21/35项；','当前完成A01至A05、B01至B04、C02至C15，共23/35项；')
text+='\n\n## 当前接续：A03/A04综合契约验收通过，整体23/35\n\n九类资产/24源码及原包上下文已综合核对，本机原34及配置14全过，实际PG去重联合121通过（r115原116通过加r116定点5，不称一次全绿）。实际30次奖励领取后归档保持所有永久账号行，旧季碎片明确支付永久专武而不入新季防具。23个既有证据根的1493项已有清单哈希一致。r113占位哈希/磁盘保护与缺失终态原件、r114外观版本、r115旧主题夹具失败及114预估/121实际计数全部保留，未放宽业务断言。详见[A03/A04当前验收](A03-A04-ASSET-CONTEXT-ACCEPTANCE.md)。\n\n各批原件验SHA后容器/私有env/tmpfs清理，隔离PG临时WAL已恢复1GB/80MB；本机2GiB保留加1GiB启动和云端500MiB/3GiB/5%保持。B05仍291、C16仍121，未补测100人或重跑C15已验收UI。剩余12项继续，完整F02、广泛E01/E02及最终F03尚未通过，生产未部署/重启。\n'
readme.write_text(text,encoding='utf-8')
context=repo/'docs/season-balance-20261102/A03-A04-CONTEXT-AUDIT.md'
with context.open('a',encoding='utf-8') as f:
 f.write('\n\n## 最新接续：A03/A04当前契约验收通过，整体23/35\n\n九类来源矩阵、24源码、原包上下文与已有专项证据已合并核对；本机34加配置14通过，实际PG去重联合121通过，来源为r115原116通过加r116定点5。新增两项实际PG综合控制覆盖30次真实领取后永久账号完整保留及旧碎片/新防具/永久专武分域。r113的11日志失败/磁盘保护/缺终态原件、r114的31/32外观版本夹具、r115的116/121旧主题夹具失败均原样保留；原114预估按实际121更正。所有清理和临时WAL恢复已完成，见[A03/A04当前验收](A03-A04-ASSET-CONTEXT-ACCEPTANCE.md)。\n\n该结论收口A03/A04合同边界，完整运行中/损坏Launching进程矩阵F02及广泛E01/E02仍独立待办；C01、B05、C16、D/F共12项继续。B05 291/300、C16 121/300未增，2GiB/1GiB启动及云端原保护不变；无100人、UI重跑或生产部署/重启。\n')
print('A03/A04 accepted; progress and continuation updated to 23/35')
