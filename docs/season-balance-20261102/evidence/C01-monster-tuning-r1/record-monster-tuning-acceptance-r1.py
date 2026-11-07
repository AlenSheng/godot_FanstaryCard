from pathlib import Path
import json,hashlib,shutil,xml.etree.ElementTree as E

repo=Path.cwd();base=Path(__file__).parent;p=repo/'docs/season-balance-20261102';out=p/'evidence/C01-monster-tuning-r1';assert not out.exists()
def outcomes(path):
 root=E.fromstring(path.read_bytes());return{x.attrib['testName']:x.attrib['outcome'] for x in root.iter() if x.tag.endswith('UnitTestResult')}
server=outcomes(base/'monster-tuning-contract-r4/results/contracts.trx');server.update(outcomes(base/'monster-tuning-contract-r6/results/contracts.trx'));assert len(server)==52 and set(server.values())=={'Passed'}
domain=outcomes(base/'monster-tuning-domain-r1/results/contracts.trx');domain.update(outcomes(base/'monster-tuning-domain-r2/results/published.trx'));assert len(domain)==4 and set(domain.values())=={'Passed'}
native=json.loads((base/'monster-config-native-r1/result.json').read_bytes());assert native['passed_checks']==19 and native['source_unchanged'] and native['original_wrapper_failed_post_check_retained']
source=base/'monster-tuning-workbook-r1/outputs/01a1737c-c1cf-7342-92cd-7cea01eded79';preserve=json.loads((source/'preservation-proof.json').read_bytes());assert preserve['original_sheets_preserved']==38 and preserve['old_formulas_preserved']==8 and preserve['native_tables_preserved']==2
assert hashlib.sha256((repo/'config/FantasyCard_Config.xlsx').read_bytes()).hexdigest()==preserve['after_sha256']
export=json.loads((base/'local-config-r15/result.json').read_bytes());assert export['original_37_table_messages_byte_identical'] and export['all_original_public_tables_equal']
for n in ['fantasycard.config.bytes','fantasycard.config.sha256','fantasycard.config.version.txt']:
 assert (repo/'server/config/generated'/n).read_bytes()==(repo/'client/data/generated'/n).read_bytes()==(base/'local-config-r15/server/config/generated'/n).read_bytes()
assert (repo/'server/config/generated/fantasycard.config.version.txt').read_text().strip()=='season-v1-config-15'
assert hashlib.sha256((repo/'server/config/archive/season-v1-config-14/fantasycard.config.bytes').read_bytes()).hexdigest()=='561fe6c86ed380c7322bbbfde344edbfa3b47c878e247dcb5c4e9ad5c1a2821a'
pin=json.loads((base/'monster-tuning-contract-r6/source-pin.json').read_bytes());assert all(hashlib.sha256((repo/n).read_bytes()).hexdigest()==h for n,h in pin.items())
assert json.loads((p/'C16-BUDGET.json').read_bytes())['used']==217 and json.loads((p/'B05-BUDGET.json').read_bytes())['used']==300
out.mkdir(parents=True)
stages=['monster-tuning-contract-r1','monster-tuning-contract-r2','monster-tuning-contract-r3','monster-tuning-contract-r4','monster-tuning-contract-r6','monster-tuning-refresh-r5','monster-tuning-domain-r1','monster-tuning-domain-r2','monster-config-wire-r1','monster-config-native-r1','monster-tuning-workbook-r1','monster-tuning-source-r1','local-config-r15']
for stage in stages:
 for f in (base/stage).rglob('*'):
  rel=f.relative_to(base/stage)
  if f.is_file() and not any(n in rel.parts for n in ['build','bin','.godot','runtime','node_modules']):
   target=out/stage/rel;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(f,target)
names=['run-monster-tuning-contract-r1.py','run-monster-tuning-contract-r2.py','run-monster-tuning-contract-r3.py','run-monster-tuning-contract-r4.py','run-monster-tuning-contract-r6.py','run-monster-tuning-refresh-r5.py','run-monster-tuning-domain-r1.py','run-monster-tuning-domain-r2.py','run-monster-tuning-workbook-r1.py','verify-monster-tuning-workbook-r1.py','export-monster-tuning-config-r15.py','produce-monster-config-wire-r1.py','run-monster-config-native-r1.py','monster-tuning-server-union.derived.json','record-monster-tuning-acceptance-r1.py']
for name in names:shutil.copyfile(base/name,out/name)
(out/'case-union.derived.json').write_text(json.dumps({'server_cases':server,'domain_cases':domain,'not_one_all_green_run':True},indent=2)+'\n')
result=dict(status='C01_current_candidate15_source_and_publication_contract_verified',completed_items=25,total_items=35,server_unique_passed=52,domain_unique_passed=4,native_checks_passed=19,
            original_failures_retained=True,one_all_green_run_claimed=False,formal_version='season-v1-config-15',content_hash=export['content_hash'],binary_sha256=export['binary_sha256'],workbook_sha256=export['workbook_sha256'],tables=38,rows=1829,public_tables=32,
            old37_table_messages_unchanged=True,old32_public_tables_unchanged=True,old_workbook_values=19107,old_workbook_styles=19989,old_workbook_formulas=8,native_tables_preserved=2,
            old14_exact_archive=True,frozen_legacy_members=35,unlisted_members_unchanged=True,original_catalog_initialization_and_recovered_move_verified=True,unscoped_modes_unchanged=True,
            tuning_member_keys=['E1:1','E3:1','E4:1','E6:1'],tuning_applied_before_difficulty_scaling=True,C16_balance_accepted=False,C16_budget_used=217,C16_remaining=83,C16_timed_encounters_added=0,B05_encounters_added=0,B05_budget_used=300,
            native_fixture_pin_classification_erratum_recorded=True,local_reserve_GiB=2,startup_budget_GiB=1,cloud_modified=False,production_deployed=False,production_restarted=False,whole_goal_complete=False,
            remaining_items=['C16','D01','D02','D03','D04','E01','E02','F01','F02','F03'])
(out/'result.json').write_text(json.dumps(result,indent=2)+'\n');m={'files':{f.relative_to(out).as_posix():hashlib.sha256(f.read_bytes()).hexdigest() for f in out.rglob('*') if f.is_file()}};(out/'manifest.json').write_text(json.dumps(m,indent=2)+'\n')
report=p/'C01-MONSTER-TUNING-IMPLEMENTED.md';assert not report.exists();report.write_text('''# C01 候选15：版本化怪组校准已接入

C01当前配置源与发布契约验收通过，整体25/35。候选15在本地实现分支安装，尚未用于生产；C16数值平衡、D/E/F继续未完成。证据见[evidence/C01-monster-tuning-r1/result.json](evidence/C01-monster-tuning-r1/result.json)。

## 实现与旧包边界

正式工作簿追加SeasonMonsterTuning一张五行元数据表、4行server-only数据。E1/E3/E4/E6按原组与成员顺序定位，避免把同名metal-guard在E1/E6的不同HP混在一起。规则/基准标识、已知组/成员/种类、唯一完整四行、类型/required/scope、正HP、初盾/循环盾范围在原编译器与加载链校验；显式0有效，空值不能代替0。

PveBattleFactory保留全部旧数值原样，新增覆盖在难度缩放之前应用一次，只改指定成员HP、初盾和Shield步骤值，保留伤害、间隔、元素、增幅与意图顺序。未列成员及双怪第二成员不改。BattleRoom初始化和移动新格均显式读取自己锁定的catalog；旧14无表时沿旧基准，未分季模式也不启用，恢复已有PVE状态不重造，不读当前大厅目录回填。固定旧基准35个初始成员/58条初始意图有独立旧程序集原件与黄金快照。

当前候选E1为180/8/2，E3为172/4/2，E4为168/12/2，E6为160/10/2，依次为缩放前HP/初盾/Shield步骤值。这些值已成为本地候选15输入，但尚未通过C16计时/平衡验收，不能把契约通过等同于平衡通过。Boss策略、玩家70/80/100、本命、卡牌、概率与费用不改。

## 工作簿与导出

表格由工作区加载器提供的Artifact Tool编辑，先查看既有样式，首次编辑前仅执行一次规定操作标记；只追加必要工作表。新范围已重新计算、扫描和渲染查看。原38张工作表19107个非公式值、19989处样式、8公式、2个原生表以及宽高/隐藏分组/校验/保护/定义名/计算设置均验证保留。编辑后工作簿SHA83155471d16d294e4a46cab5621078e1e24cf9bfe6f90e9d73fdfb532af54010。

原ConfigExporter导出38表1829行，客户端/服务端三件套相同；新表仅server可见，原37张表消息体逐字节一致、原32张公开表全部值及卡牌描述不变。内容哈希2bc11db4b287055d119aceda45deeeb6fb00c3df524b3acad9887deaa04d9d8a，bytes SHA8180f453067b9a0f5dbffc424476903fb440e7d1bf4b0ff763f284d3b5dbf3d4。内容哈希与文件SHA不同，按各自用途使用。

原14三件套逐字节归档到server/config/archive/season-v1-config-14，原内容哈希f015f18d13ddfa022cb50cc821574481a21976c0d0f21d3f4ae10dcbfaa28e62与bytes SHA561fe6c86ed380c7322bbbfde344edbfa3b47c878e247dcb5c4e9ad5c1a2821a不变。

## 实际验证与保留失败

新旧目录、工厂黄金快照、全部未列成员、显式0/缺值、坏规则/组/成员/元数据、缩放、初始化/恢复后移动及旧模式契约通过；当前15发布包实际加载。服务端按testName联合52项、领域联合4项全过、零跳过，分批来源在case-union记录，不称一次全绿。

两个原始分析器构建失败（CA1859、xUnit2031）保留。r4服务端49/50通过，1项先缺候选12输入；同程序集r5补输入后暴露旧夹具把当前包固定叫14，原失败继续保留。现formal14固定读真实原14，另加formal-current，原14原件与断言不改；只复验受影响刷新和季程发布检查3项通过。领域首次3/4通过，1项缺隔离发布三件套；复制到新隔离目录后同字节只复验该项通过，原目录未修写。

实际C#序列化原14/当前15两份typed配置响应，Godot4.7.2无窗口/headless/BelowNormal导入与消费19项全过：完整哈希、旧公开值、server表隐藏、错误版本/损坏/截断拒绝。它是原生离线互操作，不声称原生公网请求。原封存器把自建project.godot误归为产品源，导致后验比较失败；所有产品文件和自建项目各自前后SHA均一致，派生记录更正分类，未重跑或改写原结果。

本轮不增加C16计时遭遇或B05；C16仍217/300余83、B05已300/300封账。UI代码/可见表未变，不重跑C15已验收画面。当前输入/编译字节与原始失败保留，本机2GiB保留加1GiB启动，云端未改，生产未部署/激活/重启。后续校准仍须在余83场中冻结清单和验收；整体目标尚未完成。
''',encoding='utf-8')
data=json.loads((p/'PROGRESS.json').read_bytes());assert sum(x['status']=='complete' for x in data['items'])==24
for item in data['items']:
 if item['id']=='C01':
  assert item['status']=='in_progress';item['status']='complete';item['note']=item.get('note','')+' 当前候选15源链验收通过：正式工作簿追加4行server-only SeasonMonsterTuning，旧37表消息体/32公开表和38旧工作表完整保留。原14三件套精确归档，按原房catalog初始化/移动，覆盖先于难度缩放，旧/未分季/未列成员不漂移。服务端去重联合52、领域联合4及原生19项通过，所有构建/夹具/封存分类失败保留，不称一次全绿。只完成源/发布契约，C16计时平衡未通过，217/300余83未消耗；整体25/35，未部署/重启生产。'
  item['evidence']+=['C01-MONSTER-TUNING-IMPLEMENTED.md','evidence/C01-monster-tuning-r1/result.json','evidence/C01-monster-tuning-r1/case-union.derived.json']
 if item['id']=='C16':
  item['note']+=' 校准前置已落本地候选15，四个原组/成员覆盖值按原包绑定且旧14保留，C01源链已验收；本轮未跑计时，原217条对照仍属于原14/控制输入，不能当新15平衡结果。剩83场待候选15实际验证，C16状态不变。'
  item['evidence'].append('C01-MONSTER-TUNING-IMPLEMENTED.md')
assert sum(x['status']=='complete' for x in data['items'])==25;(p/'PROGRESS.json').write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
readme=p/'README.md';text=readme.read_text('utf-8').replace('当前完成A01至A05、B01至B05、C02至C15，共24/35项','当前完成A01至A05、B01至B05、C01至C15，共25/35项').replace('当前正式候选14。','当前正式候选15（本地源链通过，未生产发布）。')
text+='\n\n## 当前接续：C01候选15源链通过，整体25/35\n\n正式Excel/原编译器/双端Protobuf/内容哈希链已补齐四组季赛怪物覆盖，旧14与未分季行为保持。服务端联合52、领域联合4、原生19项通过，原始失败和封存分类更正保留。当前候选15共38表1829行，原37表消息体和32公开表保持，详见[C01当前验收](C01-MONSTER-TUNING-IMPLEMENTED.md)。\n\nC16仍217/300余83，尚未用新15做计时验证，不能把旧14结果冒称新15平衡通过。下一步按冻结清单校准；B05不追加、100人和C15 UI不重跑。当前无存活测试负载，本机2GiB/1GiB启动保留，云端与生产未部署/重启，剩10项继续。\n';readme.write_text(text,encoding='utf-8')
plan=p/'C01-MONSTER-TUNING-PLAN.md';text=plan.read_text('utf-8');text=text.replace('状态：待实现；没有改生产代码、正式数值或工作簿。','状态：已按本计划落实本地候选15，源/发布契约通过；计时平衡仍待C16。当前状态见[C01实现与验证](C01-MONSTER-TUNING-IMPLEMENTED.md)。以下为原设计与草案记录。',1);plan.write_text(text,encoding='utf-8')
theme=p/'C16-THEMES.md';text=theme.read_text('utf-8');text=text.replace(text.splitlines()[2],'状态：进行中，整体25/35。当前217/300、余83；C01源链已完成本地候选15，旧14数据及失败保留，新15的计时平衡尚未验证，见[C01实现](C01-MONSTER-TUNING-IMPLEMENTED.md)。不部署/激活生产或补测100人。',1);theme.write_text(text,encoding='utf-8')
with (p/'C01-CONFIG.md').open('a',encoding='utf-8') as f:f.write('\n\n## 候选15源链验收（当前）\n\n原工作簿追加SeasonMonsterTuning4行，38表1829行；原37消息体和32公开表保持，原14三件套精确归档。编译/加载强校验、原目录初始化/恢复后移动、旧模式与未列成员保护、客户端server字段隐藏及版本/哈希拒绝已验证：服务端联合52、领域联合4、原生19全过。见[C01当前验收](C01-MONSTER-TUNING-IMPLEMENTED.md)。C01以当前源链完成，平衡仍归C16/D03；新候选未部署/激活，C16预算217/300余83不变。\n')
with (p/'CONFIG_ARCHIVES.md').open('a',encoding='utf-8') as f:f.write('\n\n## 候选15发布前原14归档\n\nserver/config/archive/season-v1-config-14/保留原bytes/hash/version逐字节副本；原内容哈希f015f18d13ddfa022cb50cc821574481a21976c0d0f21d3f4ae10dcbfaa28e62，文件SHA561fe6c86ed380c7322bbbfde344edbfa3b47c878e247dcb5c4e9ad5c1a2821a。旧14没有SeasonMonsterTuning，仍使用冻结旧工厂基准。候选15按房间原配置显式消费新增覆盖，不回填旧包；原14原生/加载与恢复后新格契约通过。生产归档挂载和重启继续归F03，当前未更改生产运行包。\n')
print(json.dumps({'files':len(m['files']),'server_unique':52,'domain_unique':4,'native':19,'C01_complete':True,'overall':'25/35','C16_budget_unchanged':217}))
