# PR13 全范围实施与分阶段验收细则

日期：2026-09-30。范围：LOAD 44 + A 40 + B 48 = **33个处理包、132个子项、396条检查**。

本轮完成验收规格，不代表运行实现或测试已经通过。原 LOAD/B 运行状态保留，A 队列重新入库，全部细项的 accepted_by 仍为空。规范 Ready 与运行 Accepted 分开记录。

读取的PR head：`1ab3ca85e065cfead1a060cc50ffac384ef90908`；运行代码复核点：`9e0bd404bdeea9df250ba0ccd55bc8f4c98f786b`；release基线：`28c6c7e7d3898e4d2abd186f53361477ba380330`。后续运行在独立 manifest 记录实际集成SHA，不沿用文档提交当作服务器构建。

规范唯一数据源为 [验收细则JSON](PR13_ACCEPTANCE_DETAILS_20260930.json)，本手册由 `python tools/pr13_plan.py --render` 生成。 [LOAD状态](GAMEPLAY_LOAD_EXECUTION_20260929.json)、[A收尾队列](PR13_REMAINING_QUEUE_20260930.json)、[B体验队列](PR13_COMBAT_EXPERIENCE_QUEUE_20260930.json) 均逐子项链接此规格。

A01～A10来自可访问的《读取PR13报告》对话正文，原sandbox附件未取得。本轮保留其10个职责并重新明确四子项，不宣称恢复了原附件的逐字内容。A与LOAD是补充反例/收尾，共用合格case和artifact；B复用现有NUM策略，避免重复编码。

历史云端有界部署/测试授权保留；本次只完善规格和文档校验，不执行新部署、压测、数值启用或合并。后续在既有授权内可继续有界正确性测试；冻结数值正式启用和新增范围必须有对应决策。工作角色仅是计划分工，本次未启动代理。

## 七个可验收阶段

每个子项按S0～S6分别交回状态和证据。依赖只约束所需集成产物，S0/S1测试设计可提前；不能要求整个父任务先Accepted而产生循环。运行层不适用时写理由，由MAIN审核，不默认跳过。

| 阶段 | 进入条件 | 执行与通过条件 | 必备证据 | 失败/阻塞 |
|---|---|---|---|---|
| S0 输入、范围与验收规格冻结 | 读取当前base/head和所有队列；选择适用profile。 | 冻结输入/ownership/规则边界、预期、样本预算、deadline和阈值；解决依赖与字段语义。 通过：本子项必填字段完整、无循环依赖、测试预期可观察；规范校验通过。 | plan hash；profile hash；source/config/image manifest；file ownership | 未知范围/阈值/来源为Blocked，先补合同再运行。 |
| S1 复现或既有行为证明 | S0已冻结，测试接缝和数据可用。 | 正常/边界/故障各用真实入口复现；缺陷记修前失败，已有正确行为留golden，不编造失败。 通过：每测试case有setup/expected/actual；未改代码也须有实测支持。 | repro log；seed/context；before state；case IDs | 不可复现写ReproNotConfirmed并调整假设；不能由静态推导升级线上根因。 |
| S2 实现、兼容与审查 | S1明确问题或NoChange候选评估路径；文件锁已获分配。 | 最小修改、契约先于生成、候选默认保留、资源和异步上下文审查；同文件单写入者。 通过：diff与输入合同一致，默认/新旧版本/回滚边界明确；无收益不强行改。 | base/head SHA；changed_files；schema/config diff；review notes；rollback | 越界规则变化/未知资产影响为Blocked；不能删测试换通过。 |
| S3 离线与反例验证 | 候选集成代码固定；适用测试/fixture完整。 | 执行本项至少正常/边界/故障三类case，记录命令/版本/退出码、全分母和skip。 通过：每必测case预期一致；文档-only项执行来源/结构/可重算校验。 | commands.json；cases.jsonl；TRX/log；manifest.json | 任一违约为Failed，关键case跳过为Blocked；绿色CI不取代实际用例。 |
| S4 集成、数据库与兼容验证 | S3通过且requires_before_integration产物达到所需合同。 | 固定SHA运行协议往返、真实进程/事件入口、一次性PG/恢复、两消费者对账等适用层。 通过：相关客户端/server/DB/route/hold/ledger状态一致；缺环境不替换静态阅读。 | integration manifest；database/test version；actual test coverage；state/asset comparison | PG关键case不得环境性skip；依赖完成指所需输入就绪，不要求整个父包先Accepted。 |
| S5 真实运行、体验或受控实验 | S3/S4正确性已通过；profile/目标/seed/时长/停止与清理预算预登记。 | 按LIVE/RENDER/EXPERIMENT/CAPACITY/AUDIT适用层实跑；窗口/drain/final与默认/candidate分列。 通过：达到本项明确runtime判据且raw可核验；无此层需求须写NotApplicable理由由MAIN批准。 | run/profile hash；raw+derived manifests；network/resource samples；video/screenshots/human notes where applicable | 负载不达/删失/样本不足/缺真人各单列，不能由更轻玩法证明原容量。 |
| S6 MAIN独立裁决与交付 | 本项所有适用层完成，或有可审查阻塞/NoChange证据。 | MAIN重跑关键case并核对artifact，签逐项结论；汇总G0-G5，保持PR Draft到合并决定。 通过：Accepted/NoChangeWithEvidence有当前证据；Failed/Blocked/Partial有原因与解除条件。 | MAIN decision record；gate coverage；default/config/rollback；remaining blockers | 没有证据不得Accepted；有阻塞的交付完整不等于验收通过。 |

可用执行状态：Queued/InProgress/NotRevalidated/ReadyForAcceptance/Accepted/NoChangeWithEvidence/Failed/Blocked/Partial。只有MAIN根据当前集成证据签Accepted。NoChange仍须当前正确性、剖析或配对结果与明确无需改动理由；缺环境、没跑测试不能写NoChange。Blocked必须写阶段、缺失输入、影响门、解除条件、责任人和下一步。

## 冻结规则与结果合同

保留现行首张合格单元素定核、R/P/B/K与逐卡floor、生命70/80/100、职业护盾帽、自然抽牌地板、20/5/3牌数、死亡装备掉落和价格投放。候选沿用CoreCardsSpent/FractionalRemainder/OptionalMonsterPool，正式默认保留；不自动启用红装、厄运、钻石、机器人或其他冻结玩法。

规范中性能/体验预算是待预登记的验收条件，不是已测最优值或正式SLO。原项目停止线继续保留：
- **source**：GAMEPLAY_LOAD_REPAIR_20260929.md §5.3
- **algorithm**：历史性能规则不改，3个连续有效窗口；新增证据/生成器安全停止独立。
- **http**：count>=20且P95>1500ms；error_rate>=10%按历史分母与取消单列版本说明。
- **realtime**：count>=10且P95>2000ms；reject_rate>=10%。
- **resources**：health失败或>5000ms；CPU>85%；可用内存/磁盘<15%；actor wait>100ms；发压机可用内存<2GiB单独安全停止。
- **classification**：项目诊断保护规则，不能冒充正式SLO；样本不足Unknown。

各运行独立给出 execution/evidence/load/gameplay/performance/cleanup 六维结果，不能只读exit0。运行窗口、STOP后收尾增量、最终累计是三套截止点；不把130与至少139、86与至少90自动改成较大值，A01须逐事件解释。

- 每cutoff总ack=各client ack之和=至少1次+至少2次+…人数之和
- started_cycles=completed+failed+cancelled+incomplete/active，互斥且截止点相同
- logical_started=success+error+timeout+cancelled+pending，attempt独立分母
- battle_started=kill+death+extract+voluntary_abandon+fallback+error+censored/active，兜底和drain分别
- 资产/牌实例变动按实际来源-消耗-转移守恒，不能用删流水或发补偿配平

## 执行档案与实验预算

| Profile | 目的 | 前置条件 | 初始预算/判断限制 |
|---|---|---|---|
| OFFLINE | 纯函数/真实轻量进程/本地事件fixture/确定性Domain测试；禁止默认访问公网。 | 工具链及测试接缝就绪；普通UI依赖Game时走项目场景。 | 测试deadline及子进程grace按case预登记，所有子进程有所有权。 |
| POSTGRES | 一次性PG执行匹配、结算、ledger、holds、room route、重启恢复与协议集成。 | 只接受明确的一次性测试库；所有关键DB case实际执行、版本与迁移固定。 | 每case事务/连接/重启/回收有上限；可复用numerical-acceptance的PG18，生产同版另行对照。 |
| LIVE | 单账号三局、三职业及10账号各三局；正常结果、兜底和drain分列。 | 当前客户端/server/config确定；监控/cleanup/STOP可用；沿用已授权的有界云端范围。 | 先单号，再10号各3局；运行时长和未完成上限提前声明，不在不足结果时无限延长。 |
| RENDER | 真实Godot有渲染交互，1280x720/1920x1080及目标窄布局；30/60/144fps与延迟分层。 | 不能用headless结果代替；实际菜单/按钮/等待/声效需要操作日志与画面。 | 三职业每账号至少3连续cycle；独立真人计划至少6名匿名参与者覆盖三职业×初学/熟练两层，每人3局；样本为初始可用性预算，不推出人群胜率。 |
| EXPERIMENT | 默认off与候选on、同预算/信息/种子/观察期，单因素后组合。 | 真实Resolver/CombatDeck/地图与room policy，不把路线工具冒充战斗仿真。 | 每个声明主要层首轮3组互不重叠seed块，每组至少1000配对seed；有限动作数/观察期；95%配对cluster区间与预登记多比较策略，精度不足为Inconclusive。 |
| CAPACITY | 原玩法负载、三组成对A/B、默认限流50/100与稳定/浸泡资源回收。 | 正确性与证据门通过；每IP读写预算可达、effective rate limits/actual request mix固定。 | 初始诊断保持合同建议：采样≤10秒/gap≤20秒、稳定10分钟/连续共同达标≥120秒/目标覆盖≥95%；循环模型active阈值须单独预登记，声称100 active必须阈值100；长稳先30分钟，更长预算另外冻结。 |
| AUDIT | 只读来源、历史raw和ledger告警；配置/镜像回滚演练在隔离实例。 | 有权访问所需证据并脱敏，敏感账号/密钥不入Git；资料不可得为Blocked。 | 告警按账户/时间范围有限查询；不自动修余额/删流水，不向他人发招募或通知。 |

容量合同在运行前固定profile hash。循环模型允许准备/排队/结算间隙，但active目标必须明写；声明100人在房时目标不能偷换成group_size=50。建议覆盖率等初始预算需在S0完成预登记；阈值缺失时验收函数拒绝运行，而非测试后选值。延迟分位数从同集合原样本计算；低样本、未完成尾延迟和删失必须单列。

数值候选对照记录所有种子及配对单位，95%区间按seed/对局聚类；主要指标和多重比较方案测前冻结。高删失或不识别P95时不得仅用完成样本判达标。三次/1000样本只是首轮预算，精度不足时给Inconclusive，不能保证收益。真人反馈计划与模拟/机器人数据分别存放。

## 六道汇总验收门

| 门 | 本轮通过条件 | 关键子项 | 全覆盖子项数 |
|---|---|---|---|
| G0 来源、范围与基线 | source/CI/image/config/seed/profile可追溯，文件锁与有界范围明确；missing单列。 | LOAD-11.1、LOAD-06.4、PR13-A01.1、PR13-A08.1、PR13-B12.1 | 12 |
| G1 离线、进程与合同 | 关键正常/边界/故障实际执行，数值合同编译修复，关键case无环境性skip。 | LOAD-01.4、LOAD-02.4、LOAD-03.4、LOAD-07.4、LOAD-10.1、PR13-A02.3、PR13-A06.4、PR13-A07.4、PR13-B02.4 | 44 |
| G2 玩法闭环和资产/战斗合同 | 正常三局/多账号、PG持久幂等、route/holds及资源/控制/选序/恢复合同一致；headless与render证据分层。 | LOAD-04.4、LOAD-05.4、LOAD-09.2、LOAD-10.2、LOAD-10.3、PR13-A03.4、PR13-A04.4、PR13-A05.3、PR13-A09.4、PR13-B02.4、PR13-B06.3、PR13-B07.3、PR13-B08.3、PR13-B09.3、PR13-B10.4、PR13-B11.4 | 92 |
| G3 观测、历史和体验对账 | 三截止点守恒，86/90与130/139及旧52/77差异可解释；缺序号不造关联，删失/兜底/未知完整。 | LOAD-03.4、LOAD-06.4、PR13-A01.4、PR13-A02.3、PR13-A06.3、PR13-B01.4、PR13-B03.4 | 44 |
| G4 传输收益、原容量、候选体验 | 三对同负载A/B、默认限流有效覆盖/长稳、数值配对/风险与真人反馈分别裁决；不足Unknown，不拿短战替原容量。 | LOAD-08.4、LOAD-09.4、LOAD-10.4、PR13-A10.4、PR13-B03.4、PR13-B04.4、PR13-B05.4、PR13-B06.4、PR13-B07.4、PR13-B08.4、PR13-B09.4 | 60 |
| G5 当前证据、源配置和回滚交付 | 132项实现或有证据NoChange/阻塞逐项可查；适用CI、账链告警、默认off、兼容与隔离回滚都有结论。完整交付允许列阻塞，验收通过要求适用阻塞清零。 | LOAD-11.2、LOAD-11.3、LOAD-11.4、PR13-A05.4、PR13-A07.4、PR13-A08.4、PR13-B12.4 | 44 |

每道门须检查全部带gate_refs的子项；表中关键项不替代全部覆盖。当前无新运行结果，所有G0～G5的运行验收仍须按证据裁决。

## 排程与文件写入约束

同文件单写入者。授权并行实施时最多3个worker；B06/B07/B08共享PlayerCombatState，B10/B11与LOAD04/05共享game_store，runner由AG-01统一写，协议生成只交AG-05。不要因计划列出角色就填写虚假运行ID。

| 波次 | 工作 | 退出条件 |
|---|---|---|
| W0 | LOAD-11.1、LOAD-06.4、PR13-A08.1、PR13-A01.1、PR13-B12.1 | 来源/字段/输入/文件锁冻结；raw不可用仅阻历史归因。 |
| W1 | LOAD-01..07、LOAD-09.1..2、PR13-A01..07、PR13-B01..03 | 可信统计/STOP尾部/ready与结算恢复、真实PG、数值CI和可重放实验基线。 |
| W2 | PR13-B10、PR13-B11、PR13-B04 | 顺序/反馈/等待可见、有渲染交互；默认构筑/脚本问题归因。 |
| W3 | LOAD-08、LOAD-09.3..4、PR13-A06、PR13-B05..09 | 证据驱动单因素候选，默认off、正确性与版本合同通过；无收益可NoChange。 |
| W4 | LOAD-10、PR13-A09、PR13-A10、PR13-B12.2..3 | 固定SHA独立故障/多局/渲染/off-on、三对A/B与有效默认容量/长稳。 |
| W5 | PR13-B12.4、PR13-A08.4、LOAD-11.4 | MAIN逐项裁决、G0-G5证据、未完清单/回滚/PR同步。 |

波次是工作安排，真正进入S4/S5以逐项依赖为准。A08.1/LOAD11.1先冻结，LOAD11.4最后交付；B02只需基线输入即可修合同，不等待LOAD10全父包完成。

## 132项详细任务

每项的三条检查分别覆盖正常路径、边界或故障；case编号与预期唯一。下面的步骤与输入足够建立fixture，实施时将实际状态、日志/DB/route/资产比较写入同编号case。尚未存在的CLI或fixture由所属任务实现后登记，不用示例冒充已跑命令。

### LOAD-01 状态、进程归属与真实人数

负责：AG-01。文件：`tools/gameplay_load_validation.py`、`tools/gameplay_load_test.py`、`tools/tests`。

#### LOAD-01.1 输入schema

输入：已冻结状态/事件字段及有限值规则。进入集成前所需子项：LOAD-11.1、LOAD-06.4。

实施：校验容器、标量、PID、时间、计数和数组元素；坏行输出invalid_schema且继续有界处理。

| 检查 | 操作/注入 | 预期结果 |
|---|---|---|
| LOAD-01.1-T01 | None/list状态 | 记录无效不抛异常 |
| LOAD-01.1-T02 | bool冒充PID/NaN耗时 | 拒绝且保留已知失败分子 |
| LOAD-01.1-T03 | 部分合法部分坏行 | 合法行保留并使证据无效 |

通过：所有负例有分类，采样函数不异常退出，非法值不变成0延迟或成功。

执行：OFFLINE；命令入口：C-PY；关联门：G1。S5：NotApplicableWithReason，仅凭指定离线/集成产物即可判定本子项；公网压测不增加该判据可信度。

交付：`outputs/pr13-acceptance/<integration_sha>/LOAD-01.1/`，包含report/cases/commands/manifest，命令记录退出码及skip；报告填统一证据字段。本轮规格复核记录：NotRevalidated，历史状态仅作来源：InProgress，未签署Accepted；后续真实状态写入对应队列与acceptance_record。

失败：任一必测用例与预期不符为Failed；缺输入/环境/证据为Blocked；仅完成部分层次为Partial，不升级Accepted。 回滚：按任务独立提交回退统计/runner；保留原raw及算法版本，不覆盖已归档报告。

#### LOAD-01.2 唯一进程归属

输入：本轮启动台账与进程epoch。进入集成前所需子项：LOAD-01.1。

实施：在线、遥测和累计周期使用同一run/client/epoch/PID核验；已退出合法历史只计累计。

| 检查 | 操作/注入 | 预期结果 |
|---|---|---|
| LOAD-01.2-T01 | 本轮活进程 | 同时允许活跃与累计 |
| LOAD-01.2-T02 | 同PID新epoch/外部run | 不归属且不增加人数 |
| LOAD-01.2-T03 | 本轮成功退出有尾事件 | 累计保留、在线归零 |

通过：所有聚合先验归属，同一身份最多一个活跃状态，无跨run污染。

执行：OFFLINE；命令入口：C-PY；关联门：G1。S5：NotApplicableWithReason，仅凭指定离线/集成产物即可判定本子项；公网压测不增加该判据可信度。

交付：`outputs/pr13-acceptance/<integration_sha>/LOAD-01.2/`，包含report/cases/commands/manifest，命令记录退出码及skip；报告填统一证据字段。本轮规格复核记录：NotRevalidated，历史状态仅作来源：InProgress，未签署Accepted；后续真实状态写入对应队列与acceptance_record。

失败：任一必测用例与预期不符为Failed；缺输入/环境/证据为Blocked；仅完成部分层次为Partial，不升级Accepted。 回滚：按任务独立提交回退统计/runner；保留原raw及算法版本，不覆盖已归档报告。

#### LOAD-01.3 拆分负载人数

输入：本轮进程与权威/客户端状态来源。进入集成前所需子项：LOAD-01.2。

实施：输出spawned/alive/fresh/online/room_state/active_in_room，无法采集server_confirmed时写null及原因。

| 检查 | 操作/注入 | 预期结果 |
|---|---|---|
| LOAD-01.3-T01 | 离线保留room | room_state为1、active为0 |
| LOAD-01.3-T02 | 成功退出仍有历史文件 | online为0 |
| LOAD-01.3-T03 | 缺服务端确认入口 | null不可替换为客户端数 |

通过：人数列各有定义和截止点，客户端active明确为存活且新鲜且在线且在房。

执行：OFFLINE；命令入口：C-PY；关联门：G1。S5：NotApplicableWithReason，仅凭指定离线/集成产物即可判定本子项；公网压测不增加该判据可信度。

交付：`outputs/pr13-acceptance/<integration_sha>/LOAD-01.3/`，包含report/cases/commands/manifest，命令记录退出码及skip；报告填统一证据字段。本轮规格复核记录：NotRevalidated，历史状态仅作来源：InProgress，未签署Accepted；后续真实状态写入对应队列与acceptance_record。

失败：任一必测用例与预期不符为Failed；缺输入/环境/证据为Blocked；仅完成部分层次为Partial，不升级Accepted。 回滚：按任务独立提交回退统计/runner；保留原raw及算法版本，不覆盖已归档报告。

#### LOAD-01.4 真实进程反例

输入：可控子进程、临时目录和单调时钟接缝。进入集成前所需子项：LOAD-01.3。

实施：实际启动子进程产生状态，再注入慢启动/缺报/退出/PID重用；启动宽限按实际launch计。

| 检查 | 操作/注入 | 预期结果 |
|---|---|---|
| LOAD-01.4-T01 | 宽限内慢启动 | 不误报missing |
| LOAD-01.4-T02 | 异常退出码7 | failed_process可定位 |
| LOAD-01.4-T03 | 墙钟跳变/陈旧状态 | 单调宽限不变、陈旧不计在线 |

通过：真实子进程全被回收，反例不靠仅构造dict替代进程行为。

执行：OFFLINE；命令入口：C-PY；关联门：G1。S5：NotApplicableWithReason，仅凭指定离线/集成产物即可判定本子项；公网压测不增加该判据可信度。

交付：`outputs/pr13-acceptance/<integration_sha>/LOAD-01.4/`，包含report/cases/commands/manifest，命令记录退出码及skip；报告填统一证据字段。本轮规格复核记录：NotRevalidated，历史状态仅作来源：Planned，未签署Accepted；后续真实状态写入对应队列与acceptance_record。

失败：任一必测用例与预期不符为Failed；缺输入/环境/证据为Blocked；仅完成部分层次为Partial，不升级Accepted。 回滚：按任务独立提交回退统计/runner；保留原raw及算法版本，不覆盖已归档报告。

### LOAD-02 停止、结果与业务清理

负责：AG-01。文件：`tools/gameplay_load_validation.py`、`tools/gameplay_load_test.py`、`tools/tests`、`tools/cloud_load_test.py`。

#### LOAD-02.1 多维结果模型

输入：证据/负载/流程/性能/清理合同。进入集成前所需子项：LOAD-01.2。

实施：独立生成六维判定，保存首个和全部触发；exit0只由适用合同全满足推出。

| 检查 | 操作/注入 | 预期结果 |
|---|---|---|
| LOAD-02.1-T01 | 时限到但负载未达 | execution结束、load失败 |
| LOAD-02.1-T02 | 先业务失败后人工STOP | 保留业务失败 |
| LOAD-02.1-T03 | 性能超线且证据损坏 | 记录两原因且证据无效优先退出码3 |

通过：不把一个stop_reason等同所有验收通过；允许Unknown但不能升Pass。

执行：OFFLINE、POSTGRES；命令入口：C-PY、C-SERVER；关联门：G1、G2。S5：NotApplicableWithReason，仅凭指定离线/集成产物即可判定本子项；公网压测不增加该判据可信度。

交付：`outputs/pr13-acceptance/<integration_sha>/LOAD-02.1/`，包含report/cases/commands/manifest，命令记录退出码及skip；报告填统一证据字段。本轮规格复核记录：NotRevalidated，历史状态仅作来源：Planned，未签署Accepted；后续真实状态写入对应队列与acceptance_record。

失败：任一必测用例与预期不符为Failed；缺输入/环境/证据为Blocked；仅完成部分层次为Partial，不升级Accepted。 回滚：按任务独立提交回退统计/runner；保留原raw及算法版本，不覆盖已归档报告。

#### LOAD-02.2 STOP前后边界

输入：STOP monotonic时点及发起上下文。进入集成前所需子项：LOAD-02.1、LOAD-06.2。

实施：区分停止前业务失败、正常取消、停止后真实错误和结果未知写入；迟到事件按原上下文归档。

| 检查 | 操作/注入 | 预期结果 |
|---|---|---|
| LOAD-02.2-T01 | STOP前超时 | 业务失败不变取消 |
| LOAD-02.2-T02 | STOP后正常等待取消 | 不计服务错误或完成 |
| LOAD-02.2-T03 | ack已提交结果未知 | pending直到权威核实 |

通过：每cycle一个终态，取消不抹去先前失败，未知资产写入不猜成功/失败。

执行：OFFLINE、POSTGRES；命令入口：C-PY、C-SERVER；关联门：G1、G2。S5：NotApplicableWithReason，仅凭指定离线/集成产物即可判定本子项；公网压测不增加该判据可信度。

交付：`outputs/pr13-acceptance/<integration_sha>/LOAD-02.2/`，包含report/cases/commands/manifest，命令记录退出码及skip；报告填统一证据字段。本轮规格复核记录：NotRevalidated，历史状态仅作来源：InProgress，未签署Accepted；后续真实状态写入对应队列与acceptance_record。

失败：任一必测用例与预期不符为Failed；缺输入/环境/证据为Blocked；仅完成部分层次为Partial，不升级Accepted。 回滚：按任务独立提交回退统计/runner；保留原raw及算法版本，不覆盖已归档报告。

#### LOAD-02.3 有界清理和应急报告

输入：拥有进程清单、grace与服务端回收时限。进入集成前所需子项：LOAD-02.2。

实施：排队取消/结算保留/关闭连接/回收进程分步；最终报告写失败产出独立应急摘要。

| 检查 | 操作/注入 | 预期结果 |
|---|---|---|
| LOAD-02.3-T01 | 正常响应STOP | grace内退出且服务后置状态可恢复 |
| LOAD-02.3-T02 | 子进程hang | 仅终止本轮PID并记录forced |
| LOAD-02.3-T03 | 最终文件写失败 | 应急报告存在且不可Pass |

通过：进程清理与业务清理分列，所有强退和报告失败可见，非本轮进程不被操作。

执行：OFFLINE、POSTGRES；命令入口：C-PY、C-SERVER；关联门：G1、G2。S5：NotApplicableWithReason，仅凭指定离线/集成产物即可判定本子项；公网压测不增加该判据可信度。

交付：`outputs/pr13-acceptance/<integration_sha>/LOAD-02.3/`，包含report/cases/commands/manifest，命令记录退出码及skip；报告填统一证据字段。本轮规格复核记录：NotRevalidated，历史状态仅作来源：InProgress，未签署Accepted；后续真实状态写入对应队列与acceptance_record。

失败：任一必测用例与预期不符为Failed；缺输入/环境/证据为Blocked；仅完成部分层次为Partial，不升级Accepted。 回滚：按任务独立提交回退统计/runner；保留原raw及算法版本，不覆盖已归档报告。

#### LOAD-02.4 退出码兼容

输入：当前调用者和旧报告算法版本。进入集成前所需子项：LOAD-02.3。

实施：固定0/1/2/3/130及preparation-only语义，调用者读取六维结果而非只读0。

| 检查 | 操作/注入 | 预期结果 |
|---|---|---|
| LOAD-02.4-T01 | preparation-only exit0 | 标仅准备不算压测成功 |
| LOAD-02.4-T02 | redline | exit2且记录全部触发 |
| LOAD-02.4-T03 | invalid/人工STOP | 分别3/130 |

通过：新旧调用者有子进程集成用例，任何未完成/无证据运行不能冒充Passed。

执行：OFFLINE、POSTGRES；命令入口：C-PY、C-SERVER；关联门：G1、G2。S5：NotApplicableWithReason，仅凭指定离线/集成产物即可判定本子项；公网压测不增加该判据可信度。

交付：`outputs/pr13-acceptance/<integration_sha>/LOAD-02.4/`，包含report/cases/commands/manifest，命令记录退出码及skip；报告填统一证据字段。本轮规格复核记录：NotRevalidated，历史状态仅作来源：Planned，未签署Accepted；后续真实状态写入对应队列与acceptance_record。

失败：任一必测用例与预期不符为Failed；缺输入/环境/证据为Blocked；仅完成部分层次为Partial，不升级Accepted。 回滚：按任务独立提交回退统计/runner；保留原raw及算法版本，不覆盖已归档报告。

### LOAD-03 事件守恒与统计口径

负责：AG-01。文件：`tools/gameplay_load_validation.py`、`tools/gameplay_load_test.py`、`tools/tests`。

#### LOAD-03.1 事件水位

输入：JSONL与状态snapshot的序号合同。进入集成前所需子项：LOAD-01.2、LOAD-06.4。

实施：用run/client/epoch/event_seq增量消费；检测重复/乱序/缺口/截断/尾部未flush。

| 检查 | 操作/注入 | 预期结果 |
|---|---|---|
| LOAD-03.1-T01 | 同毫秒两事件 | 均消费且仅一次 |
| LOAD-03.1-T02 | seq1/3缺2 | lost_count=1证据无效 |
| LOAD-03.1-T03 | 轮转/重启换epoch | 各自水位不混用 |

通过：JSONL原样本与汇总逐事件可对账；缺失不能因下次快照到达静默消失。

执行：OFFLINE；命令入口：C-PY；关联门：G1、G3。S5：NotApplicableWithReason，仅凭指定离线/集成产物即可判定本子项；公网压测不增加该判据可信度。

交付：`outputs/pr13-acceptance/<integration_sha>/LOAD-03.1/`，包含report/cases/commands/manifest，命令记录退出码及skip；报告填统一证据字段。本轮规格复核记录：NotRevalidated，历史状态仅作来源：InProgress，未签署Accepted；后续真实状态写入对应队列与acceptance_record。

失败：任一必测用例与预期不符为Failed；缺输入/环境/证据为Blocked；仅完成部分层次为Partial，不升级Accepted。 回滚：按任务独立提交回退统计/runner；保留原raw及算法版本，不覆盖已归档报告。

#### LOAD-03.2 生命周期阶段

输入：请求发起时的phase/cycle合同。进入集成前所需子项：LOAD-03.1。

实施：按login/initial/matchmaking/playing/settlement/cleanup显式分层；无标签历史标legacy_unknown。

| 检查 | 操作/注入 | 预期结果 |
|---|---|---|
| LOAD-03.2-T01 | playing中bootstrap | 归playing |
| LOAD-03.2-T02 | settlement轮询 | 归settlement |
| LOAD-03.2-T03 | 旧无标签bootstrap | unknown且旧口径单列 |

通过：当前阶段与历史auth-excluded列不能互相替代；迟到回包仍用发起阶段。

执行：OFFLINE；命令入口：C-PY；关联门：G1、G3。S5：NotApplicableWithReason，仅凭指定离线/集成产物即可判定本子项；公网压测不增加该判据可信度。

交付：`outputs/pr13-acceptance/<integration_sha>/LOAD-03.2/`，包含report/cases/commands/manifest，命令记录退出码及skip；报告填统一证据字段。本轮规格复核记录：NotRevalidated，历史状态仅作来源：InProgress，未签署Accepted；后续真实状态写入对应队列与acceptance_record。

失败：任一必测用例与预期不符为Failed；缺输入/环境/证据为Blocked；仅完成部分层次为Partial，不升级Accepted。 回滚：按任务独立提交回退统计/runner；保留原raw及算法版本，不覆盖已归档报告。

#### LOAD-03.3 请求完整分母

输入：logical/attempt/command终态事件。进入集成前所需子项：LOAD-03.2。

实施：分开success/rejection/timeout/cancelled/decode_error/pending，耗时缺失仅减少valid_latency而不删除请求。

| 检查 | 操作/注入 | 预期结果 |
|---|---|---|
| LOAD-03.3-T01 | 一个请求两attempt | logical1、attempt2 |
| LOAD-03.3-T02 | 失败且duration为NaN | 失败分子仍1 |
| LOAD-03.3-T03 | operations重复telemetry | 只计一次 |

通过：started=各互斥终态+pending；all_attempt与valid_latency可独立重算。

执行：OFFLINE；命令入口：C-PY；关联门：G1、G3。S5：NotApplicableWithReason，仅凭指定离线/集成产物即可判定本子项；公网压测不增加该判据可信度。

交付：`outputs/pr13-acceptance/<integration_sha>/LOAD-03.3/`，包含report/cases/commands/manifest，命令记录退出码及skip；报告填统一证据字段。本轮规格复核记录：NotRevalidated，历史状态仅作来源：InProgress，未签署Accepted；后续真实状态写入对应队列与acceptance_record。

失败：任一必测用例与预期不符为Failed；缺输入/环境/证据为Blocked；仅完成部分层次为Partial，不升级Accepted。 回滚：按任务独立提交回退统计/runner；保留原raw及算法版本，不覆盖已归档报告。

#### LOAD-03.4 分布与错误率

输入：原始样本、窗口边界和原停止线。进入集成前所需子项：LOAD-03.3、LOAD-06.1。

实施：分路由/phase输出P50/P95/P99/max、吞吐、样本不足；全局从样本或可合并分布计算。

| 检查 | 操作/注入 | 预期结果 |
|---|---|---|
| LOAD-03.4-T01 | 两窗数量不同 | 不平均P95 |
| LOAD-03.4-T02 | N0/N19 | unavailable/insufficient不写达标 |
| LOAD-03.4-T03 | 失败请求在错误集合 | 分子分母同口径 |

通过：三截止点和全程指标可重算，末窗零错误不取代全场；算法版本明确。

执行：OFFLINE；命令入口：C-PY；关联门：G1、G3。S5：NotApplicableWithReason，仅凭指定离线/集成产物即可判定本子项；公网压测不增加该判据可信度。

交付：`outputs/pr13-acceptance/<integration_sha>/LOAD-03.4/`，包含report/cases/commands/manifest，命令记录退出码及skip；报告填统一证据字段。本轮规格复核记录：NotRevalidated，历史状态仅作来源：Planned，未签署Accepted；后续真实状态写入对应队列与acceptance_record。

失败：任一必测用例与预期不符为Failed；缺输入/环境/证据为Blocked；仅完成部分层次为Partial，不升级Accepted。 回滚：按任务独立提交回退统计/runner；保留原raw及算法版本，不覆盖已归档报告。

### LOAD-04 ready状态机与权威恢复

负责：AG-02。文件：`client/tests/gameplay_load_client.gd`、`client/state/game_store.gd`、`client/tests`、`server/src/FantasyCard.Server/Matchmaking`、`server/src/FantasyCard.Server/Rooms`、`server/tests/FantasyCard.Server.Tests`。

#### LOAD-04.1 当前匹配状态机

输入：ticket/preparation/match/room/deadline真实字段。进入集成前所需子项：LOAD-11.1、LOAD-06.4。

实施：定义Queued至RoomStarted及取消/超时终态，权威ticket校验后才确认当前match。

| 检查 | 操作/注入 | 预期结果 |
|---|---|---|
| LOAD-04.1-T01 | match.found先到 | 不凭非空prompt误进房 |
| LOAD-04.1-T02 | 第二局旧started | 不覆盖新match |
| LOAD-04.1-T03 | 空RoomReadyCommand | 不私塞未约定字段 |

通过：转移表每条有事件来源与关联条件，非法转移拒绝且记录原因。

执行：OFFLINE、POSTGRES、LIVE；命令入口：C-GODOT、C-SERVER、C-LIVE；关联门：G2。S5：Required，按所列profile取得真实执行证据；历史结果不能冒充当前集成SHA。

交付：`outputs/pr13-acceptance/<integration_sha>/LOAD-04.1/`，包含report/cases/commands/manifest，命令记录退出码及skip；报告填统一证据字段。本轮规格复核记录：NotRevalidated，历史状态仅作来源：InProgress，未签署Accepted；后续真实状态写入对应队列与acceptance_record。

失败：任一必测用例与预期不符为Failed；缺输入/环境/证据为Blocked；仅完成部分层次为Partial，不升级Accepted。 回滚：回退客户端状态/流程提交，保留未确认结算上下文；不清空服务器资产或重放游标。

#### LOAD-04.2 有界ready发送

输入：send返回值、连接状态与服务端deadline。进入集成前所需子项：LOAD-04.1。

实施：send=false不认成功；次数/截止双界；accepted后迟到required不回退。

| 检查 | 操作/注入 | 预期结果 |
|---|---|---|
| LOAD-04.2-T01 | 三次均send=false | 有限失败终态 |
| LOAD-04.2-T02 | accepted先到/required后到 | 保持accepted不重发 |
| LOAD-04.2-T03 | deadline已过 | 不发送并恢复权威终态 |

通过：无无限重试、跨match确认或靠延长服务端15秒规则通过。

执行：OFFLINE、POSTGRES、LIVE；命令入口：C-GODOT、C-SERVER、C-LIVE；关联门：G2。S5：Required，按所列profile取得真实执行证据；历史结果不能冒充当前集成SHA。

交付：`outputs/pr13-acceptance/<integration_sha>/LOAD-04.2/`，包含report/cases/commands/manifest，命令记录退出码及skip；报告填统一证据字段。本轮规格复核记录：NotRevalidated，历史状态仅作来源：InProgress，未签署Accepted；后续真实状态写入对应队列与acceptance_record。

失败：任一必测用例与预期不符为Failed；缺输入/环境/证据为Blocked；仅完成部分层次为Partial，不升级Accepted。 回滚：回退客户端状态/流程提交，保留未确认结算上下文；不清空服务器资产或重放游标。

#### LOAD-04.3 缺通知/started恢复

输入：ticket查询、snapshot/resume与本机时间。进入集成前所需子项：LOAD-04.2。

实施：通知丢失也启动有界权威查询；分别测queue/ready/start等待，不清全局WS游标。

| 检查 | 操作/注入 | 预期结果 |
|---|---|---|
| LOAD-04.3-T01 | required完全丢失但ticket可ready | 恢复并合法确认 |
| LOAD-04.3-T02 | accepted后无started | 查询权威room或明确失败 |
| LOAD-04.3-T03 | snapshot属旧match | 拒绝且继续当前恢复 |

通过：不能无限等通知，room快照只应用当前匹配；每种超时可归因。

执行：OFFLINE、POSTGRES、LIVE；命令入口：C-GODOT、C-SERVER、C-LIVE；关联门：G2。S5：Required，按所列profile取得真实执行证据；历史结果不能冒充当前集成SHA。

交付：`outputs/pr13-acceptance/<integration_sha>/LOAD-04.3/`，包含report/cases/commands/manifest，命令记录退出码及skip；报告填统一证据字段。本轮规格复核记录：NotRevalidated，历史状态仅作来源：Planned，未签署Accepted；后续真实状态写入对应队列与acceptance_record。

失败：任一必测用例与预期不符为Failed；缺输入/环境/证据为Blocked；仅完成部分层次为Partial，不升级Accepted。 回滚：回退客户端状态/流程提交，保留未确认结算上下文；不清空服务器资产或重放游标。

#### LOAD-04.4 ready全矩阵

输入：可暂停事件/请求的真实入口测试接缝。进入集成前所需子项：LOAD-04.3。

实施：组合重复/乱序/丢失/send失败/断连/STOP/旧局事件；记录预期终态与票据后置状态。

| 检查 | 操作/注入 | 预期结果 |
|---|---|---|
| LOAD-04.4-T01 | required丢失再重连 | 权威恢复 |
| LOAD-04.4-T02 | 注册失败再恢复 | 至多一个room |
| LOAD-04.4-T03 | STOP排队/ready | 取消或明确超时回收 |

通过：每种反例先复现或证明当前正确，再在集成SHA运行；同账号三局第二次匹配不污染。

执行：OFFLINE、POSTGRES、LIVE；命令入口：C-GODOT、C-SERVER、C-LIVE；关联门：G2。S5：Required，按所列profile取得真实执行证据；历史结果不能冒充当前集成SHA。

交付：`outputs/pr13-acceptance/<integration_sha>/LOAD-04.4/`，包含report/cases/commands/manifest，命令记录退出码及skip；报告填统一证据字段。本轮规格复核记录：NotRevalidated，历史状态仅作来源：Planned，未签署Accepted；后续真实状态写入对应队列与acceptance_record。

失败：任一必测用例与预期不符为Failed；缺输入/环境/证据为Blocked；仅完成部分层次为Partial，不升级Accepted。 回滚：回退客户端状态/流程提交，保留未确认结算上下文；不清空服务器资产或重放游标。

### LOAD-05 结算、多局与取消

负责：AG-02。文件：`client/tests/gameplay_load_client.gd`、`client/state/game_store.gd`、`client/tests`、`server/src/FantasyCard.Server/Settlement`。

#### LOAD-05.1 服务端ack完成依据

输入：当前match/settlement与ack权威响应。进入集成前所需子项：LOAD-04.1、LOAD-02.1。

实施：返回成功/拒绝/忙/过期会话/结果未知类型，只有同match真实ack成功才计completed。

| 检查 | 操作/注入 | 预期结果 |
|---|---|---|
| LOAD-05.1-T01 | UI乐观清空但ack失败 | 不completed且恢复receipt |
| LOAD-05.1-T02 | busy拒绝 | 不发送不completed |
| LOAD-05.1-T03 | 他match的receipt | 拒绝且当前状态不变 |

通过：completed具有唯一ack证据，清空UI不是成功凭据。

执行：OFFLINE、POSTGRES、LIVE；命令入口：C-GODOT、C-SERVER、C-LIVE；关联门：G2。S5：Required，按所列profile取得真实执行证据；历史结果不能冒充当前集成SHA。

交付：`outputs/pr13-acceptance/<integration_sha>/LOAD-05.1/`，包含report/cases/commands/manifest，命令记录退出码及skip；报告填统一证据字段。本轮规格复核记录：NotRevalidated，历史状态仅作来源：InProgress，未签署Accepted；后续真实状态写入对应队列与acceptance_record。

失败：任一必测用例与预期不符为Failed；缺输入/环境/证据为Blocked；仅完成部分层次为Partial，不升级Accepted。 回滚：回退客户端状态/流程提交，保留未确认结算上下文；不清空服务器资产或重放游标。

#### LOAD-05.2 跨局状态隔离

输入：会话、cycle epoch、match和异步发起context。进入集成前所需子项：LOAD-05.1。

实施：成功清局部ready/ticket/选牌/pending/poll；迟到HTTP/WS核验发起epoch，失败原状态可恢复。

| 检查 | 操作/注入 | 预期结果 |
|---|---|---|
| LOAD-05.2-T01 | 第一局回包在第二局到达 | 不恢复旧room |
| LOAD-05.2-T02 | ack失败 | 恢复同局装备/命令与receipt |
| LOAD-05.2-T03 | 同会话连续三局 | WS全局游标不重置 |

通过：每局资源和回调隔离；新局不被旧事件清空，状态清理表完整。

执行：OFFLINE、POSTGRES、LIVE；命令入口：C-GODOT、C-SERVER、C-LIVE；关联门：G2。S5：Required，按所列profile取得真实执行证据；历史结果不能冒充当前集成SHA。

交付：`outputs/pr13-acceptance/<integration_sha>/LOAD-05.2/`，包含report/cases/commands/manifest，命令记录退出码及skip；报告填统一证据字段。本轮规格复核记录：NotRevalidated，历史状态仅作来源：InProgress，未签署Accepted；后续真实状态写入对应队列与acceptance_record。

失败：任一必测用例与预期不符为Failed；缺输入/环境/证据为Blocked；仅完成部分层次为Partial，不升级Accepted。 回滚：回退客户端状态/流程提交，保留未确认结算上下文；不清空服务器资产或重放游标。

#### LOAD-05.3 各await取消

输入：取消token、队列权威状态和恢复信息。进入集成前所需子项：LOAD-05.2、LOAD-02.2。

实施：登录/排队/进房/战斗/结算/ack所有等待点有取消；业务回收独立于进程退出。

| 检查 | 操作/注入 | 预期结果 |
|---|---|---|
| LOAD-05.3-T01 | STOP前尚未room | Cancelled不追加伪失败 |
| LOAD-05.3-T02 | ack发送后STOP | Unknown直到权威确认 |
| LOAD-05.3-T03 | settlement待holds | 保留恢复ID不删流水 |

通过：取消有界，未确认资产操作可恢复，不二次领奖不丢失业务状态。

执行：OFFLINE、POSTGRES、LIVE；命令入口：C-GODOT、C-SERVER、C-LIVE；关联门：G2。S5：Required，按所列profile取得真实执行证据；历史结果不能冒充当前集成SHA。

交付：`outputs/pr13-acceptance/<integration_sha>/LOAD-05.3/`，包含report/cases/commands/manifest，命令记录退出码及skip；报告填统一证据字段。本轮规格复核记录：NotRevalidated，历史状态仅作来源：Planned，未签署Accepted；后续真实状态写入对应队列与acceptance_record。

失败：任一必测用例与预期不符为Failed；缺输入/环境/证据为Blocked；仅完成部分层次为Partial，不升级Accepted。 回滚：回退客户端状态/流程提交，保留未确认结算上下文；不清空服务器资产或重放游标。

#### LOAD-05.4 幂等三局矩阵

输入：一次性数据库与真实Godot会话。进入集成前所需子项：LOAD-05.3、LOAD-04.4。

实施：测ack响应丢失/重复receipt/旧snapshot/重启/重连；对每cutoff核对cycle与资产。

| 检查 | 操作/注入 | 预期结果 |
|---|---|---|
| LOAD-05.4-T01 | ack提交后响应丢失再重试 | 同一receipt/资产只一次 |
| LOAD-05.4-T02 | pending holds | 不对外ready |
| LOAD-05.4-T03 | 三局夹一失败重试 | 仅真实成功计一次 |

通过：started=completed+failed+cancelled+incomplete，同cycle互斥；资产账本与持久状态一致。

执行：OFFLINE、POSTGRES、LIVE；命令入口：C-GODOT、C-SERVER、C-LIVE；关联门：G2。S5：Required，按所列profile取得真实执行证据；历史结果不能冒充当前集成SHA。

交付：`outputs/pr13-acceptance/<integration_sha>/LOAD-05.4/`，包含report/cases/commands/manifest，命令记录退出码及skip；报告填统一证据字段。本轮规格复核记录：NotRevalidated，历史状态仅作来源：Planned，未签署Accepted；后续真实状态写入对应队列与acceptance_record。

失败：任一必测用例与预期不符为Failed；缺输入/环境/证据为Blocked；仅完成部分层次为Partial，不升级Accepted。 回滚：回退客户端状态/流程提交，保留未确认结算上下文；不清空服务器资产或重放游标。

### LOAD-06 端到端遥测合同

负责：MAIN。文件：`client/network/gateway.gd`、`client/network/reusable_http_client.gd`、`client/tests`、`client/tests/gameplay_load_client.gd`、`client/state/game_store.gd`、`client/tests`、`server/src/FantasyCard.Server/Common/ServerMetrics.cs`。

#### LOAD-06.1 HTTP不可变上下文

输入：逻辑ID/幂等键及request开始点。进入集成前所需子项：LOAD-06.4。

实施：冻结origin/session/cycle/phase/trace；记录每attempt、decode、backoff、body、总等待与pending终态。

| 检查 | 操作/注入 | 预期结果 |
|---|---|---|
| LOAD-06.1-T01 | 两次重试 | logicalID/写幂等键不变 |
| LOAD-06.1-T02 | 切cycle后旧请求完成 | 仍归旧cycle |
| LOAD-06.1-T03 | 超时/解码失败 | 都有attempt和logical终态 |

通过：request与attempt可关联，回调不读取当前stage重贴标签。

执行：OFFLINE、POSTGRES、LIVE；命令入口：C-PY、C-GODOT、C-SERVER、C-LIVE；关联门：G3。S5：Required，按所列profile取得真实执行证据；历史结果不能冒充当前集成SHA。

交付：`outputs/pr13-acceptance/<integration_sha>/LOAD-06.1/`，包含report/cases/commands/manifest，命令记录退出码及skip；报告填统一证据字段。本轮规格复核记录：NotRevalidated，历史状态仅作来源：InProgress，未签署Accepted；后续真实状态写入对应队列与acceptance_record。

失败：任一必测用例与预期不符为Failed；缺输入/环境/证据为Blocked；仅完成部分层次为Partial，不升级Accepted。 回滚：按任务独立提交回退统计/runner；保留原raw及算法版本，不覆盖已归档报告。

#### LOAD-06.2 生命周期/玩法进度

输入：当前match/battle/command和可见状态。进入集成前所需子项：LOAD-06.4、LOAD-04.1。

实施：分transport_progress与gameplay_progress，记录prepare至ack及命令确认、有效状态变化。

| 检查 | 操作/注入 | 预期结果 |
|---|---|---|
| LOAD-06.2-T01 | pong/重复snapshot | 只续通信不续玩法 |
| LOAD-06.2-T02 | 0伤害但新抽牌机会 | 合法进展有原因 |
| LOAD-06.2-T03 | 拒绝/超时命令 | 独立事件不算成功 |

通过：能定位失败cycle的等待阶段；无事件到达掩盖停滞。

执行：OFFLINE、POSTGRES、LIVE；命令入口：C-PY、C-GODOT、C-SERVER、C-LIVE；关联门：G3。S5：Required，按所列profile取得真实执行证据；历史结果不能冒充当前集成SHA。

交付：`outputs/pr13-acceptance/<integration_sha>/LOAD-06.2/`，包含report/cases/commands/manifest，命令记录退出码及skip；报告填统一证据字段。本轮规格复核记录：NotRevalidated，历史状态仅作来源：InProgress，未签署Accepted；后续真实状态写入对应队列与acceptance_record。

失败：任一必测用例与预期不符为Failed；缺输入/环境/证据为Blocked；仅完成部分层次为Partial，不升级Accepted。 回滚：按任务独立提交回退统计/runner；保留原raw及算法版本，不覆盖已归档报告。

#### LOAD-06.3 服务端分段

输入：HTTP/DB/launch/actor/send入口及受控trace。进入集成前所需子项：LOAD-06.4。

实施：测本机连接获取/执行/锁等待、launch各段、command排队执行发送；无法可靠测量写null。

| 检查 | 操作/注入 | 预期结果 |
|---|---|---|
| LOAD-06.3-T01 | 慢DB连接 | 等待与SQL执行分开 |
| LOAD-06.3-T02 | 慢玩家send | 与actor执行分开 |
| LOAD-06.3-T03 | 大量不同match | Prometheus label数有界 |

通过：至少一个失败cycle可关联实际服务端trace；单位/起止统一且无高基数业务label。

执行：OFFLINE、POSTGRES、LIVE；命令入口：C-PY、C-GODOT、C-SERVER、C-LIVE；关联门：G3。S5：Required，按所列profile取得真实执行证据；历史结果不能冒充当前集成SHA。

交付：`outputs/pr13-acceptance/<integration_sha>/LOAD-06.3/`，包含report/cases/commands/manifest，命令记录退出码及skip；报告填统一证据字段。本轮规格复核记录：NotRevalidated，历史状态仅作来源：InProgress，未签署Accepted；后续真实状态写入对应队列与acceptance_record。

失败：任一必测用例与预期不符为Failed；缺输入/环境/证据为Blocked；仅完成部分层次为Partial，不升级Accepted。 回滚：按任务独立提交回退统计/runner；保留原raw及算法版本，不覆盖已归档报告。

#### LOAD-06.4 时间/缺失/脱敏

输入：字段字典、clock来源与采样规则。进入集成前所需子项：LOAD-11.1。

实施：冻结单位/基数/缺失原因/版本；UTC只关联，不跨机相减伪造DNS/TLS/单向延迟。

| 检查 | 操作/注入 | 预期结果 |
|---|---|---|
| LOAD-06.4-T01 | 本地单调钟测耗时 | 正确非负 |
| LOAD-06.4-T02 | 无TLS阶段hook | null+unavailable |
| LOAD-06.4-T03 | token/票据正文 | 脱敏审查拒绝入报告 |

通过：同字段同单位同语义；外部curl和Godot请求分列，敏感值不进入提交。

执行：OFFLINE、POSTGRES、LIVE；命令入口：C-PY、C-GODOT、C-SERVER、C-LIVE；关联门：G3。S5：Required，按所列profile取得真实执行证据；历史结果不能冒充当前集成SHA。

交付：`outputs/pr13-acceptance/<integration_sha>/LOAD-06.4/`，包含report/cases/commands/manifest，命令记录退出码及skip；报告填统一证据字段。本轮规格复核记录：NotRevalidated，历史状态仅作来源：InProgress，未签署Accepted；后续真实状态写入对应队列与acceptance_record。

失败：任一必测用例与预期不符为Failed；缺输入/环境/证据为Blocked；仅完成部分层次为Partial，不升级Accepted。 回滚：按任务独立提交回退统计/runner；保留原raw及算法版本，不覆盖已归档报告。

### LOAD-07 发压器资源、调度与故障

负责：AG-01。文件：`tools/gameplay_load_validation.py`、`tools/gameplay_load_test.py`、`tools/tests`、`client/tests/gameplay_load_client.gd`、`client/state/game_store.gd`、`client/tests`。

#### LOAD-07.1 有界探测调度

输入：deadline、worker数和monotonic计划。进入集成前所需子项：LOAD-01.1、LOAD-03.1、LOAD-06.4。

实施：分离健康/Prometheus探测，记录schedule/actual/lag，超时future不无界堆积。

| 检查 | 操作/注入 | 预期结果 |
|---|---|---|
| LOAD-07.1-T01 | 20秒探测阻塞 | 采样仍有明确延迟且不补发多组 |
| LOAD-07.1-T02 | worker全占 | 有界失败触发停止 |
| LOAD-07.1-T03 | 墙钟跳变 | 组间隔不变 |

通过：无无界future/追赶发压，监控失效不得继续扩组。

执行：OFFLINE、LIVE；命令入口：C-PY、C-LIVE；关联门：G1、G3、G4。S5：Required，按所列profile取得真实执行证据；历史结果不能冒充当前集成SHA。

交付：`outputs/pr13-acceptance/<integration_sha>/LOAD-07.1/`，包含report/cases/commands/manifest，命令记录退出码及skip；报告填统一证据字段。本轮规格复核记录：NotRevalidated，历史状态仅作来源：InProgress，未签署Accepted；后续真实状态写入对应队列与acceptance_record。

失败：任一必测用例与预期不符为Failed；缺输入/环境/证据为Blocked；仅完成部分层次为Partial，不升级Accepted。 回滚：按任务独立提交回退统计/runner；保留原raw及算法版本，不覆盖已归档报告。

#### LOAD-07.2 实际发压与资源

输入：psutil、Godot启动参数及帧时钟。进入集成前所需子项：LOAD-07.1。

实施：总/每进程CPU/RSS/可用内存/可得句柄与发包率；不可得值带原因，FPS候选单独profile。

| 检查 | 操作/注入 | 预期结果 |
|---|---|---|
| LOAD-07.2-T01 | 本机内存低于2GiB | 安全停止且非服务容量结论 |
| LOAD-07.2-T02 | 客户端退出 | 负载下降显式记录 |
| LOAD-07.2-T03 | 更改FPS | 新profile而非原基线 |

通过：生成器瓶颈和服务器指标分列，采样有实际launch时刻和速率。

执行：OFFLINE、LIVE；命令入口：C-PY、C-LIVE；关联门：G1、G3、G4。S5：Required，按所列profile取得真实执行证据；历史结果不能冒充当前集成SHA。

交付：`outputs/pr13-acceptance/<integration_sha>/LOAD-07.2/`，包含report/cases/commands/manifest，命令记录退出码及skip；报告填统一证据字段。本轮规格复核记录：NotRevalidated，历史状态仅作来源：InProgress，未签署Accepted；后续真实状态写入对应队列与acceptance_record。

失败：任一必测用例与预期不符为Failed；缺输入/环境/证据为Blocked；仅完成部分层次为Partial，不升级Accepted。 回滚：按任务独立提交回退统计/runner；保留原raw及算法版本，不覆盖已归档报告。

#### LOAD-07.3 有界JSONL与session隔离

输入：文件写入接缝、缓冲上限和autoload配置。进入集成前所需子项：LOAD-07.1、LOAD-06.2。

实施：批写/flush/轮转记录序号；会话隔离在autoload读取前；原子替换缺口仅用有界新鲜缓存。

| 检查 | 操作/注入 | 预期结果 |
|---|---|---|
| LOAD-07.3-T01 | 文件短暂缺失 | 复用本轮上一状态且受30秒stale界 |
| LOAD-07.3-T02 | 磁盘满/缓冲溢出 | lost并证据无效 |
| LOAD-07.3-T03 | 并行进程启动 | 不共享session身份 |

通过：内存/文件上限可测，退出尾部flush可对账，不静默丢事件换性能。

执行：OFFLINE、LIVE；命令入口：C-PY、C-LIVE；关联门：G1、G3、G4。S5：Required，按所列profile取得真实执行证据；历史结果不能冒充当前集成SHA。

交付：`outputs/pr13-acceptance/<integration_sha>/LOAD-07.3/`，包含report/cases/commands/manifest，命令记录退出码及skip；报告填统一证据字段。本轮规格复核记录：NotRevalidated，历史状态仅作来源：InProgress，未签署Accepted；后续真实状态写入对应队列与acceptance_record。

失败：任一必测用例与预期不符为Failed；缺输入/环境/证据为Blocked；仅完成部分层次为Partial，不升级Accepted。 回滚：按任务独立提交回退统计/runner；保留原raw及算法版本，不覆盖已归档报告。

#### LOAD-07.4 发压器故障矩阵

输入：轻量子进程、慢I/O/探测/时钟接缝。进入集成前所需子项：LOAD-07.2、LOAD-07.3。

实施：注入慢磁盘、坏JSON、单进程hang、信号、STOP与监控失败；记录停止后最终错误。

| 检查 | 操作/注入 | 预期结果 |
|---|---|---|
| LOAD-07.4-T01 | 坏最终JSON | 证据无效不Pass |
| LOAD-07.4-T02 | STOP后exit7 | 清理失败可见 |
| LOAD-07.4-T03 | 一进程hang | 有界强退并不操作其他PID |

通过：所有故障有分类和尾部验收；安全人数/时长上限不取消。

执行：OFFLINE、LIVE；命令入口：C-PY、C-LIVE；关联门：G1、G3、G4。S5：Required，按所列profile取得真实执行证据；历史结果不能冒充当前集成SHA。

交付：`outputs/pr13-acceptance/<integration_sha>/LOAD-07.4/`，包含report/cases/commands/manifest，命令记录退出码及skip；报告填统一证据字段。本轮规格复核记录：NotRevalidated，历史状态仅作来源：InProgress，未签署Accepted；后续真实状态写入对应队列与acceptance_record。

失败：任一必测用例与预期不符为Failed；缺输入/环境/证据为Blocked；仅完成部分层次为Partial，不升级Accepted。 回滚：按任务独立提交回退统计/runner；保留原raw及算法版本，不覆盖已归档报告。

### LOAD-08 HTTP与读取候选

负责：AG-03。文件：`client/network/gateway.gd`、`client/network/reusable_http_client.gd`、`client/tests`、`client/tests/gameplay_load_client.gd`、`client/state/game_store.gd`、`client/tests`、`server/src/FantasyCard.Server/Bootstrap`、`protocol/http/v1`。

#### LOAD-08.1 TLS连接复用边界

输入：真实引擎、本地TLS/chunked测试服务与旧transport。进入集成前所需子项：LOAD-05.4、LOAD-06.1、LOAD-07.4。

实施：复用顺序连接，重叠请求走兼容fallback；验证完整body而非简单Connected状态。

| 检查 | 操作/注入 | 预期结果 |
|---|---|---|
| LOAD-08.1-T01 | 完整body后server-close | 成功且下次重连 |
| LOAD-08.1-T02 | body/chunked中途断开 | 失败不回成功 |
| LOAD-08.1-T03 | 非法TLS/超2MiB | 拒绝且不降级校验 |

通过：无截断成功、跨origin/session泄漏，复用证据是底层连接行为；旧transport可回滚。

执行：OFFLINE、POSTGRES、EXPERIMENT；命令入口：C-GODOT、C-SERVER、C-PROTO、C-AB；关联门：G2、G4。S5：Required，按所列profile取得真实执行证据；历史结果不能冒充当前集成SHA。

交付：`outputs/pr13-acceptance/<integration_sha>/LOAD-08.1/`，包含report/cases/commands/manifest，命令记录退出码及skip；报告填统一证据字段。本轮规格复核记录：NotRevalidated，历史状态仅作来源：Conditional，未签署Accepted；后续真实状态写入对应队列与acceptance_record。

失败：任一必测用例与预期不符为Failed；缺输入/环境/证据为Blocked；仅完成部分层次为Partial，不升级Accepted。 回滚：回退客户端状态/流程提交，保留未确认结算上下文；不清空服务器资产或重放游标。

#### LOAD-08.2 GET单飞一致性

输入：同origin/session/path/params/cache-version读请求。进入集成前所需子项：LOAD-08.1。

实施：合并同一只读请求并共享真实结果；写后新版本隔离旧响应；先量化重复读取。

| 检查 | 操作/注入 | 预期结果 |
|---|---|---|
| LOAD-08.2-T01 | 同版本同GET两个调用 | 一个底层请求且结果相同 |
| LOAD-08.2-T02 | 写后迟到旧GET | 不覆盖新值 |
| LOAD-08.2-T03 | 两玩家/两版本/写请求 | 绝不合并 |

通过：请求数下降且状态新鲜无退化；无收益以数据裁决NoChange，不伪造正在处理成功。

执行：OFFLINE、POSTGRES、EXPERIMENT；命令入口：C-GODOT、C-SERVER、C-PROTO、C-AB；关联门：G2、G4。S5：Required，按所列profile取得真实执行证据；历史结果不能冒充当前集成SHA。

交付：`outputs/pr13-acceptance/<integration_sha>/LOAD-08.2/`，包含report/cases/commands/manifest，命令记录退出码及skip；报告填统一证据字段。本轮规格复核记录：NotRevalidated，历史状态仅作来源：Conditional，未签署Accepted；后续真实状态写入对应队列与acceptance_record。

失败：任一必测用例与预期不符为Failed；缺输入/环境/证据为Blocked；仅完成部分层次为Partial，不升级Accepted。 回滚：回退客户端状态/流程提交，保留未确认结算上下文；不清空服务器资产或重放游标。

#### LOAD-08.3 有界去同步重试

输入：retry分类、总deadline、Retry-After与幂等键。进入集成前所需子项：LOAD-08.2。

实施：抖动在最小等待之后、受总deadline/取消约束；不重放解码失败/跨会话不确定写入。

| 检查 | 操作/注入 | 预期结果 |
|---|---|---|
| LOAD-08.3-T01 | 429 Retry-After5 | 等待不少于5秒 |
| LOAD-08.3-T02 | retry中STOP | 有界取消保留原context |
| LOAD-08.3-T03 | 写请求503后重试 | 同键且资产一次 |

通过：用户总等待与attempt放大均报告；候选无确定收益可保留现行重试。

执行：OFFLINE、POSTGRES、EXPERIMENT；命令入口：C-GODOT、C-SERVER、C-PROTO、C-AB；关联门：G2、G4。S5：Required，按所列profile取得真实执行证据；历史结果不能冒充当前集成SHA。

交付：`outputs/pr13-acceptance/<integration_sha>/LOAD-08.3/`，包含report/cases/commands/manifest，命令记录退出码及skip；报告填统一证据字段。本轮规格复核记录：NotRevalidated，历史状态仅作来源：Conditional，未签署Accepted；后续真实状态写入对应队列与acceptance_record。

失败：任一必测用例与预期不符为Failed；缺输入/环境/证据为Blocked；仅完成部分层次为Partial，不升级Accepted。 回滚：回退客户端状态/流程提交，保留未确认结算上下文；不清空服务器资产或重放游标。

#### LOAD-08.4 结算轻量查询

输入：Bootstrap成本trace、已有settlement单项与holds规则。进入集成前所需子项：LOAD-08.3。

实施：有ID优先单项，无ID经协议评审最小只读入口；保留旧fallback/鉴权/match/holds边界。

| 检查 | 操作/注入 | 预期结果 |
|---|---|---|
| LOAD-08.4-T01 | 有settlementID | 不重复拉全catalog |
| LOAD-08.4-T02 | 其他玩家/旧match | 拒绝 |
| LOAD-08.4-T03 | pending holds/旧客户端 | 未ready且兼容fallback |

通过：每局字节/SQL/等待改善有三轮配对；无热点证据不新增接口，不绕过资产完成检查。

执行：OFFLINE、POSTGRES、EXPERIMENT；命令入口：C-GODOT、C-SERVER、C-PROTO、C-AB；关联门：G2、G4。S5：Required，按所列profile取得真实执行证据；历史结果不能冒充当前集成SHA。

交付：`outputs/pr13-acceptance/<integration_sha>/LOAD-08.4/`，包含report/cases/commands/manifest，命令记录退出码及skip；报告填统一证据字段。本轮规格复核记录：NotRevalidated，历史状态仅作来源：Conditional，未签署Accepted；后续真实状态写入对应队列与acceptance_record。

失败：任一必测用例与预期不符为Failed；缺输入/环境/证据为Blocked；仅完成部分层次为Partial，不升级Accepted。 回滚：回退客户端状态/流程提交，保留未确认结算上下文；不清空服务器资产或重放游标。

### LOAD-09 匹配、launch和定向服务优化

负责：AG-04。文件：`server/src/FantasyCard.Server/Matchmaking`、`server/src/FantasyCard.Server/Rooms`、`server/tests/FantasyCard.Server.Tests`、`server/src/FantasyCard.Server/Realtime`、`server/src/FantasyCard.Server/Common/ServerMetrics.cs`。

#### LOAD-09.1 enqueue回放关联

输入：同player/request与多preparation数据库fixture。进入集成前所需子项：LOAD-11.1。

实施：固定回放ticket与其preparation/match关联，与GetTicket一致，保留玩家锁/冲突。

| 检查 | 操作/注入 | 预期结果 |
|---|---|---|
| LOAD-09.1-T01 | 同request重放 | 同ticket/preparation/match |
| LOAD-09.1-T02 | 历史多局新preparation | 不返回旧match |
| LOAD-09.1-T03 | 同键异body | 幂等冲突不新建票据 |

通过：实际PostgreSQL复现与回归通过，无重复冻结或错误历史match。

执行：OFFLINE、POSTGRES、EXPERIMENT；命令入口：C-SERVER、C-AB；关联门：G2、G4。S5：Required，按所列profile取得真实执行证据；历史结果不能冒充当前集成SHA。

交付：`outputs/pr13-acceptance/<integration_sha>/LOAD-09.1/`，包含report/cases/commands/manifest，命令记录退出码及skip；报告填统一证据字段。本轮规格复核记录：NotRevalidated，历史状态仅作来源：InProgress，未签署Accepted；后续真实状态写入对应队列与acceptance_record。

失败：任一必测用例与预期不符为Failed；缺输入/环境/证据为Blocked；仅完成部分层次为Partial，不升级Accepted。 回滚：回退服务代码并复测旧新房间恢复；保留数据库备份/幂等流水，不用删行制造成功。

#### LOAD-09.2 launch与旧路由恢复

输入：Starting/Launching/Running及持久结算事实。进入集成前所需子项：LOAD-09.1、LOAD-04.4。

实施：注入snapshot保存/registry/MarkRunning失败；释放终态玩家路由只删仍指旧room者。

| 检查 | 操作/注入 | 预期结果 |
|---|---|---|
| LOAD-09.2-T01 | 保存失败 | 不宣称running且可恢复 |
| LOAD-09.2-T02 | A下一局/B旧局继续 | 旧snapshot不删A新路由 |
| LOAD-09.2-T03 | 重启恢复terminal | 不占活动路由且资产不二次扣 |

通过：DB、room registry、asset hold、客户端终态一致；不无lease增加launch worker。

执行：OFFLINE、POSTGRES、EXPERIMENT；命令入口：C-SERVER、C-AB；关联门：G2、G4。S5：Required，按所列profile取得真实执行证据；历史结果不能冒充当前集成SHA。

交付：`outputs/pr13-acceptance/<integration_sha>/LOAD-09.2/`，包含report/cases/commands/manifest，命令记录退出码及skip；报告填统一证据字段。本轮规格复核记录：NotRevalidated，历史状态仅作来源：InProgress，未签署Accepted；后续真实状态写入对应队列与acceptance_record。

失败：任一必测用例与预期不符为Failed；缺输入/环境/证据为Blocked；仅完成部分层次为Partial，不升级Accepted。 回滚：回退服务代码并复测旧新房间恢复；保留数据库备份/幂等流水，不用删行制造成功。

#### LOAD-09.3 慢连接隔离候选

输入：每玩家send wait和事件序列trace。进入集成前所需子项：LOAD-09.2、LOAD-06.3。

实施：先测队头阻塞；必要时同match内有界投递且每玩家序列仍保序。

| 检查 | 操作/注入 | 预期结果 |
|---|---|---|
| LOAD-09.3-T01 | 一慢三正常 | 正常玩家等待可量化且不无限拖住 |
| LOAD-09.3-T02 | pending发送32/16KiB保护 | 继续有效 |
| LOAD-09.3-T03 | found/required重放 | 同玩家先后次序不变 |

通过：性能收益配对可解释且无乱序/泄漏；无阻塞热点则NoChangeWithEvidence。

执行：OFFLINE、POSTGRES、EXPERIMENT；命令入口：C-SERVER、C-AB；关联门：G2、G4。S5：Required，按所列profile取得真实执行证据；历史结果不能冒充当前集成SHA。

交付：`outputs/pr13-acceptance/<integration_sha>/LOAD-09.3/`，包含report/cases/commands/manifest，命令记录退出码及skip；报告填统一证据字段。本轮规格复核记录：NotRevalidated，历史状态仅作来源：Conditional，未签署Accepted；后续真实状态写入对应队列与acceptance_record。

失败：任一必测用例与预期不符为Failed；缺输入/环境/证据为Blocked；仅完成部分层次为Partial，不升级Accepted。 回滚：回退服务代码并复测旧新房间恢复；保留数据库备份/幂等流水，不用删行制造成功。

#### LOAD-09.4 实例级热点裁决

输入：每核/容器/GC/Npgsql/SQL/序列化trace。进入集成前所需子项：LOAD-06.3、LOAD-07.4。

实施：逐热点最小候选，固定SQL计划与资源限额；不凭整机平均加资源。

| 检查 | 操作/注入 | 预期结果 |
|---|---|---|
| LOAD-09.4-T01 | DB等待热点 | 候选只针对已定位路径 |
| LOAD-09.4-T02 | actor处理正确 | 单写顺序不变 |
| LOAD-09.4-T03 | 三轮无收益 | 回退并记录NoChange |

通过：所有优化有前后同负载证据和回滚点，schema变化独立审查而非直接生产DDL。

执行：OFFLINE、POSTGRES、EXPERIMENT；命令入口：C-SERVER、C-AB；关联门：G2、G4。S5：Required，按所列profile取得真实执行证据；历史结果不能冒充当前集成SHA。

交付：`outputs/pr13-acceptance/<integration_sha>/LOAD-09.4/`，包含report/cases/commands/manifest，命令记录退出码及skip；报告填统一证据字段。本轮规格复核记录：NotRevalidated，历史状态仅作来源：Conditional，未签署Accepted；后续真实状态写入对应队列与acceptance_record。

失败：任一必测用例与预期不符为Failed；缺输入/环境/证据为Blocked；仅完成部分层次为Partial，不升级Accepted。 回滚：回退服务代码并复测旧新房间恢复；保留数据库备份/幂等流水，不用删行制造成功。

### LOAD-10 独立集成与负载验收

负责：AG-06。文件：`docs/plans`、`docs/reports`、`.github/workflows`、`tools/tests`、`client/tests`、`server/tests`。

#### LOAD-10.1 独立离线/协议套件

输入：原F01-F08负例及当前生成物。进入集成前所需子项：LOAD-01.4、LOAD-02.4、LOAD-03.4、LOAD-07.4。

实施：非实现作者视角重跑统计/真实进程/exit/schema兼容，新增文件纳入CI触发。

| 检查 | 操作/注入 | 预期结果 |
|---|---|---|
| LOAD-10.1-T01 | 未知optional proto字段 | 旧新兼容 |
| LOAD-10.1-T02 | 丢失事件/invalid schema | 失败可复现 |
| LOAD-10.1-T03 | 关键用例环境跳过 | Blocked非Pass |

通过：集成SHA适用测试真实执行，原断言不删除放宽，跳过清单逐项解释。

执行：OFFLINE、POSTGRES、LIVE、CAPACITY；命令入口：C-PY、C-GODOT、C-DOMAIN、C-SERVER、C-PROTO、C-LIVE、C-AB、C-CAPACITY；关联门：G1、G2、G3、G4。S5：Required，按所列profile取得真实执行证据；历史结果不能冒充当前集成SHA。

交付：`outputs/pr13-acceptance/<integration_sha>/LOAD-10.1/`，包含report/cases/commands/manifest，命令记录退出码及skip；报告填统一证据字段。本轮规格复核记录：NotRevalidated，历史状态仅作来源：InProgress，未签署Accepted；后续真实状态写入对应队列与acceptance_record。

失败：任一必测用例与预期不符为Failed；缺输入/环境/证据为Blocked；仅完成部分层次为Partial，不升级Accepted。 回滚：按任务独立提交回退统计/runner；保留原raw及算法版本，不覆盖已归档报告。

#### LOAD-10.2 真实同账号三局

输入：有界隔离服务与三职业测试账号。进入集成前所需子项：LOAD-05.4、LOAD-09.2。

实施：各职业单账号连续至少三局，再10账号各三局；明确正常/兜底/清理完成。

| 检查 | 操作/注入 | 预期结果 |
|---|---|---|
| LOAD-10.2-T01 | 第二/第三次匹配 | 旧局不污染 |
| LOAD-10.2-T02 | 一局ack超时恢复 | 只计一次 |
| LOAD-10.2-T03 | 兜底弃战 | 单列不算正常击杀 |

通过：每局匹配/settlement/ack可关联且DB资产一次；30局目标缺一正常终态即不能称全通过。

执行：OFFLINE、POSTGRES、LIVE、CAPACITY；命令入口：C-PY、C-GODOT、C-DOMAIN、C-SERVER、C-PROTO、C-LIVE、C-AB、C-CAPACITY；关联门：G1、G2、G3、G4。S5：Required，按所列profile取得真实执行证据；历史结果不能冒充当前集成SHA。

交付：`outputs/pr13-acceptance/<integration_sha>/LOAD-10.2/`，包含report/cases/commands/manifest，命令记录退出码及skip；报告填统一证据字段。本轮规格复核记录：NotRevalidated，历史状态仅作来源：InProgress，未签署Accepted；后续真实状态写入对应队列与acceptance_record。

失败：任一必测用例与预期不符为Failed；缺输入/环境/证据为Blocked；仅完成部分层次为Partial，不升级Accepted。 回滚：按任务独立提交回退统计/runner；保留原raw及算法版本，不覆盖已归档报告。

#### LOAD-10.3 全链路故障用例

输入：ready/HTTP/settlement/runner可控接缝。进入集成前所需子项：LOAD-10.1、LOAD-10.2、LOAD-08.1。

实施：逐用例冻结注入点、预期终态、DB/route后置条件，再在集成SHA运行。

| 检查 | 操作/注入 | 预期结果 |
|---|---|---|
| LOAD-10.3-T01 | accepted后无started | 有界恢复/失败 |
| LOAD-10.3-T02 | ack丢包+重启 | 幂等恢复 |
| LOAD-10.3-T03 | STOP在全部阶段 | 分类/资源/尾事件完整 |

通过：故障矩阵逐行有实际值，组合失败不被正常三局掩盖。

执行：OFFLINE、POSTGRES、LIVE、CAPACITY；命令入口：C-PY、C-GODOT、C-DOMAIN、C-SERVER、C-PROTO、C-LIVE、C-AB、C-CAPACITY；关联门：G1、G2、G3、G4。S5：Required，按所列profile取得真实执行证据；历史结果不能冒充当前集成SHA。

交付：`outputs/pr13-acceptance/<integration_sha>/LOAD-10.3/`，包含report/cases/commands/manifest，命令记录退出码及skip；报告填统一证据字段。本轮规格复核记录：NotRevalidated，历史状态仅作来源：Planned，未签署Accepted；后续真实状态写入对应队列与acceptance_record。

失败：任一必测用例与预期不符为Failed；缺输入/环境/证据为Blocked；仅完成部分层次为Partial，不升级Accepted。 回滚：按任务独立提交回退统计/runner；保留原raw及算法版本，不覆盖已归档报告。

#### LOAD-10.4 同负载性能与保持

输入：原50/120模型、active合同与监控selector。进入集成前所需子项：LOAD-10.3、LOAD-09.3、LOAD-09.4。

实施：单→10→50→100，三轮交错配对，保持期按覆盖率与实际请求率验收。

| 检查 | 操作/注入 | 预期结果 |
|---|---|---|
| LOAD-10.4-T01 | 只峰值100其余50 | 负载合同不通过 |
| LOAD-10.4-T02 | 客户端提前退出使P95下降 | 收益无效 |
| LOAD-10.4-T03 | 默认单IP429 | 限流结果不等同容量 |

通过：有界退出与性能/SLO分别判定，默认限流和临时覆盖结果分列，原停止线保留。

执行：OFFLINE、POSTGRES、LIVE、CAPACITY；命令入口：C-PY、C-GODOT、C-DOMAIN、C-SERVER、C-PROTO、C-LIVE、C-AB、C-CAPACITY；关联门：G1、G2、G3、G4。S5：Required，按所列profile取得真实执行证据；历史结果不能冒充当前集成SHA。

交付：`outputs/pr13-acceptance/<integration_sha>/LOAD-10.4/`，包含report/cases/commands/manifest，命令记录退出码及skip；报告填统一证据字段。本轮规格复核记录：NotRevalidated，历史状态仅作来源：Planned，未签署Accepted；后续真实状态写入对应队列与acceptance_record。

失败：任一必测用例与预期不符为Failed；缺输入/环境/证据为Blocked；仅完成部分层次为Partial，不升级Accepted。 回滚：按任务独立提交回退统计/runner；保留原raw及算法版本，不覆盖已归档报告。

### LOAD-11 来源、CI与最终交付

负责：MAIN。文件：`docs/plans`、`docs/reports`、`.github/workflows`、`tools/pr13_plan.py`。

#### LOAD-11.1 基线来源冻结

输入：release/PR head、dirty、raw清单与工具链。进入集成前所需子项：无；此项为根前置。

实施：分开source checkout、CI checkout、实际运行镜像digest、部署marker、有效配置hash；保存差异。

| 检查 | 操作/注入 | 预期结果 |
|---|---|---|
| LOAD-11.1-T01 | checkout a33f58f/runtime cb96d16 | 分别记录不等同 |
| LOAD-11.1-T02 | 缺raw | 历史归因Blocked而非重跑代替 |
| LOAD-11.1-T03 | SDK缺失 | 阻塞不降target |

通过：baseline可追溯到实际运行内容，缺证据及范围在开工前可见。

执行：OFFLINE、AUDIT；命令入口：C-PLAN、C-CI、C-AUDIT；关联门：G0、G5。S5：Required，按所列profile取得真实执行证据；历史结果不能冒充当前集成SHA。

交付：`outputs/pr13-acceptance/<integration_sha>/LOAD-11.1/`，包含report/cases/commands/manifest，命令记录退出码及skip；报告填统一证据字段。本轮规格复核记录：NotRevalidated，历史状态仅作来源：InProgress，未签署Accepted；后续真实状态写入对应队列与acceptance_record。

失败：任一必测用例与预期不符为Failed；缺输入/环境/证据为Blocked；仅完成部分层次为Partial，不升级Accepted。 回滚：只回退文档/工作流变更，保留历史报告和raw；部署回滚另按运行镜像/配置/DB备份演练。

#### LOAD-11.2 全量manifest脱敏

输入：当前脚本/proto/生成物/raw及未跟踪相关文件。进入集成前所需子项：LOAD-11.1、LOAD-06.4。

实施：记录字节hash、种子/flags/硬件/region/selector，私密原始资料只保存在授权artifact。

| 检查 | 操作/注入 | 预期结果 |
|---|---|---|
| LOAD-11.2-T01 | 同名文件被覆盖 | hash差异拒绝 |
| LOAD-11.2-T02 | 敏感token/密钥 | 公共报告移除 |
| LOAD-11.2-T03 | 原始与派生报告 | 各自hash/父关系明确 |

通过：可重算资料来源完整，Git仅脱敏摘要，历史字节不被新报告覆盖。

执行：OFFLINE、AUDIT；命令入口：C-PLAN、C-CI、C-AUDIT；关联门：G0、G5。S5：Required，按所列profile取得真实执行证据；历史结果不能冒充当前集成SHA。

交付：`outputs/pr13-acceptance/<integration_sha>/LOAD-11.2/`，包含report/cases/commands/manifest，命令记录退出码及skip；报告填统一证据字段。本轮规格复核记录：NotRevalidated，历史状态仅作来源：Planned，未签署Accepted；后续真实状态写入对应队列与acceptance_record。

失败：任一必测用例与预期不符为Failed；缺输入/环境/证据为Blocked；仅完成部分层次为Partial，不升级Accepted。 回滚：只回退文档/工作流变更，保留历史报告和raw；部署回滚另按运行镜像/配置/DB备份演练。

#### LOAD-11.3 可重复CI覆盖

输入：Python/Godot/.NET/PG工作流与路径。进入集成前所需子项：LOAD-11.2、LOAD-10.1。

实施：检查新增文件触发、当前checkoutSHA、真实执行/跳过、日志artifact；非可信PR无生产凭据。

| 检查 | 操作/注入 | 预期结果 |
|---|---|---|
| LOAD-11.3-T01 | 新client测试只改该文件 | 相关CI会触发 |
| LOAD-11.3-T02 | DB矩阵无连接串 | Blocked并列skip |
| LOAD-11.3-T03 | 旧成功run | 只能历史不能新headPass |

通过：适用关键测试非跳过，报告命令/退出码/版本，CI成功不自动推广到未运行场景。

执行：OFFLINE、AUDIT；命令入口：C-PLAN、C-CI、C-AUDIT；关联门：G0、G5。S5：Required，按所列profile取得真实执行证据；历史结果不能冒充当前集成SHA。

交付：`outputs/pr13-acceptance/<integration_sha>/LOAD-11.3/`，包含report/cases/commands/manifest，命令记录退出码及skip；报告填统一证据字段。本轮规格复核记录：NotRevalidated，历史状态仅作来源：InProgress，未签署Accepted；后续真实状态写入对应队列与acceptance_record。

失败：任一必测用例与预期不符为Failed；缺输入/环境/证据为Blocked；仅完成部分层次为Partial，不升级Accepted。 回滚：只回退文档/工作流变更，保留历史报告和raw；部署回滚另按运行镜像/配置/DB备份演练。

#### LOAD-11.4 MAIN交付与回滚

输入：所有LOAD/A/B裁决与G0-G5证据。进入集成前所需子项：PR13-B12.4、PR13-A08.4、PR13-A09.4、PR13-A10.4。

实施：汇总逐项实现/NoChange/Blocked、配置/兼容/风险和演练回滚；保持Draft到人工合并决定。

| 检查 | 操作/注入 | 预期结果 |
|---|---|---|
| LOAD-11.4-T01 | 任一适用门Blocked | 不得PR全部Accepted |
| LOAD-11.4-T02 | 关闭PR但云端仍运行 | 不能声称已回滚 |
| LOAD-11.4-T03 | 回退配置旧room | 沿原policy且资产不倒灌 |

通过：每子项都有有证据裁决，未完清单和默认值真实；代码/配置/数据库回滚分别可执行。

执行：OFFLINE、AUDIT；命令入口：C-PLAN、C-CI、C-AUDIT；关联门：G0、G5。S5：Required，按所列profile取得真实执行证据；历史结果不能冒充当前集成SHA。

交付：`outputs/pr13-acceptance/<integration_sha>/LOAD-11.4/`，包含report/cases/commands/manifest，命令记录退出码及skip；报告填统一证据字段。本轮规格复核记录：NotRevalidated，历史状态仅作来源：Planned，未签署Accepted；后续真实状态写入对应队列与acceptance_record。

失败：任一必测用例与预期不符为Failed；缺输入/环境/证据为Blocked；仅完成部分层次为Partial，不升级Accepted。 回滚：只回退文档/工作流变更，保留历史报告和raw；部署回滚另按运行镜像/配置/DB备份演练。

### PR13-A01 完成次数与历史证据对账

负责：AG-01。文件：`tools/gameplay_load_validation.py`、`tools/gameplay_load_test.py`、`tools/tests`、`docs/plans`、`docs/reports`、`.github/workflows`。

可复用同SHA/profile合格证据：LOAD-03.1、LOAD-03.3、LOAD-03.4、LOAD-11.2；本包新增反例仍需逐条验证。

#### PR13-A01.1 历史raw取证

输入：两套manifest及原report/samples/final/JSONL。进入集成前所需子项：LOAD-03.4、LOAD-11.1。

实施：逐文件核对路径/大小/hash，建立run至代码/镜像/配置关系；缺失原样标注。

| 检查 | 操作/注入 | 预期结果 |
|---|---|---|
| PR13-A01.1-T01 | 文件完整 | 允许派生重算 |
| PR13-A01.1-T02 | hash不匹配 | 隔离该文件并Blocked |
| PR13-A01.1-T03 | 仅有manifest无内容 | 不能宣称已读raw |

通过：2,084项及早期清单全部有存在/匹配/缺失分类，原始文件不改写。

执行：OFFLINE、AUDIT；命令入口：C-PY、C-AUDIT；关联门：G3。S5：Required，按所列profile取得真实执行证据；历史结果不能冒充当前集成SHA。

交付：`outputs/pr13-acceptance/<integration_sha>/PR13-A01.1/`，包含report/cases/commands/manifest，命令记录退出码及skip；报告填统一证据字段。本轮规格复核记录：NotRevalidated，历史状态仅作来源：Queued，未签署Accepted；后续真实状态写入对应队列与acceptance_record。

失败：任一必测用例与预期不符为Failed；缺输入/环境/证据为Blocked；仅完成部分层次为Partial，不升级Accepted。 回滚：按任务独立提交回退统计/runner；保留原raw及算法版本，不覆盖已归档报告。

#### PR13-A01.2 统一三截止点

输入：STOP发出、最后采样、grace结束和event_seq。进入集成前所需子项：PR13-A01.1。

实施：独立算运行期、收尾增量、最终累计；ack与cycle完成分开，兜底分层。

| 检查 | 操作/注入 | 预期结果 |
|---|---|---|
| PR13-A01.2-T01 | ack在STOP后 | 仅收尾计数 |
| PR13-A01.2-T02 | 同事件重复快照 | 一次 |
| PR13-A01.2-T03 | 最后状态cycles增加但无ack证据 | Unknown不补造 |

通过：每cutoff的总ack=逐客户端和=各至少k次人数之和；无法关联事件明确缺证据。

执行：OFFLINE、AUDIT；命令入口：C-PY、C-AUDIT；关联门：G3。S5：Required，按所列profile取得真实执行证据；历史结果不能冒充当前集成SHA。

交付：`outputs/pr13-acceptance/<integration_sha>/PR13-A01.2/`，包含report/cases/commands/manifest，命令记录退出码及skip；报告填统一证据字段。本轮规格复核记录：NotRevalidated，历史状态仅作来源：Queued，未签署Accepted；后续真实状态写入对应队列与acceptance_record。

失败：任一必测用例与预期不符为Failed；缺输入/环境/证据为Blocked；仅完成部分层次为Partial，不升级Accepted。 回滚：按任务独立提交回退统计/runner；保留原raw及算法版本，不覆盖已归档报告。

#### PR13-A01.3 差异逐事件解释

输入：86/至少90、130/至少139及旧52/77记录。进入集成前所需子项：PR13-A01.2。

实施：输出每client/cycle/event的截止点/定义差异，解释报告差额而不直接改成较大值。

| 检查 | 操作/注入 | 预期结果 |
|---|---|---|
| PR13-A01.3-T01 | 同cutoff矛盾fixture | 守恒校验拒绝 |
| PR13-A01.3-T02 | 不同cutoff真实增量 | 差额可逐事件列出 |
| PR13-A01.3-T03 | STOP检查与业务失败 | 52客户端和77检查不同分母 |

通过：两处总数差异和旧失败表均有可审查映射；未能解释则G3仍Blocked。

执行：OFFLINE、AUDIT；命令入口：C-PY、C-AUDIT；关联门：G3。S5：Required，按所列profile取得真实执行证据；历史结果不能冒充当前集成SHA。

交付：`outputs/pr13-acceptance/<integration_sha>/PR13-A01.3/`，包含report/cases/commands/manifest，命令记录退出码及skip；报告填统一证据字段。本轮规格复核记录：NotRevalidated，历史状态仅作来源：Queued，未签署Accepted；后续真实状态写入对应队列与acceptance_record。

失败：任一必测用例与预期不符为Failed；缺输入/环境/证据为Blocked；仅完成部分层次为Partial，不升级Accepted。 回滚：按任务独立提交回退统计/runner；保留原raw及算法版本，不覆盖已归档报告。

#### PR13-A01.4 单来源报告生成

输入：版本化派生模型和原报告immutable备份。进入集成前所需子项：PR13-A01.3。

实施：正文/分布/总表由同一派生数据生成，旧统计与新口径并存；加入守恒回归。

| 检查 | 操作/注入 | 预期结果 |
|---|---|---|
| PR13-A01.4-T01 | 人工改一处总数 | 生成/校验失败 |
| PR13-A01.4-T02 | 重算同raw同版本 | 字节稳定 |
| PR13-A01.4-T03 | 旧算法重放 | 保留旧红线不覆写 |

通过：报告数字不能分散手工维护；所有修正引用run/hash/cutoff和算法版本。

执行：OFFLINE、AUDIT；命令入口：C-PY、C-AUDIT；关联门：G3。S5：Required，按所列profile取得真实执行证据；历史结果不能冒充当前集成SHA。

交付：`outputs/pr13-acceptance/<integration_sha>/PR13-A01.4/`，包含report/cases/commands/manifest，命令记录退出码及skip；报告填统一证据字段。本轮规格复核记录：NotRevalidated，历史状态仅作来源：Queued，未签署Accepted；后续真实状态写入对应队列与acceptance_record。

失败：任一必测用例与预期不符为Failed；缺输入/环境/证据为Blocked；仅完成部分层次为Partial，不升级Accepted。 回滚：按任务独立提交回退统计/runner；保留原raw及算法版本，不覆盖已归档报告。

### PR13-A02 负载合同与STOP后终态

负责：AG-01。文件：`tools/gameplay_load_validation.py`、`tools/gameplay_load_test.py`、`tools/tests`、`client/tests/gameplay_load_client.gd`、`client/state/game_store.gd`、`client/tests`。

可复用同SHA/profile合格证据：LOAD-02.1、LOAD-02.3、LOAD-07.4、LOAD-10.4；本包新增反例仍需逐条验证。

#### PR13-A02.1 负载模型预登记

输入：目标人数、阶段、warmup/hold/drain及采样合同。进入集成前所需子项：LOAD-02.4、LOAD-07.4。

实施：区分循环玩法与固定active-hold，声明online/active目标、覆盖率/连续时长/命令率和gap上限。

| 检查 | 操作/注入 | 预期结果 |
|---|---|---|
| PR13-A02.1-T01 | 100累计登录仅50活跃 | 拒绝100active声明 |
| PR13-A02.1-T02 | 循环结算间隙 | 按预登记模型判不临时改目标 |
| PR13-A02.1-T03 | 采样断档 | Unknown时间不算覆盖 |

通过：合同在运行前hash冻结，测后不能根据结果降低目标；目标与观测用同窗口。

执行：OFFLINE、POSTGRES、CAPACITY；命令入口：C-PY、C-SERVER、C-CAPACITY；关联门：G1、G2、G4。S5：Required，按所列profile取得真实执行证据；历史结果不能冒充当前集成SHA。

交付：`outputs/pr13-acceptance/<integration_sha>/PR13-A02.1/`，包含report/cases/commands/manifest，命令记录退出码及skip；报告填统一证据字段。本轮规格复核记录：NotRevalidated，历史状态仅作来源：Queued，未签署Accepted；后续真实状态写入对应队列与acceptance_record。

失败：任一必测用例与预期不符为Failed；缺输入/环境/证据为Blocked；仅完成部分层次为Partial，不升级Accepted。 回滚：按任务独立提交回退统计/runner；保留原raw及算法版本，不覆盖已归档报告。

#### PR13-A02.2 时间覆盖验收函数

输入：实际monotonic样本与六维判定。进入集成前所需子项：PR13-A02.1。

实施：计算连续满足时长与有效时长覆盖，不用峰值代替保持；缺采样不得默认延用。

| 检查 | 操作/注入 | 预期结果 |
|---|---|---|
| PR13-A02.2-T01 | online100与active100分两窗 | 不算共同达标 |
| PR13-A02.2-T02 | 稳定段半数窗仅50 | 100合同Failed |
| PR13-A02.2-T03 | 间隔超gap | 该时间Unknown且不能拼接连续保持 |

通过：覆盖率分母含全部声明稳定时长，实际负载下降可见；exit0不推出容量通过。

执行：OFFLINE、POSTGRES、CAPACITY；命令入口：C-PY、C-SERVER、C-CAPACITY；关联门：G1、G2、G4。S5：Required，按所列profile取得真实执行证据；历史结果不能冒充当前集成SHA。

交付：`outputs/pr13-acceptance/<integration_sha>/PR13-A02.2/`，包含report/cases/commands/manifest，命令记录退出码及skip；报告填统一证据字段。本轮规格复核记录：NotRevalidated，历史状态仅作来源：Queued，未签署Accepted；后续真实状态写入对应队列与acceptance_record。

失败：任一必测用例与预期不符为Failed；缺输入/环境/证据为Blocked；仅完成部分层次为Partial，不升级Accepted。 回滚：按任务独立提交回退统计/runner；保留原raw及算法版本，不覆盖已归档报告。

#### PR13-A02.3 STOP尾部证据

输入：最后水位、客户端最终schema/退出码和flush。进入集成前所需子项：PR13-A02.2。

实施：grace结束重读所有最终状态与尾事件，累加最终读取错误和STOP后异常。

| 检查 | 操作/注入 | 预期结果 |
|---|---|---|
| PR13-A02.3-T01 | 最终JSON损坏 | InvalidEvidence |
| PR13-A02.3-T02 | STOP后exit7 | cleanup失败 |
| PR13-A02.3-T03 | 尾部缺seq或写失败 | lost保留且不Pass |

通过：最后一窗之后的事件亦守恒，先前错误不被stop_all成功抹去。

执行：OFFLINE、POSTGRES、CAPACITY；命令入口：C-PY、C-SERVER、C-CAPACITY；关联门：G1、G2、G4。S5：Required，按所列profile取得真实执行证据；历史结果不能冒充当前集成SHA。

交付：`outputs/pr13-acceptance/<integration_sha>/PR13-A02.3/`，包含report/cases/commands/manifest，命令记录退出码及skip；报告填统一证据字段。本轮规格复核记录：NotRevalidated，历史状态仅作来源：Queued，未签署Accepted；后续真实状态写入对应队列与acceptance_record。

失败：任一必测用例与预期不符为Failed；缺输入/环境/证据为Blocked；仅完成部分层次为Partial，不升级Accepted。 回滚：按任务独立提交回退统计/runner；保留原raw及算法版本，不覆盖已归档报告。

#### PR13-A02.4 服务端后置清理

输入：ticket/preparation/holds/room route与回收时限。进入集成前所需子项：PR13-A02.3。

实施：grace内查询取消/超时回收和待结算恢复；进程结束与业务资源状态单独签署。

| 检查 | 操作/注入 | 预期结果 |
|---|---|---|
| PR13-A02.4-T01 | 排队STOP | ticket取消或权威时限内回收 |
| PR13-A02.4-T02 | 未ready资产hold | 明确释放机制而非删行 |
| PR13-A02.4-T03 | 未确认receipt | 可恢复且不重复发资产 |

通过：每测试账号有业务后置报告，无route错误残留和无界冻结；无法验证为Blocked。

执行：OFFLINE、POSTGRES、CAPACITY；命令入口：C-PY、C-SERVER、C-CAPACITY；关联门：G1、G2、G4。S5：Required，按所列profile取得真实执行证据；历史结果不能冒充当前集成SHA。

交付：`outputs/pr13-acceptance/<integration_sha>/PR13-A02.4/`，包含report/cases/commands/manifest，命令记录退出码及skip；报告填统一证据字段。本轮规格复核记录：NotRevalidated，历史状态仅作来源：Queued，未签署Accepted；后续真实状态写入对应队列与acceptance_record。

失败：任一必测用例与预期不符为Failed；缺输入/环境/证据为Blocked；仅完成部分层次为Partial，不升级Accepted。 回滚：按任务独立提交回退统计/runner；保留原raw及算法版本，不覆盖已归档报告。

### PR13-A03 结算恢复上下文修复

负责：AG-02。文件：`client/tests/gameplay_load_client.gd`、`client/state/game_store.gd`、`client/tests`。

可复用同SHA/profile合格证据：LOAD-05.1、LOAD-05.2、LOAD-05.4；本包新增反例仍需逐条验证。

#### PR13-A03.1 真实入口反例

输入：_on_event入口、可暂停Bootstrap和match M。进入集成前所需子项：LOAD-05.2。

实施：第一次NOT_IN_ROOM清room，Bootstrap无receipt，再发同错误，然后M就绪；不直接填恢复变量绕入口。

| 检查 | 操作/注入 | 预期结果 |
|---|---|---|
| PR13-A03.1-T01 | 重复同错误 | 恢复ID始终M |
| PR13-A03.1-T02 | Bootstrap晚返回 | 继续按M恢复 |
| PR13-A03.1-T03 | 错误无可验证match | 不能清有效M |

通过：反例先测当前行为并留证；修复只由关联的非空match更新恢复上下文。

执行：OFFLINE、POSTGRES、LIVE；命令入口：C-GODOT、C-SERVER、C-LIVE；关联门：G2。S5：Required，按所列profile取得真实执行证据；历史结果不能冒充当前集成SHA。

交付：`outputs/pr13-acceptance/<integration_sha>/PR13-A03.1/`，包含report/cases/commands/manifest，命令记录退出码及skip；报告填统一证据字段。本轮规格复核记录：NotRevalidated，历史状态仅作来源：Queued，未签署Accepted；后续真实状态写入对应队列与acceptance_record。

失败：任一必测用例与预期不符为Failed；缺输入/环境/证据为Blocked；仅完成部分层次为Partial，不升级Accepted。 回滚：回退客户端状态/流程提交，保留未确认结算上下文；不清空服务器资产或重放游标。

#### PR13-A03.2 旧局回调隔离

输入：session/cycle/match/revision发起上下文。进入集成前所需子项：PR13-A03.1。

实施：HTTP/WS/恢复poll异步沿用context，回调重新核对当前局与恢复目标。

| 检查 | 操作/注入 | 预期结果 |
|---|---|---|
| PR13-A03.2-T01 | M错误在新N房到达 | N不被清 |
| PR13-A03.2-T02 | M的Bootstrap在N到达 | 不覆盖N |
| PR13-A03.2-T03 | session切换 | 不恢复旧账号状态 |

通过：相同session不同cycle也隔离，不能只依赖session_generation。

执行：OFFLINE、POSTGRES、LIVE；命令入口：C-GODOT、C-SERVER、C-LIVE；关联门：G2。S5：Required，按所列profile取得真实执行证据；历史结果不能冒充当前集成SHA。

交付：`outputs/pr13-acceptance/<integration_sha>/PR13-A03.2/`，包含report/cases/commands/manifest，命令记录退出码及skip；报告填统一证据字段。本轮规格复核记录：NotRevalidated，历史状态仅作来源：Queued，未签署Accepted；后续真实状态写入对应队列与acceptance_record。

失败：任一必测用例与预期不符为Failed；缺输入/环境/证据为Blocked；仅完成部分层次为Partial，不升级Accepted。 回滚：回退客户端状态/流程提交，保留未确认结算上下文；不清空服务器资产或重放游标。

#### PR13-A03.3 ack丢响应恢复

输入：ack权威持久化与可控响应丢失。进入集成前所需子项：PR13-A03.2。

实施：超时后查询receipt/ack事实，重试同一幂等操作；UI显示已提交待核实。

| 检查 | 操作/注入 | 预期结果 |
|---|---|---|
| PR13-A03.3-T01 | 已提交响应丢失 | 一次资产且一次完成 |
| PR13-A03.3-T02 | 未提交超时 | 可安全重试 |
| PR13-A03.3-T03 | busy/旧receipt | 不计完成 |

通过：unknown不猜成功，恢复后一个cycle只有一个明确终态。

执行：OFFLINE、POSTGRES、LIVE；命令入口：C-GODOT、C-SERVER、C-LIVE；关联门：G2。S5：Required，按所列profile取得真实执行证据；历史结果不能冒充当前集成SHA。

交付：`outputs/pr13-acceptance/<integration_sha>/PR13-A03.3/`，包含report/cases/commands/manifest，命令记录退出码及skip；报告填统一证据字段。本轮规格复核记录：NotRevalidated，历史状态仅作来源：Queued，未签署Accepted；后续真实状态写入对应队列与acceptance_record。

失败：任一必测用例与预期不符为Failed；缺输入/环境/证据为Blocked；仅完成部分层次为Partial，不升级Accepted。 回滚：回退客户端状态/流程提交，保留未确认结算上下文；不清空服务器资产或重放游标。

#### PR13-A03.4 三局和回归

输入：A03真实入口fixture、pending holds和Godot会话。进入集成前所需子项：PR13-A03.3。

实施：结合重复错误、旧回包、ack失败恢复做同账号三局，核对资产与poll清理。

| 检查 | 操作/注入 | 预期结果 |
|---|---|---|
| PR13-A03.4-T01 | 先M恢复后N开局 | 无M poll污染 |
| PR13-A03.4-T02 | 结算尚未holds ready | 等待不失context |
| PR13-A03.4-T03 | 三局其中重复NOT_IN_ROOM | 仍恰好三次正常ack |

通过：新真实入口反例、既有settlement/play-retry回归和持久资产验证同SHA通过。

执行：OFFLINE、POSTGRES、LIVE；命令入口：C-GODOT、C-SERVER、C-LIVE；关联门：G2。S5：Required，按所列profile取得真实执行证据；历史结果不能冒充当前集成SHA。

交付：`outputs/pr13-acceptance/<integration_sha>/PR13-A03.4/`，包含report/cases/commands/manifest，命令记录退出码及skip；报告填统一证据字段。本轮规格复核记录：NotRevalidated，历史状态仅作来源：Queued，未签署Accepted；后续真实状态写入对应队列与acceptance_record。

失败：任一必测用例与预期不符为Failed；缺输入/环境/证据为Blocked；仅完成部分层次为Partial，不升级Accepted。 回滚：回退客户端状态/流程提交，保留未确认结算上下文；不清空服务器资产或重放游标。

### PR13-A04 ready丢失、乱序和启动故障

负责：AG-02。文件：`client/tests/gameplay_load_client.gd`、`client/state/game_store.gd`、`client/tests`、`server/src/FantasyCard.Server/Matchmaking`、`server/src/FantasyCard.Server/Rooms`、`server/tests/FantasyCard.Server.Tests`。

可复用同SHA/profile合格证据：LOAD-04.1、LOAD-04.2、LOAD-04.3、LOAD-04.4、LOAD-09.2；本包新增反例仍需逐条验证。

#### PR13-A04.1 丢required主动恢复

输入：丢事件接缝与权威ticket。进入集成前所需子项：LOAD-04.4、LOAD-09.2。

实施：无required也有界查询可ready状态，合法确认；定义NOT_FOUND/expired分类。

| 检查 | 操作/注入 | 预期结果 |
|---|---|---|
| PR13-A04.1-T01 | required全丢 | ticket恢复后ready |
| PR13-A04.1-T02 | ticket暂未found | 有限查询后明确终态 |
| PR13-A04.1-T03 | deadline过期 | 不无限等待/发送 |

通过：恢复不受ready_required为true前置卡死，权威15秒/bot填充规则不变。

执行：OFFLINE、POSTGRES、LIVE；命令入口：C-GODOT、C-SERVER、C-LIVE；关联门：G2。S5：Required，按所列profile取得真实执行证据；历史结果不能冒充当前集成SHA。

交付：`outputs/pr13-acceptance/<integration_sha>/PR13-A04.1/`，包含report/cases/commands/manifest，命令记录退出码及skip；报告填统一证据字段。本轮规格复核记录：NotRevalidated，历史状态仅作来源：Queued，未签署Accepted；后续真实状态写入对应队列与acceptance_record。

失败：任一必测用例与预期不符为Failed；缺输入/环境/证据为Blocked；仅完成部分层次为Partial，不升级Accepted。 回滚：回退客户端状态/流程提交，保留未确认结算上下文；不清空服务器资产或重放游标。

#### PR13-A04.2 ready乱序/send失败

输入：found/required/accepted/started可编排流。进入集成前所需子项：PR13-A04.1。

实施：测send=false/重复accepted/accepted后required/旧match；不把本地send当权威成功。

| 检查 | 操作/注入 | 预期结果 |
|---|---|---|
| PR13-A04.2-T01 | send=false两次第三次成功 | 次数有界 |
| PR13-A04.2-T02 | accepted后required | 不回退不重发 |
| PR13-A04.2-T03 | 第二局旧started | 不应用 |

通过：转移日志可重放且每match至多一个启动/ready确认结果。

执行：OFFLINE、POSTGRES、LIVE；命令入口：C-GODOT、C-SERVER、C-LIVE；关联门：G2。S5：Required，按所列profile取得真实执行证据；历史结果不能冒充当前集成SHA。

交付：`outputs/pr13-acceptance/<integration_sha>/PR13-A04.2/`，包含report/cases/commands/manifest，命令记录退出码及skip；报告填统一证据字段。本轮规格复核记录：NotRevalidated，历史状态仅作来源：Queued，未签署Accepted；后续真实状态写入对应队列与acceptance_record。

失败：任一必测用例与预期不符为Failed；缺输入/环境/证据为Blocked；仅完成部分层次为Partial，不升级Accepted。 回滚：回退客户端状态/流程提交，保留未确认结算上下文；不清空服务器资产或重放游标。

#### PR13-A04.3 启动失败与恢复

输入：snapshot/registry/MarkRunning数据库故障点。进入集成前所需子项：PR13-A04.2。

实施：在三处单独失败再重试并重启，验证room唯一、route、hold和ticket终态。

| 检查 | 操作/注入 | 预期结果 |
|---|---|---|
| PR13-A04.3-T01 | 保存失败 | 不提前Running |
| PR13-A04.3-T02 | registry失败后重试 | 同匹配不双房 |
| PR13-A04.3-T03 | MarkRunning丢结果 | 按持久状态恢复 |

通过：不遗留不可恢复Starting，启动/扣资源恰好一次；不是只提高客户端timeout。

执行：OFFLINE、POSTGRES、LIVE；命令入口：C-GODOT、C-SERVER、C-LIVE；关联门：G2。S5：Required，按所列profile取得真实执行证据；历史结果不能冒充当前集成SHA。

交付：`outputs/pr13-acceptance/<integration_sha>/PR13-A04.3/`，包含report/cases/commands/manifest，命令记录退出码及skip；报告填统一证据字段。本轮规格复核记录：NotRevalidated，历史状态仅作来源：Queued，未签署Accepted；后续真实状态写入对应队列与acceptance_record。

失败：任一必测用例与预期不符为Failed；缺输入/环境/证据为Blocked；仅完成部分层次为Partial，不升级Accepted。 回滚：回退客户端状态/流程提交，保留未确认结算上下文；不清空服务器资产或重放游标。

#### PR13-A04.4 多局/STOP组合

输入：真实入口、多客户端与ready阶段STOP。进入集成前所需子项：PR13-A04.3。

实施：合并断线resume、晚通知、第二/第三局和取消，逐账号查后置状态。

| 检查 | 操作/注入 | 预期结果 |
|---|---|---|
| PR13-A04.4-T01 | ready阶段STOP | 取消或明确deadline回收 |
| PR13-A04.4-T02 | reconnect收到重放 | 序号与room正确 |
| PR13-A04.4-T03 | 多局迟到事件 | 只影响原cycle |

通过：每例有客户端终态和服务端DB/route证据，测试不能绕过实际事件入口。

执行：OFFLINE、POSTGRES、LIVE；命令入口：C-GODOT、C-SERVER、C-LIVE；关联门：G2。S5：Required，按所列profile取得真实执行证据；历史结果不能冒充当前集成SHA。

交付：`outputs/pr13-acceptance/<integration_sha>/PR13-A04.4/`，包含report/cases/commands/manifest，命令记录退出码及skip；报告填统一证据字段。本轮规格复核记录：NotRevalidated，历史状态仅作来源：Queued，未签署Accepted；后续真实状态写入对应队列与acceptance_record。

失败：任一必测用例与预期不符为Failed；缺输入/环境/证据为Blocked；仅完成部分层次为Partial，不升级Accepted。 回滚：回退客户端状态/流程提交，保留未确认结算上下文；不清空服务器资产或重放游标。

### PR13-A05 结算持久化、路由和账链

负责：AG-04。文件：`server/src/FantasyCard.Server/Matchmaking`、`server/src/FantasyCard.Server/Rooms`、`server/tests/FantasyCard.Server.Tests`、`server/src/FantasyCard.Server/Settlement`、`server/tests/FantasyCard.Server.Tests/Settlement`。

可复用同SHA/profile合格证据：LOAD-05.4、LOAD-09.2、PR13-B12.2；本包新增反例仍需逐条验证。

#### PR13-A05.1 持久化失败恢复

输入：settlement写入/asset holds故障点。进入集成前所需子项：LOAD-05.4、LOAD-09.2。

实施：提交前/后分别故障，按durable事实决定释放路由和结算可见，不提前成功。

| 检查 | 操作/注入 | 预期结果 |
|---|---|---|
| PR13-A05.1-T01 | 提交前失败 | 无completed/可重试 |
| PR13-A05.1-T02 | 提交后响应丢 | 同receipt恢复不再发资产 |
| PR13-A05.1-T03 | holds延迟 | 未ready不绕过 |

通过：durable settlement、holds、route、玩家下一局权限一致。

执行：OFFLINE、POSTGRES、AUDIT；命令入口：C-SERVER、C-AUDIT；关联门：G2、G5。S5：Required，按所列profile取得真实执行证据；历史结果不能冒充当前集成SHA。

交付：`outputs/pr13-acceptance/<integration_sha>/PR13-A05.1/`，包含report/cases/commands/manifest，命令记录退出码及skip；报告填统一证据字段。本轮规格复核记录：NotRevalidated，历史状态仅作来源：Queued，未签署Accepted；后续真实状态写入对应队列与acceptance_record。

失败：任一必测用例与预期不符为Failed；缺输入/环境/证据为Blocked；仅完成部分层次为Partial，不升级Accepted。 回滚：回退服务代码并复测旧新房间恢复；保留数据库备份/幂等流水，不用删行制造成功。

#### PR13-A05.2 队友和旧房间隔离

输入：玩家A已终态/B仍活动及新房N。进入集成前所需子项：PR13-A05.1。

实施：A进入新局后旧房snapshot继续；旧route删除只在仍指旧room时发生。

| 检查 | 操作/注入 | 预期结果 |
|---|---|---|
| PR13-A05.2-T01 | 旧snapshot继续 | B正常/A的N route不删除 |
| PR13-A05.2-T02 | 恢复terminal A | 不重新占旧route |
| PR13-A05.2-T03 | 相同玩家新route | 旧结算callback无权清 |

通过：A可继续多局、B可完成旧局，旧新room registry与DB关联无污染。

执行：OFFLINE、POSTGRES、AUDIT；命令入口：C-SERVER、C-AUDIT；关联门：G2、G5。S5：Required，按所列profile取得真实执行证据；历史结果不能冒充当前集成SHA。

交付：`outputs/pr13-acceptance/<integration_sha>/PR13-A05.2/`，包含report/cases/commands/manifest，命令记录退出码及skip；报告填统一证据字段。本轮规格复核记录：NotRevalidated，历史状态仅作来源：Queued，未签署Accepted；后续真实状态写入对应队列与acceptance_record。

失败：任一必测用例与预期不符为Failed；缺输入/环境/证据为Blocked；仅完成部分层次为Partial，不升级Accepted。 回滚：回退服务代码并复测旧新房间恢复；保留数据库备份/幂等流水，不用删行制造成功。

#### PR13-A05.3 幂等/重启资产矩阵

输入：一次性PG、ledger/receipt/instance清单。进入集成前所需子项：PR13-A05.2。

实施：重复请求/ack/通知与重启覆盖持久资源，比较金额和实例集合。

| 检查 | 操作/注入 | 预期结果 |
|---|---|---|
| PR13-A05.3-T01 | 同ack三次 | 一条业务结果 |
| PR13-A05.3-T02 | 重启在holds完成前 | 恢复同一资产转移 |
| PR13-A05.3-T03 | 重复ready通知 | 不重复领奖 |

通过：账户/物品实例/流水在允许交易转移后守恒，不删测试数据伪造通过。

执行：OFFLINE、POSTGRES、AUDIT；命令入口：C-SERVER、C-AUDIT；关联门：G2、G5。S5：Required，按所列profile取得真实执行证据；历史结果不能冒充当前集成SHA。

交付：`outputs/pr13-acceptance/<integration_sha>/PR13-A05.3/`，包含report/cases/commands/manifest，命令记录退出码及skip；报告填统一证据字段。本轮规格复核记录：NotRevalidated，历史状态仅作来源：Queued，未签署Accepted；后续真实状态写入对应队列与acceptance_record。

失败：任一必测用例与预期不符为Failed；缺输入/环境/证据为Blocked；仅完成部分层次为Partial，不升级Accepted。 回滚：回退服务代码并复测旧新房间恢复；保留数据库备份/幂等流水，不用删行制造成功。

#### PR13-A05.4 ledgerChainMismatches告警归因

输入：既有告警时间/范围与只读账链权限。进入集成前所需子项：PR13-A05.3。

实施：只读取证定位受影响账户及前后变化，复算链并判既有/测试相关/未定；修数据另起审查。

| 检查 | 操作/注入 | 预期结果 |
|---|---|---|
| PR13-A05.4-T01 | 告警在测试前已存在 | 有历史证据才归既有 |
| PR13-A05.4-T02 | 测试后新差异 | 阻塞资产验收 |
| PR13-A05.4-T03 | 无权限或链条缺失 | Blocked不写无影响 |

通过：给独立有证据结论；未知风险不由压测exit0覆盖，不自动修余额或删流水。

执行：OFFLINE、POSTGRES、AUDIT；命令入口：C-SERVER、C-AUDIT；关联门：G2、G5。S5：Required，按所列profile取得真实执行证据；历史结果不能冒充当前集成SHA。

交付：`outputs/pr13-acceptance/<integration_sha>/PR13-A05.4/`，包含report/cases/commands/manifest，命令记录退出码及skip；报告填统一证据字段。本轮规格复核记录：NotRevalidated，历史状态仅作来源：Queued，未签署Accepted；后续真实状态写入对应队列与acceptance_record。

失败：任一必测用例与预期不符为Failed；缺输入/环境/证据为Blocked；仅完成部分层次为Partial，不升级Accepted。 回滚：回退服务代码并复测旧新房间恢复；保留数据库备份/幂等流水，不用删行制造成功。

### PR13-A06 HTTP响应边界与遥测

负责：AG-03。文件：`client/network/gateway.gd`、`client/network/reusable_http_client.gd`、`client/tests`、`tools/tests`。

可复用同SHA/profile合格证据：LOAD-06.1、LOAD-08.1、LOAD-08.3；本包新增反例仍需逐条验证。

#### PR13-A06.1 响应完整性fixture

输入：可控本地HTTP/TLS/chunked服务。进入集成前所需子项：LOAD-06.1、LOAD-08.1。

实施：按协议判断body完整结束；合法close与截断区分，保留大小/超时保护。

| 检查 | 操作/注入 | 预期结果 |
|---|---|---|
| PR13-A06.1-T01 | 完整Content-Length后close | success |
| PR13-A06.1-T02 | 少字节/截断chunk | 失败 |
| PR13-A06.1-T03 | 超2MiB/非法压缩 | 拒绝无部分成功 |

通过：连接状态不独自决定成功；测试记录真实字节/分帧与transport结果。

执行：OFFLINE、EXPERIMENT；命令入口：C-GODOT、C-AB；关联门：G1、G3、G4。S5：Required，按所列profile取得真实执行证据；历史结果不能冒充当前集成SHA。

交付：`outputs/pr13-acceptance/<integration_sha>/PR13-A06.1/`，包含report/cases/commands/manifest，命令记录退出码及skip；报告填统一证据字段。本轮规格复核记录：NotRevalidated，历史状态仅作来源：Queued，未签署Accepted；后续真实状态写入对应队列与acceptance_record。

失败：任一必测用例与预期不符为Failed；缺输入/环境/证据为Blocked；仅完成部分层次为Partial，不升级Accepted。 回滚：回退客户端状态/流程提交，保留未确认结算上下文；不清空服务器资产或重放游标。

#### PR13-A06.2 连接失效/并发/会话

输入：真实引擎连接和origin/session切换。进入集成前所需子项：PR13-A06.1。

实施：空闲close下一请求重连、重叠走fallback，generation变化取消并阻旧响应。

| 检查 | 操作/注入 | 预期结果 |
|---|---|---|
| PR13-A06.2-T01 | 空闲断开 | 有界重连同logicalID |
| PR13-A06.2-T02 | overlap两个请求 | 正确各自body |
| PR13-A06.2-T03 | 新session/token | 不泄漏旧结果/headers |

通过：不支持的并发不压到单HTTPClient，TLS失败不退化为不校验。

执行：OFFLINE、EXPERIMENT；命令入口：C-GODOT、C-AB；关联门：G1、G3、G4。S5：Required，按所列profile取得真实执行证据；历史结果不能冒充当前集成SHA。

交付：`outputs/pr13-acceptance/<integration_sha>/PR13-A06.2/`，包含report/cases/commands/manifest，命令记录退出码及skip；报告填统一证据字段。本轮规格复核记录：NotRevalidated，历史状态仅作来源：Queued，未签署Accepted；后续真实状态写入对应队列与acceptance_record。

失败：任一必测用例与预期不符为Failed；缺输入/环境/证据为Blocked；仅完成部分层次为Partial，不升级Accepted。 回滚：回退客户端状态/流程提交，保留未确认结算上下文；不清空服务器资产或重放游标。

#### PR13-A06.3 请求开始context

输入：Gateway与load telemetry异步上下文。进入集成前所需子项：PR13-A06.2。

实施：发起时冻结run/client/cycle/match/phase/logicalID，attempt及终态沿用。

| 检查 | 操作/注入 | 预期结果 |
|---|---|---|
| PR13-A06.3-T01 | cycle1请求cycle2回包 | 标cycle1 |
| PR13-A06.3-T02 | retry期间stage改变 | 仍原phase |
| PR13-A06.3-T03 | STOP后迟到response | 归drain且保原业务context |

通过：每请求可对账，缺上下文标Unknown不冒名贴当前cycle。

执行：OFFLINE、EXPERIMENT；命令入口：C-GODOT、C-AB；关联门：G1、G3、G4。S5：Required，按所列profile取得真实执行证据；历史结果不能冒充当前集成SHA。

交付：`outputs/pr13-acceptance/<integration_sha>/PR13-A06.3/`，包含report/cases/commands/manifest，命令记录退出码及skip；报告填统一证据字段。本轮规格复核记录：NotRevalidated，历史状态仅作来源：Queued，未签署Accepted；后续真实状态写入对应队列与acceptance_record。

失败：任一必测用例与预期不符为Failed；缺输入/环境/证据为Blocked；仅完成部分层次为Partial，不升级Accepted。 回滚：回退客户端状态/流程提交，保留未确认结算上下文；不清空服务器资产或重放游标。

#### PR13-A06.4 边界与收益复验

输入：fixture全集与同接口配对样本。进入集成前所需子项：PR13-A06.3。

实施：先全部边界通过，再三轮固定请求组合A/B；报告成功/失败/pending及实际复用率。

| 检查 | 操作/注入 | 预期结果 |
|---|---|---|
| PR13-A06.4-T01 | 只成功请求P95改善但失败上升 | 候选不通过 |
| PR13-A06.4-T02 | 字节/组合不同 | 诊断而非因果 |
| PR13-A06.4-T03 | 同组合三轮 | 差异区间可重算 |

通过：正确性零退化，收益与负载同口径；无收益候选可回退现行并有NoChange证据。

执行：OFFLINE、EXPERIMENT；命令入口：C-GODOT、C-AB；关联门：G1、G3、G4。S5：Required，按所列profile取得真实执行证据；历史结果不能冒充当前集成SHA。

交付：`outputs/pr13-acceptance/<integration_sha>/PR13-A06.4/`，包含report/cases/commands/manifest，命令记录退出码及skip；报告填统一证据字段。本轮规格复核记录：NotRevalidated，历史状态仅作来源：Queued，未签署Accepted；后续真实状态写入对应队列与acceptance_record。

失败：任一必测用例与预期不符为Failed；缺输入/环境/证据为Blocked；仅完成部分层次为Partial，不升级Accepted。 回滚：回退客户端状态/流程提交，保留未确认结算上下文；不清空服务器资产或重放游标。

### PR13-A07 当前合同CI与真实数据库覆盖

负责：MAIN。文件：`docs/plans`、`docs/reports`、`.github/workflows`、`server/tests`、`client/tests`、`tools/tests`。

可复用同SHA/profile合格证据：LOAD-10.1、LOAD-11.3、PR13-B02.1；本包新增反例仍需逐条验证。

#### PR13-A07.1 旧数值合同定位

输入：编译日志及当前策略API。进入集成前所需子项：LOAD-10.1。

实施：复现旧布尔/余量成员错误，列每断言迁移映射给B02；不恢复废弃参数。

| 检查 | 操作/注入 | 预期结果 |
|---|---|---|
| PR13-A07.1-T01 | useConsumptionBasedFenxian | 映射现有枚举 |
| PR13-A07.1-T02 | 余量旧属性 | 现有GuardianShieldRemainderTenths |
| PR13-A07.1-T03 | 默认断言误用候选 | 默认/candidate分离 |

通过：每编译错误有当前合同去向，无删测试/禁分析器/改默认迎合断言。

执行：OFFLINE、POSTGRES；命令入口：C-BUILD、C-DOMAIN、C-SERVER、C-GODOT、C-CI；关联门：G1、G2、G5。S5：NotApplicableWithReason，仅凭指定离线/集成产物即可判定本子项；公网压测不增加该判据可信度。

交付：`outputs/pr13-acceptance/<integration_sha>/PR13-A07.1/`，包含report/cases/commands/manifest，命令记录退出码及skip；报告填统一证据字段。本轮规格复核记录：NotRevalidated，历史状态仅作来源：Queued，未签署Accepted；后续真实状态写入对应队列与acceptance_record。

失败：任一必测用例与预期不符为Failed；缺输入/环境/证据为Blocked；仅完成部分层次为Partial，不升级Accepted。 回滚：回退服务代码并复测旧新房间恢复；保留数据库备份/幂等流水，不用删行制造成功。

#### PR13-A07.2 全PG关键矩阵

输入：一次性数据库版本与可用集成用例表。进入集成前所需子项：PR13-A07.1。

实施：执行完整适用Server测试；关键settlement/asset/route/restart/replay用例不用单个filter替代。

| 检查 | 操作/注入 | 预期结果 |
|---|---|---|
| PR13-A07.2-T01 | 仅匹配1项通过 | 结算矩阵仍Pending |
| PR13-A07.2-T02 | 关键DB用例Skip | Blocked |
| PR13-A07.2-T03 | 错误生产连接 | 运行前拒绝 |

通过：关键用例actual executed且无环境性跳过，PG版本与迁移log齐全。

执行：OFFLINE、POSTGRES；命令入口：C-BUILD、C-DOMAIN、C-SERVER、C-GODOT、C-CI；关联门：G1、G2、G5。S5：NotApplicableWithReason，仅凭指定离线/集成产物即可判定本子项；公网压测不增加该判据可信度。

交付：`outputs/pr13-acceptance/<integration_sha>/PR13-A07.2/`，包含report/cases/commands/manifest，命令记录退出码及skip；报告填统一证据字段。本轮规格复核记录：NotRevalidated，历史状态仅作来源：Queued，未签署Accepted；后续真实状态写入对应队列与acceptance_record。

失败：任一必测用例与预期不符为Failed；缺输入/环境/证据为Blocked；仅完成部分层次为Partial，不升级Accepted。 回滚：回退服务代码并复测旧新房间恢复；保留数据库备份/幂等流水，不用删行制造成功。

#### PR13-A07.3 CI触发和证据

输入：workflows路径/checkoutSHA与新增fixture。进入集成前所需子项：PR13-A07.2。

实施：覆盖所有新增测试/helper路径，上传TRX/日志/skip/版本；离线网络隔离。

| 检查 | 操作/注入 | 预期结果 |
|---|---|---|
| PR13-A07.3-T01 | 仅改新ready测试 | 应触发相关工作流 |
| PR13-A07.3-T02 | fork PR | 无生产凭据/动作 |
| PR13-A07.3-T03 | job exit0但用例缺失 | 覆盖验收失败 |

通过：能证明哪些用例在当前SHA运行，不能只用工作流绿色徽标替代清单。

执行：OFFLINE、POSTGRES；命令入口：C-BUILD、C-DOMAIN、C-SERVER、C-GODOT、C-CI；关联门：G1、G2、G5。S5：NotApplicableWithReason，仅凭指定离线/集成产物即可判定本子项；公网压测不增加该判据可信度。

交付：`outputs/pr13-acceptance/<integration_sha>/PR13-A07.3/`，包含report/cases/commands/manifest，命令记录退出码及skip；报告填统一证据字段。本轮规格复核记录：NotRevalidated，历史状态仅作来源：Queued，未签署Accepted；后续真实状态写入对应队列与acceptance_record。

失败：任一必测用例与预期不符为Failed；缺输入/环境/证据为Blocked；仅完成部分层次为Partial，不升级Accepted。 回滚：回退服务代码并复测旧新房间恢复；保留数据库备份/幂等流水，不用删行制造成功。

#### PR13-A07.4 MAIN复跑适用套件

输入：B02合同修复与PG/offline结果。进入集成前所需子项：PR13-A07.3、PR13-B02.4。

实施：MAIN固定SHA重跑关键回归并核对计数/skip/artifact，独立Numerical和load均记录。

| 检查 | 操作/注入 | 预期结果 |
|---|---|---|
| PR13-A07.4-T01 | 专用load成功但Numerical失败 | G1/G2不全Pass |
| PR13-A07.4-T02 | 基线编译已失败 | 仍阻塞当前完整回归 |
| PR13-A07.4-T03 | 新head沿用旧CI | 拒绝 |

通过：同一集成SHA全部适用门具真实证据，跳过清单和失败原因逐项可追踪。

执行：OFFLINE、POSTGRES；命令入口：C-BUILD、C-DOMAIN、C-SERVER、C-GODOT、C-CI；关联门：G1、G2、G5。S5：NotApplicableWithReason，仅凭指定离线/集成产物即可判定本子项；公网压测不增加该判据可信度。

交付：`outputs/pr13-acceptance/<integration_sha>/PR13-A07.4/`，包含report/cases/commands/manifest，命令记录退出码及skip；报告填统一证据字段。本轮规格复核记录：NotRevalidated，历史状态仅作来源：Queued，未签署Accepted；后续真实状态写入对应队列与acceptance_record。

失败：任一必测用例与预期不符为Failed；缺输入/环境/证据为Blocked；仅完成部分层次为Partial，不升级Accepted。 回滚：回退服务代码并复测旧新房间恢复；保留数据库备份/幂等流水，不用删行制造成功。

### PR13-A08 来源、当前状态与回滚

负责：MAIN。文件：`docs/plans`、`docs/reports`、`.github/workflows`、`server/deploy`。

可复用同SHA/profile合格证据：LOAD-11.1、LOAD-11.2、LOAD-11.4、PR13-B12.3；本包新增反例仍需逐条验证。

#### PR13-A08.1 运行来源与历史基线

输入：实际镜像digest/构建源/checkout/marker/config。进入集成前所需子项：LOAD-11.1。

实施：区分cb96d16构建与a33f58f仅checkout；记当前head与历史run来源，无法读取写missing。

| 检查 | 操作/注入 | 预期结果 |
|---|---|---|
| PR13-A08.1-T01 | marker先进但未rebuild | 不写新镜像已运行 |
| PR13-A08.1-T02 | dirty补丁 | 单独hash来源 |
| PR13-A08.1-T03 | 配置包同名不同hash | 阻塞比较 |

通过：每历史与新run有完整source/config/image关系，不靠部署marker替代内容证据。

执行：OFFLINE、POSTGRES、AUDIT；命令入口：C-PLAN、C-SERVER、C-AUDIT；关联门：G0、G5。S5：Required，按所列profile取得真实执行证据；历史结果不能冒充当前集成SHA。

交付：`outputs/pr13-acceptance/<integration_sha>/PR13-A08.1/`，包含report/cases/commands/manifest，命令记录退出码及skip；报告填统一证据字段。本轮规格复核记录：NotRevalidated，历史状态仅作来源：Queued，未签署Accepted；后续真实状态写入对应队列与acceptance_record。

失败：任一必测用例与预期不符为Failed；缺输入/环境/证据为Blocked；仅完成部分层次为Partial，不升级Accepted。 回滚：回退服务代码并复测旧新房间恢复；保留数据库备份/幂等流水，不用删行制造成功。

#### PR13-A08.2 任务状态同步

输入：原LOAD状态、A/B队列和当前验证覆盖。进入集成前所需子项：PR13-A08.1。

实施：每项分别记录实现存在/历史测试/当前复验/可验收；对账差异加入阻塞非覆盖历史。

| 检查 | 操作/注入 | 预期结果 |
|---|---|---|
| PR13-A08.2-T01 | 旧191/62 | 历史执行/skip分类 |
| PR13-A08.2-T02 | 新48项Queued | 不升级Pass |
| PR13-A08.2-T03 | 130差异未解 | 数字保留但结论受限 |

通过：状态与当前证据一致，规范Ready和运行Accepted分开。

执行：OFFLINE、POSTGRES、AUDIT；命令入口：C-PLAN、C-SERVER、C-AUDIT；关联门：G0、G5。S5：Required，按所列profile取得真实执行证据；历史结果不能冒充当前集成SHA。

交付：`outputs/pr13-acceptance/<integration_sha>/PR13-A08.2/`，包含report/cases/commands/manifest，命令记录退出码及skip；报告填统一证据字段。本轮规格复核记录：NotRevalidated，历史状态仅作来源：Queued，未签署Accepted；后续真实状态写入对应队列与acceptance_record。

失败：任一必测用例与预期不符为Failed；缺输入/环境/证据为Blocked；仅完成部分层次为Partial，不升级Accepted。 回滚：回退服务代码并复测旧新房间恢复；保留数据库备份/幂等流水，不用删行制造成功。

#### PR13-A08.3 隔离回滚演练

输入：原服务镜像/配置/测试数据库备份及旧新房间。进入集成前所需子项：PR13-A08.2。

实施：在隔离实例恢复旧镜像/配置，验证健康/房间/receipt；DB迁移单独预演。

| 检查 | 操作/注入 | 预期结果 |
|---|---|---|
| PR13-A08.3-T01 | 代码回滚 | 旧当前room可处理或兼容限制明确 |
| PR13-A08.3-T02 | config回滚 | 新room用旧、旧room锁定 |
| PR13-A08.3-T03 | DB恢复 | 资产不逆向复制 |

通过：三类回滚分别有真实日志与适用边界，生产备份不是演练通过本身。

执行：OFFLINE、POSTGRES、AUDIT；命令入口：C-PLAN、C-SERVER、C-AUDIT；关联门：G0、G5。S5：Required，按所列profile取得真实执行证据；历史结果不能冒充当前集成SHA。

交付：`outputs/pr13-acceptance/<integration_sha>/PR13-A08.3/`，包含report/cases/commands/manifest，命令记录退出码及skip；报告填统一证据字段。本轮规格复核记录：NotRevalidated，历史状态仅作来源：Queued，未签署Accepted；后续真实状态写入对应队列与acceptance_record。

失败：任一必测用例与预期不符为Failed；缺输入/环境/证据为Blocked；仅完成部分层次为Partial，不升级Accepted。 回滚：回退服务代码并复测旧新房间恢复；保留数据库备份/幂等流水，不用删行制造成功。

#### PR13-A08.4 交付来源与未完清单

输入：当前裁决及回滚artifact。进入集成前所需子项：PR13-A08.3、PR13-B12.4。

实施：更新PR/报告/状态一致，记录暂存旧云端补丁、备份和临时范围；未验证线上状态标历史。

| 检查 | 操作/注入 | 预期结果 |
|---|---|---|
| PR13-A08.4-T01 | 原env恢复hash记录 | 仅证明当次恢复 |
| PR13-A08.4-T02 | 本次未health check | 不写现在健康 |
| PR13-A08.4-T03 | 未验收项存在 | PR Draft且清单非空 |

通过：文档事实与版本可核对，未合并/未启用不伪称上线完成。

执行：OFFLINE、POSTGRES、AUDIT；命令入口：C-PLAN、C-SERVER、C-AUDIT；关联门：G0、G5。S5：Required，按所列profile取得真实执行证据；历史结果不能冒充当前集成SHA。

交付：`outputs/pr13-acceptance/<integration_sha>/PR13-A08.4/`，包含report/cases/commands/manifest，命令记录退出码及skip；报告填统一证据字段。本轮规格复核记录：NotRevalidated，历史状态仅作来源：Queued，未签署Accepted；后续真实状态写入对应队列与acceptance_record。

失败：任一必测用例与预期不符为Failed；缺输入/环境/证据为Blocked；仅完成部分层次为Partial，不升级Accepted。 回滚：回退服务代码并复测旧新房间恢复；保留数据库备份/幂等流水，不用删行制造成功。

### PR13-A09 独立多局、故障和资产验收

负责：AG-06。文件：`docs/plans`、`docs/reports`、`.github/workflows`、`client/tests`、`tools/tests`、`server/tests`。

可复用同SHA/profile合格证据：LOAD-10.2、LOAD-10.3、PR13-B11.4、PR13-B12.2；本包新增反例仍需逐条验证。

#### PR13-A09.1 固定集成验收输入

输入：immutable SHA、case清单、effective policies。进入集成前所需子项：PR13-A03.4、PR13-A04.4、PR13-A05.3、PR13-A06.4、PR13-A07.4。

实施：测前冻结输入与必跑用例，独立设计反例；每run只验一个确切集成版本。

| 检查 | 操作/注入 | 预期结果 |
|---|---|---|
| PR13-A09.1-T01 | 实现者改head中途 | 原证据只归旧SHA |
| PR13-A09.1-T02 | fixture改后 | 重新hash对应用例 |
| PR13-A09.1-T03 | 运行ID缺失 | 不伪填agentID |

通过：所有证据有同一集成来源和执行身份，静态自述不能代替运行。

执行：OFFLINE、POSTGRES、LIVE、RENDER；命令入口：C-GODOT、C-SERVER、C-LIVE、C-RENDER；关联门：G2、G5。S5：Required，按所列profile取得真实执行证据；历史结果不能冒充当前集成SHA。

交付：`outputs/pr13-acceptance/<integration_sha>/PR13-A09.1/`，包含report/cases/commands/manifest，命令记录退出码及skip；报告填统一证据字段。本轮规格复核记录：NotRevalidated，历史状态仅作来源：Queued，未签署Accepted；后续真实状态写入对应队列与acceptance_record。

失败：任一必测用例与预期不符为Failed；缺输入/环境/证据为Blocked；仅完成部分层次为Partial，不升级Accepted。 回滚：回退客户端状态/流程提交，保留未确认结算上下文；不清空服务器资产或重放游标。

#### PR13-A09.2 多账号正常三局

输入：三职业单号、10账号各三局及明确结果口径。进入集成前所需子项：PR13-A09.1。

实施：headless流程和rendered操作分别跑，正常完成/撤离/死亡/兜底/drain分列。

| 检查 | 操作/注入 | 预期结果 |
|---|---|---|
| PR13-A09.2-T01 | 三局第二局旧事件 | 不污染 |
| PR13-A09.2-T02 | 10号30cycle一局Unknown | 不能全通过 |
| PR13-A09.2-T03 | 自动弃战 | 不归正常击杀 |

通过：同match ack/DB实例/终态可关联，玩法可恢复且统计守恒。

执行：OFFLINE、POSTGRES、LIVE、RENDER；命令入口：C-GODOT、C-SERVER、C-LIVE、C-RENDER；关联门：G2、G5。S5：Required，按所列profile取得真实执行证据；历史结果不能冒充当前集成SHA。

交付：`outputs/pr13-acceptance/<integration_sha>/PR13-A09.2/`，包含report/cases/commands/manifest，命令记录退出码及skip；报告填统一证据字段。本轮规格复核记录：NotRevalidated，历史状态仅作来源：Queued，未签署Accepted；后续真实状态写入对应队列与acceptance_record。

失败：任一必测用例与预期不符为Failed；缺输入/环境/证据为Blocked；仅完成部分层次为Partial，不升级Accepted。 回滚：回退客户端状态/流程提交，保留未确认结算上下文；不清空服务器资产或重放游标。

#### PR13-A09.3 全故障与资产后置

输入：A02-A06用例和真实入口/PG接缝。进入集成前所需子项：PR13-A09.2。

实施：注入丢失/乱序/超时/重启/STOP，记录客户端DB/route/holds四方实际状态。

| 检查 | 操作/注入 | 预期结果 |
|---|---|---|
| PR13-A09.3-T01 | ack丢包再重启 | 一次资源 |
| PR13-A09.3-T02 | 旧room持续snapshot | 新route不删 |
| PR13-A09.3-T03 | 最终坏状态 | InvalidEvidence而非正常清理 |

通过：每必测行有injection/expected/actual/exit/hash，关键故障无跳过。

执行：OFFLINE、POSTGRES、LIVE、RENDER；命令入口：C-GODOT、C-SERVER、C-LIVE、C-RENDER；关联门：G2、G5。S5：Required，按所列profile取得真实执行证据；历史结果不能冒充当前集成SHA。

交付：`outputs/pr13-acceptance/<integration_sha>/PR13-A09.3/`，包含report/cases/commands/manifest，命令记录退出码及skip；报告填统一证据字段。本轮规格复核记录：NotRevalidated，历史状态仅作来源：Queued，未签署Accepted；后续真实状态写入对应队列与acceptance_record。

失败：任一必测用例与预期不符为Failed；缺输入/环境/证据为Blocked；仅完成部分层次为Partial，不升级Accepted。 回滚：回退客户端状态/流程提交，保留未确认结算上下文；不清空服务器资产或重放游标。

#### PR13-A09.4 独立裁决反馈

输入：当前case结果与失败最小复现。进入集成前所需子项：PR13-A09.3。

实施：失败回对应owner保留seed/context；MAIN重跑关键用例，正确性后才允许扩大负载。

| 检查 | 操作/注入 | 预期结果 |
|---|---|---|
| PR13-A09.4-T01 | 单纯脚本成功但UI按钮不可用 | render验收Failed |
| PR13-A09.4-T02 | DB未跑 | Blocked |
| PR13-A09.4-T03 | 重新修复head | 相关证据重取 |

通过：不把QA自述自动当MAIN Accepted，结果引用完整report/artifact。

执行：OFFLINE、POSTGRES、LIVE、RENDER；命令入口：C-GODOT、C-SERVER、C-LIVE、C-RENDER；关联门：G2、G5。S5：Required，按所列profile取得真实执行证据；历史结果不能冒充当前集成SHA。

交付：`outputs/pr13-acceptance/<integration_sha>/PR13-A09.4/`，包含report/cases/commands/manifest，命令记录退出码及skip；报告填统一证据字段。本轮规格复核记录：NotRevalidated，历史状态仅作来源：Queued，未签署Accepted；后续真实状态写入对应队列与acceptance_record。

失败：任一必测用例与预期不符为Failed；缺输入/环境/证据为Blocked；仅完成部分层次为Partial，不升级Accepted。 回滚：回退客户端状态/流程提交，保留未确认结算上下文；不清空服务器资产或重放游标。

### PR13-A10 受控A/B、默认限流和长稳

负责：AG-06。文件：`tools/gameplay_load_validation.py`、`tools/gameplay_load_test.py`、`tools/tests`、`docs/plans`、`docs/reports`、`.github/workflows`。

可复用同SHA/profile合格证据：LOAD-10.4、LOAD-08.1、PR13-B03.4；本包新增反例仍需逐条验证。

#### PR13-A10.1 三组成对A/B预登记

输入：同服务资源/config/玩法/请求集合/种子/统计版本。进入集成前所需子项：PR13-A09.4、PR13-A02.4、PR13-A01.4。

实施：AB/BA顺序交错至少三对，固定warmup/hold/drain/拒绝标准；收益目标先冻结。

| 检查 | 操作/注入 | 预期结果 |
|---|---|---|
| PR13-A10.1-T01 | 两方案请求集合变动 | 只诊断不能因果 |
| PR13-A10.1-T02 | 策略改短战 | 归新玩法profile |
| PR13-A10.1-T03 | 默认限流与临时覆盖 | 分开组 |

通过：三对均有实际负载和完整结果，不能选择性删红线/失败配对。

执行：OFFLINE、CAPACITY；命令入口：C-AB、C-CAPACITY；关联门：G4。S5：Required，按所列profile取得真实执行证据；历史结果不能冒充当前集成SHA。

交付：`outputs/pr13-acceptance/<integration_sha>/PR13-A10.1/`，包含report/cases/commands/manifest，命令记录退出码及skip；报告填统一证据字段。本轮规格复核记录：NotRevalidated，历史状态仅作来源：Queued，未签署Accepted；后续真实状态写入对应队列与acceptance_record。

失败：任一必测用例与预期不符为Failed；缺输入/环境/证据为Blocked；仅完成部分层次为Partial，不升级Accepted。 回滚：按任务独立提交回退统计/runner；保留原raw及算法版本，不覆盖已归档报告。

#### PR13-A10.2 默认限流建立负载

输入：默认10/30/120与每IP请求预算。进入集成前所需子项：PR13-A10.1。

实施：合法多发压源或预登录/渐进启动，记录各IP持续写/读率；无法建立目标直接Blocked。

| 检查 | 操作/注入 | 预期结果 |
|---|---|---|
| PR13-A10.2-T01 | 单IP auth429 | 限流生效单列 |
| PR13-A10.2-T02 | 预登录仍写超限 | 不能宣称容量失败/通过 |
| PR13-A10.2-T03 | 目标online/active持续不足 | load contract Failed |

通过：默认限流保持，50/100各独立声明目标与覆盖；临时覆盖不替代默认容量。

执行：OFFLINE、CAPACITY；命令入口：C-AB、C-CAPACITY；关联门：G4。S5：Required，按所列profile取得真实执行证据；历史结果不能冒充当前集成SHA。

交付：`outputs/pr13-acceptance/<integration_sha>/PR13-A10.2/`，包含report/cases/commands/manifest，命令记录退出码及skip；报告填统一证据字段。本轮规格复核记录：NotRevalidated，历史状态仅作来源：Queued，未签署Accepted；后续真实状态写入对应队列与acceptance_record。

失败：任一必测用例与预期不符为Failed；缺输入/环境/证据为Blocked；仅完成部分层次为Partial，不升级Accepted。 回滚：按任务独立提交回退统计/runner；保留原raw及算法版本，不覆盖已归档报告。

#### PR13-A10.3 长期资源回收

输入：稳定段合同、容器/进程/DB/route/hold基线。进入集成前所需子项：PR13-A10.2。

实施：先30分钟稳定观察再明确预算的浸泡；资源斜率/GC后水位/每已完成局回收及drain核查。

| 检查 | 操作/注入 | 预期结果 |
|---|---|---|
| PR13-A10.3-T01 | RSS持续增长 | 保留斜率和分配证据 |
| PR13-A10.3-T02 | STOP后route/hold未归预期 | cleanup不通过 |
| PR13-A10.3-T03 | 监控断档 | 稳定结果Unknown |

通过：无未解释单调资源增长或业务遗留；时长/目标预登记，30分钟不冒称无限稳定。

执行：OFFLINE、CAPACITY；命令入口：C-AB、C-CAPACITY；关联门：G4。S5：Required，按所列profile取得真实执行证据；历史结果不能冒充当前集成SHA。

交付：`outputs/pr13-acceptance/<integration_sha>/PR13-A10.3/`，包含report/cases/commands/manifest，命令记录退出码及skip；报告填统一证据字段。本轮规格复核记录：NotRevalidated，历史状态仅作来源：Queued，未签署Accepted；后续真实状态写入对应队列与acceptance_record。

失败：任一必测用例与预期不符为Failed；缺输入/环境/证据为Blocked；仅完成部分层次为Partial，不升级Accepted。 回滚：按任务独立提交回退统计/runner；保留原raw及算法版本，不覆盖已归档报告。

#### PR13-A10.4 性能收益和容量裁决

输入：同负载配对差异区间/覆盖率/原停止线。进入集成前所需子项：PR13-A10.3。

实施：原性能红线与正式预登记SLO独立；timeout/pending和失败率一起评估，给benefit/nochange/blocked结论。

| 检查 | 操作/注入 | 预期结果 |
|---|---|---|
| PR13-A10.4-T01 | P95下降但请求率下跌 | 不接受收益 |
| PR13-A10.4-T02 | N不足 | Unknown非达标 |
| PR13-A10.4-T03 | 无收益且正确 | 可签NoChangeWithEvidence |

通过：G4分别给传输收益/原profile容量/候选玩法结果，不用单个exit0代替所有结论。

执行：OFFLINE、CAPACITY；命令入口：C-AB、C-CAPACITY；关联门：G4。S5：Required，按所列profile取得真实执行证据；历史结果不能冒充当前集成SHA。

交付：`outputs/pr13-acceptance/<integration_sha>/PR13-A10.4/`，包含report/cases/commands/manifest，命令记录退出码及skip；报告填统一证据字段。本轮规格复核记录：NotRevalidated，历史状态仅作来源：Queued，未签署Accepted；后续真实状态写入对应队列与acceptance_record。

失败：任一必测用例与预期不符为Failed；缺输入/环境/证据为Blocked；仅完成部分层次为Partial，不升级Accepted。 回滚：按任务独立提交回退统计/runner；保留原raw及算法版本，不覆盖已归档报告。

### PR13-B01 战斗停滞归因与体验指标

负责：AG-01。文件：`tools/gameplay_load_validation.py`、`tools/gameplay_load_test.py`、`tools/tests`、`client/tests/gameplay_load_client.gd`、`client/state/game_store.gd`、`client/tests`。

#### PR13-B01.1 战斗关联合同

输入：run/client/epoch/cycle/match/battle/request及effective policy。进入集成前所需子项：LOAD-06.4、LOAD-03.3。

实施：冻结config hash/strategy/seed/phase与发起context；数据不可得为null+原因。

| 检查 | 操作/注入 | 预期结果 |
|---|---|---|
| PR13-B01.1-T01 | cycle切换迟到event | 仍旧context |
| PR13-B01.1-T02 | 不知battle seed | null不可造随机值 |
| PR13-B01.1-T03 | match维度日志 | 不变Prometheus无限label |

通过：每异步事件可追溯原上下文，字段与LOAD06共用字典和版本。

执行：OFFLINE、EXPERIMENT；命令入口：C-PY、C-GODOT、C-EXPERIMENT；关联门：G1、G3。S5：Required，按所列profile取得真实执行证据；历史结果不能冒充当前集成SHA。

交付：`outputs/pr13-acceptance/<integration_sha>/PR13-B01.1/`，包含report/cases/commands/manifest，命令记录退出码及skip；报告填统一证据字段。本轮规格复核记录：NotRevalidated，历史状态仅作来源：Queued，未签署Accepted；后续真实状态写入对应队列与acceptance_record。

失败：任一必测用例与预期不符为Failed；缺输入/环境/证据为Blocked；仅完成部分层次为Partial，不升级Accepted。 回滚：按任务独立提交回退统计/runner；保留原raw及算法版本，不覆盖已归档报告。

#### PR13-B01.2 通信、机会和有效进展

输入：合法动作门、目标/手牌/控制及权威结果。进入集成前所需子项：PR13-B01.1。

实施：区分心跳、动作机会、submit/ack、有效伤害/治疗/盾/抽牌、目标变化及等待原因。

| 检查 | 操作/注入 | 预期结果 |
|---|---|---|
| PR13-B01.2-T01 | pong和重复snapshot | 通信而非玩法进展 |
| PR13-B01.2-T02 | 满血治疗 | 耗牌/溢出而非有效恢复 |
| PR13-B01.2-T03 | 无牌/受控/等确认 | 三类原因不同 |

通过：同一等待区间有可审查原因，0伤害回包不能掩盖停滞也不能把合法蓄牌算卡死。

执行：OFFLINE、EXPERIMENT；命令入口：C-PY、C-GODOT、C-EXPERIMENT；关联门：G1、G3。S5：Required，按所列profile取得真实执行证据；历史结果不能冒充当前集成SHA。

交付：`outputs/pr13-acceptance/<integration_sha>/PR13-B01.2/`，包含report/cases/commands/manifest，命令记录退出码及skip；报告填统一证据字段。本轮规格复核记录：NotRevalidated，历史状态仅作来源：Queued，未签署Accepted；后续真实状态写入对应队列与acceptance_record。

失败：任一必测用例与预期不符为Failed；缺输入/环境/证据为Blocked；仅完成部分层次为Partial，不升级Accepted。 回滚：按任务独立提交回退统计/runner；保留原raw及算法版本，不覆盖已归档报告。

#### PR13-B01.3 分层体验指标

输入：职业/构筑/装备/怪物/网络与monotonic事件。进入集成前所需子项：PR13-B01.2。

实施：输出首次有效操作、10/30/60秒有效量、操作占比、连续控制、抽牌/溢出/请求率。

| 检查 | 操作/注入 | 预期结果 |
|---|---|---|
| PR13-B01.3-T01 | 同时两个控制 | union不叠加双倍时长 |
| PR13-B01.3-T02 | 治疗10实际2 | 有效2溢出8 |
| PR13-B01.3-T03 | 首次操作跨主机钟 | 不可测则unavailable |

通过：指标分子分母和窗口明确，可从case事件重算；延迟三段不混HTTP P95。

执行：OFFLINE、EXPERIMENT；命令入口：C-PY、C-GODOT、C-EXPERIMENT；关联门：G1、G3。S5：Required，按所列profile取得真实执行证据；历史结果不能冒充当前集成SHA。

交付：`outputs/pr13-acceptance/<integration_sha>/PR13-B01.3/`，包含report/cases/commands/manifest，命令记录退出码及skip；报告填统一证据字段。本轮规格复核记录：NotRevalidated，历史状态仅作来源：Queued，未签署Accepted；后续真实状态写入对应队列与acceptance_record。

失败：任一必测用例与预期不符为Failed；缺输入/环境/证据为Blocked；仅完成部分层次为Partial，不升级Accepted。 回滚：按任务独立提交回退统计/runner；保留原raw及算法版本，不覆盖已归档报告。

#### PR13-B01.4 终点与删失

输入：正常击杀/死亡/撤离/主动弃战/兜底/异常/截止。进入集成前所需子项：PR13-B01.3。

实施：保留全部分母，截止样本observed_duration+censored；停滞兜底单列非独立随机删失。

| 检查 | 操作/注入 | 预期结果 |
|---|---|---|
| PR13-B01.4-T01 | 观察期截止未结束 | 不记0秒/完成TTK |
| PR13-B01.4-T02 | 兜底弃战 | 不归正常胜利 |
| PR13-B01.4-T03 | 样本N不足 | 不写P99达标 |

通过：started battle=互斥结果+active/unknown；TTK结论附终点定义、删失率与限制。

执行：OFFLINE、EXPERIMENT；命令入口：C-PY、C-GODOT、C-EXPERIMENT；关联门：G1、G3。S5：Required，按所列profile取得真实执行证据；历史结果不能冒充当前集成SHA。

交付：`outputs/pr13-acceptance/<integration_sha>/PR13-B01.4/`，包含report/cases/commands/manifest，命令记录退出码及skip；报告填统一证据字段。本轮规格复核记录：NotRevalidated，历史状态仅作来源：Queued，未签署Accepted；后续真实状态写入对应队列与acceptance_record。

失败：任一必测用例与预期不符为Failed；缺输入/环境/证据为Blocked；仅完成部分层次为Partial，不升级Accepted。 回滚：按任务独立提交回退统计/runner；保留原raw及算法版本，不覆盖已归档报告。

### PR13-B02 数值合同、预览和CI一致性

负责：AG-04。文件：`server/src/FantasyCard.Domain/Combat`、`server/src/FantasyCard.Domain/Rooms`、`server/tests/FantasyCard.Domain.Tests`、`client/tests`、`protocol`。

#### PR13-B02.1 过期测试API迁移

输入：CombatAuthoritativeRulesTests及当前枚举/快照。进入集成前所需子项：LOAD-11.1。

实施：旧布尔与余量成员逐断言映射CurrentRhythm/CoreCardsSpent、CurrentSteps/FractionalRemainder；先编译复现。

| 检查 | 操作/注入 | 预期结果 |
|---|---|---|
| PR13-B02.1-T01 | 旧参数构造 | 编译失败证据 |
| PR13-B02.1-T02 | 默认构造 | 仍CurrentRhythm/CurrentSteps |
| PR13-B02.1-T03 | 候选显式枚举 | 候选断言独立 |

通过：保留原测试意图与数量变动说明，不复活废弃生产成员、不改默认来迎合断言。

执行：OFFLINE、POSTGRES；命令入口：C-BUILD、C-DOMAIN、C-SERVER、C-GODOT-NUM、C-PROTO；关联门：G1、G2、G5。S5：NotApplicableWithReason，仅凭指定离线/集成产物即可判定本子项；公网压测不增加该判据可信度。

交付：`outputs/pr13-acceptance/<integration_sha>/PR13-B02.1/`，包含report/cases/commands/manifest，命令记录退出码及skip；报告填统一证据字段。本轮规格复核记录：NotRevalidated，历史状态仅作来源：Queued，未签署Accepted；后续真实状态写入对应队列与acceptance_record。

失败：任一必测用例与预期不符为Failed；缺输入/环境/证据为Blocked；仅完成部分层次为Partial，不升级Accepted。 回滚：回退服务代码并复测旧新房间恢复；保留数据库备份/幂等流水，不用删行制造成功。

#### PR13-B02.2 真实Resolver规则向量

输入：GDD对应实例/等级/抗性/顺序输入。进入集成前所需子项：PR13-B02.1。

实施：首核/R/P/B/逐卡floor、46/72/113限定向量、双元素/调节/两种治疗用真实Resolver。

| 检查 | 操作/注入 | 预期结果 |
|---|---|---|
| PR13-B02.2-T01 | 重排同牌 | 按首核合同可不同 |
| PR13-B02.2-T02 | GDD三四五火指定向量 | 46/72/113 |
| PR13-B02.2-T03 | 普通治疗与向反E0 | 分别计算不共套牧师倍率 |

通过：金标准向量有完整配置上下文；数值不能推广为任意三张火牌伤害。

执行：OFFLINE、POSTGRES；命令入口：C-BUILD、C-DOMAIN、C-SERVER、C-GODOT-NUM、C-PROTO；关联门：G1、G2、G5。S5：NotApplicableWithReason，仅凭指定离线/集成产物即可判定本子项；公网压测不增加该判据可信度。

交付：`outputs/pr13-acceptance/<integration_sha>/PR13-B02.2/`，包含report/cases/commands/manifest，命令记录退出码及skip；报告填统一证据字段。本轮规格复核记录：NotRevalidated，历史状态仅作来源：Queued，未签署Accepted；后续真实状态写入对应队列与acceptance_record。

失败：任一必测用例与预期不符为Failed；缺输入/环境/证据为Blocked；仅完成部分层次为Partial，不升级Accepted。 回滚：回退服务代码并复测旧新房间恢复；保留数据库备份/幂等流水，不用删行制造成功。

#### PR13-B02.3 预览/协议/权威一致

输入：相同选牌顺序、target/revision、固定random与快照。进入集成前所需子项：PR13-B02.2。

实施：预览与提交比较有效伤害/治疗/盾/控制/余量；前后状态/RNG hash不变。

| 检查 | 操作/注入 | 预期结果 |
|---|---|---|
| PR13-B02.3-T01 | 连续preview | 不抽牌不进RNG不提交盾余量 |
| PR13-B02.3-T02 | proto往返 | 顺序保持 |
| PR13-B02.3-T03 | 过期revision | 预览弃置不覆盖当前 |

通过：确定性字段零差异；随机结果用受控种子/规则校验，不能要求未公开未来伤害精确展示。

执行：OFFLINE、POSTGRES；命令入口：C-BUILD、C-DOMAIN、C-SERVER、C-GODOT-NUM、C-PROTO；关联门：G1、G2、G5。S5：NotApplicableWithReason，仅凭指定离线/集成产物即可判定本子项；公网压测不增加该判据可信度。

交付：`outputs/pr13-acceptance/<integration_sha>/PR13-B02.3/`，包含report/cases/commands/manifest，命令记录退出码及skip；报告填统一证据字段。本轮规格复核记录：NotRevalidated，历史状态仅作来源：Queued，未签署Accepted；后续真实状态写入对应队列与acceptance_record。

失败：任一必测用例与预期不符为Failed；缺输入/环境/证据为Blocked；仅完成部分层次为Partial，不升级Accepted。 回滚：回退服务代码并复测旧新房间恢复；保留数据库备份/幂等流水，不用删行制造成功。

#### PR13-B02.4 房间策略和恢复

输入：effective room policy/config hash及旧快照fixture。进入集成前所需子项：PR13-B02.3。

实施：创建/PVE/PVP工作副本/持久化/恢复保策略；缺旧字段按已批准默认解释。

| 检查 | 操作/注入 | 预期结果 |
|---|---|---|
| PR13-B02.4-T01 | 当前room热更源表 | policy不静默换 |
| PR13-B02.4-T02 | PVP结束 | 恢复PVE原state |
| PR13-B02.4-T03 | 旧snapshot缺策略/无效枚举 | 兼容默认或明确拒绝不半恢复 |

通过：同SHA客户端/server/proto/Domain/PG适用测试真实执行，新旧room来源可查。

执行：OFFLINE、POSTGRES；命令入口：C-BUILD、C-DOMAIN、C-SERVER、C-GODOT-NUM、C-PROTO；关联门：G1、G2、G5。S5：NotApplicableWithReason，仅凭指定离线/集成产物即可判定本子项；公网压测不增加该判据可信度。

交付：`outputs/pr13-acceptance/<integration_sha>/PR13-B02.4/`，包含report/cases/commands/manifest，命令记录退出码及skip；报告填统一证据字段。本轮规格复核记录：NotRevalidated，历史状态仅作来源：Queued，未签署Accepted；后续真实状态写入对应队列与acceptance_record。

失败：任一必测用例与预期不符为Failed；缺输入/环境/证据为Blocked；仅完成部分层次为Partial，不升级Accepted。 回滚：回退服务代码并复测旧新房间恢复；保留数据库备份/幂等流水，不用删行制造成功。

### PR13-B03 公平场景、合法策略和统计设计

负责：AG-01。文件：`server/tools/FantasyCard.Numerics`、`tools`、`server/tests`。

#### PR13-B03.1 三种脚本策略

输入：原全手牌策略、可见信息接口及合法action门。进入集成前所需子项：PR13-B01.4、PR13-B02.4。

实施：保留baseline_all_hand，新增确定性basic/build策略；不能看库序/隐藏路线/未来drop。

| 检查 | 操作/注入 | 预期结果 |
|---|---|---|
| PR13-B03.1-T01 | 同可见state/seed | 相同动作 |
| PR13-B03.1-T02 | 只改变隐藏未来 | 策略动作不变 |
| PR13-B03.1-T03 | 目标失效/无合法动作 | 等待有原因不发非法命令 |

通过：策略版本与信息边界可审查，合法率与放弃/失败完整报告。

执行：OFFLINE、EXPERIMENT；命令入口：C-DOMAIN、C-EXPERIMENT；关联门：G2、G3、G4。S5：Required，按所列profile取得真实执行证据；历史结果不能冒充当前集成SHA。

交付：`outputs/pr13-acceptance/<integration_sha>/PR13-B03.1/`，包含report/cases/commands/manifest，命令记录退出码及skip；报告填统一证据字段。本轮规格复核记录：NotRevalidated，历史状态仅作来源：Queued，未签署Accepted；后续真实状态写入对应队列与acceptance_record。

失败：任一必测用例与预期不符为Failed；缺输入/环境/证据为Blocked；仅完成部分层次为Partial，不升级Accepted。 回滚：候选切回原策略/原配置；已创建房间沿锁定策略完成；不逆向发放资产或退款。

#### PR13-B03.2 同预算场景矩阵

输入：三职业实际20张配置与装备/地图/战斗种子。进入集成前所需子项：PR13-B03.1。

实施：默认/纯核/续航/控制过牌/调节混核，同品质等级成本；单/双/精英/Boss/PVP换边，成对加极值。

| 检查 | 操作/注入 | 预期结果 |
|---|---|---|
| PR13-B03.2-T01 | 同预算两构筑 | 成本/品质/等级一致 |
| PR13-B03.2-T02 | PVP换边 | 双方镜像资源 |
| PR13-B03.2-T03 | 隐藏路径不可见 | 不偷最优撤离 |

通过：每主要层有scenario_id/config/seed/策略，失败场景保留不过滤。

执行：OFFLINE、EXPERIMENT；命令入口：C-DOMAIN、C-EXPERIMENT；关联门：G2、G3、G4。S5：Required，按所列profile取得真实执行证据；历史结果不能冒充当前集成SHA。

交付：`outputs/pr13-acceptance/<integration_sha>/PR13-B03.2/`，包含report/cases/commands/manifest，命令记录退出码及skip；报告填统一证据字段。本轮规格复核记录：NotRevalidated，历史状态仅作来源：Queued，未签署Accepted；后续真实状态写入对应队列与acceptance_record。

失败：任一必测用例与预期不符为Failed；缺输入/环境/证据为Blocked；仅完成部分层次为Partial，不升级Accepted。 回滚：候选切回原策略/原配置；已创建房间沿锁定策略完成；不逆向发放资产或退款。

#### PR13-B03.3 配对样本与区间

输入：预登记primary endpoint/层次/观察期/seed块。进入集成前所需子项：PR13-B03.2。

实施：首轮每主要声明层至少1000配对seed、三独立seed块；按seed成对重抽样，真人资料另记。

| 检查 | 操作/注入 | 预期结果 |
|---|---|---|
| PR13-B03.3-T01 | 同seed多战 | cluster不当独立样本 |
| PR13-B03.3-T02 | 删除未结束样本 | 完整性失败 |
| PR13-B03.3-T03 | 区间宽/高删失 | 追加预登记预算或Inconclusive |

通过：样本预算不等于精度保证，报告全部结果与95%区间/多比较方案；bot不能称真人体验。

执行：OFFLINE、EXPERIMENT；命令入口：C-DOMAIN、C-EXPERIMENT；关联门：G2、G3、G4。S5：Required，按所列profile取得真实执行证据；历史结果不能冒充当前集成SHA。

交付：`outputs/pr13-acceptance/<integration_sha>/PR13-B03.3/`，包含report/cases/commands/manifest，命令记录退出码及skip；报告填统一证据字段。本轮规格复核记录：NotRevalidated，历史状态仅作来源：Queued，未签署Accepted；后续真实状态写入对应队列与acceptance_record。

失败：任一必测用例与预期不符为Failed；缺输入/环境/证据为Blocked；仅完成部分层次为Partial，不升级Accepted。 回滚：候选切回原策略/原配置；已创建房间沿锁定策略完成；不逆向发放资产或退款。

#### PR13-B03.4 profile边界和可重放

输入：capacity_baseline与combat_experience/candidate manifests。进入集成前所需子项：PR13-B03.3。

实施：策略/卡组/时长/兜底任何变化均新profile；原baseline保留同版本可重放。

| 检查 | 操作/注入 | 预期结果 |
|---|---|---|
| PR13-B03.4-T01 | 候选怪物更短 | 仅玩法结果不写容量收益 |
| PR13-B03.4-T02 | 两次同manifest | 同确定性轨迹 |
| PR13-B03.4-T03 | 改规则不改profileID | 校验拒绝 |

通过：配置可复现、时限有界、删失可见；真人缺失仅阻塞体验结论，不抹去算法证据。

执行：OFFLINE、EXPERIMENT；命令入口：C-DOMAIN、C-EXPERIMENT；关联门：G2、G3、G4。S5：Required，按所列profile取得真实执行证据；历史结果不能冒充当前集成SHA。

交付：`outputs/pr13-acceptance/<integration_sha>/PR13-B03.4/`，包含report/cases/commands/manifest，命令记录退出码及skip；报告填统一证据字段。本轮规格复核记录：NotRevalidated，历史状态仅作来源：Queued，未签署Accepted；后续真实状态写入对应队列与acceptance_record。

失败：任一必测用例与预期不符为Failed；缺输入/环境/证据为Blocked；仅完成部分层次为Partial，不升级Accepted。 回滚：候选切回原策略/原配置；已创建房间沿锁定策略完成；不逆向发放资产或退款。

### PR13-B04 默认构筑与等牌反馈

负责：AG-04。文件：`server/src/FantasyCard.Domain/Combat`、`server/src/FantasyCard.Domain/Rooms`、`server/tests/FantasyCard.Domain.Tests`、`client/state/game_store.gd`、`client/ui`、`client/data/localization_battle.json`、`client/tests`、`config/FantasyCard_Config.xlsx`。

#### PR13-B04.1 真实默认牌表诊断

输入：source workbook/生成包hash与三职业20张。进入集成前所需子项：PR13-B03.4。

实施：读取有效牌表，测无有效行动、缺防御、满血治疗、凑核和关键牌到手；区分策略打空。

| 检查 | 操作/注入 | 预期结果 |
|---|---|---|
| PR13-B04.1-T01 | 实际配置与印象不同 | 只用hash对应真实表 |
| PR13-B04.1-T02 | 全手牌/构筑策略 | 分开等牌原因 |
| PR13-B04.1-T03 | 库空有弃牌 | 按真实洗回不称永久耗尽 |

通过：20张预算与牌实例全列出，问题能区分配置/策略/流程来源。

执行：OFFLINE、EXPERIMENT、RENDER；命令入口：C-DOMAIN、C-GODOT-NUM、C-EXPERIMENT、C-RENDER；关联门：G2、G4。S5：Required，按所列profile取得真实执行证据；历史结果不能冒充当前集成SHA。

交付：`outputs/pr13-acceptance/<integration_sha>/PR13-B04.1/`，包含report/cases/commands/manifest，命令记录退出码及skip；报告填统一证据字段。本轮规格复核记录：NotRevalidated，历史状态仅作来源：Queued，未签署Accepted；后续真实状态写入对应队列与acceptance_record。

失败：任一必测用例与预期不符为Failed；缺输入/环境/证据为Blocked；仅完成部分层次为Partial，不升级Accepted。 回滚：候选切回原策略/原配置；已创建房间沿锁定策略完成；不逆向发放资产或退款。

#### PR13-B04.2 单卡替换候选

输入：B04诊断、同品质等级成本约束。进入集成前所需子项：PR13-B04.1。

实施：一次替一张，先协同再收益；保留正式默认，不加初始资源或改基础手牌。

| 检查 | 操作/注入 | 预期结果 |
|---|---|---|
| PR13-B04.2-T01 | 同预算替换 | 可配对 |
| PR13-B04.2-T02 | 用高品质替低 | 实验无效 |
| PR13-B04.2-T03 | 无构筑缺陷证据 | NoChangeWithEvidence |

通过：收益须同预算且资源守恒；默认构筑变更是后续显式配置评审。

执行：OFFLINE、EXPERIMENT、RENDER；命令入口：C-DOMAIN、C-GODOT-NUM、C-EXPERIMENT、C-RENDER；关联门：G2、G4。S5：Required，按所列profile取得真实执行证据；历史结果不能冒充当前集成SHA。

交付：`outputs/pr13-acceptance/<integration_sha>/PR13-B04.2/`，包含report/cases/commands/manifest，命令记录退出码及skip；报告填统一证据字段。本轮规格复核记录：NotRevalidated，历史状态仅作来源：Queued，未签署Accepted；后续真实状态写入对应队列与acceptance_record。

失败：任一必测用例与预期不符为Failed；缺输入/环境/证据为Blocked；仅完成部分层次为Partial，不升级Accepted。 回滚：候选切回原策略/原配置；已创建房间沿锁定策略完成；不逆向发放资产或退款。

#### PR13-B04.3 抽牌与等待提示

输入：权威draw进度、control/block/hand cap和合法动作。进入集成前所需子项：PR13-B04.2。

实施：显示正在抽牌/受控/阻断/满手轮空/等确认，ETA仅在可可靠估计时显示。

| 检查 | 操作/注入 | 预期结果 |
|---|---|---|
| PR13-B04.3-T01 | 满手5 | 满手提示不假装抽牌停坏 |
| PR13-B04.3-T02 | control | 显示权威剩余时长 |
| PR13-B04.3-T03 | 0能量无加速 | 按实际进度不把20秒推算写实测 |

通过：中文英文及现有其他语种无缺键/硬编码，宽高边界可读，按钮原因与action门一致。

执行：OFFLINE、EXPERIMENT、RENDER；命令入口：C-DOMAIN、C-GODOT-NUM、C-EXPERIMENT、C-RENDER；关联门：G2、G4。S5：Required，按所列profile取得真实执行证据；历史结果不能冒充当前集成SHA。

交付：`outputs/pr13-acceptance/<integration_sha>/PR13-B04.3/`，包含report/cases/commands/manifest，命令记录退出码及skip；报告填统一证据字段。本轮规格复核记录：NotRevalidated，历史状态仅作来源：Queued，未签署Accepted；后续真实状态写入对应队列与acceptance_record。

失败：任一必测用例与预期不符为Failed；缺输入/环境/证据为Blocked；仅完成部分层次为Partial，不升级Accepted。 回滚：候选切回原策略/原配置；已创建房间沿锁定策略完成；不逆向发放资产或退款。

#### PR13-B04.4 初始体验裁决

输入：空防具三职业、同预算seed与rendered操作。进入集成前所需子项：PR13-B04.3。

实施：对比有效操作、首战结果、凑核、资源守恒和保留牌决策；不只看点击频率。

| 检查 | 操作/注入 | 预期结果 |
|---|---|---|
| PR13-B04.4-T01 | 操作更多但死亡增多 | 不自动更好 |
| PR13-B04.4-T02 | 一职业无恢复动作 | 正确性Failed |
| PR13-B04.4-T03 | 候选无显著收益 | 保留默认并记录NoChange |

通过：无新增不可恢复无动作状态；体验与策略选择共同评估，缺真人则结论Partial。

执行：OFFLINE、EXPERIMENT、RENDER；命令入口：C-DOMAIN、C-GODOT-NUM、C-EXPERIMENT、C-RENDER；关联门：G2、G4。S5：Required，按所列profile取得真实执行证据；历史结果不能冒充当前集成SHA。

交付：`outputs/pr13-acceptance/<integration_sha>/PR13-B04.4/`，包含report/cases/commands/manifest，命令记录退出码及skip；报告填统一证据字段。本轮规格复核记录：NotRevalidated，历史状态仅作来源：Queued，未签署Accepted；后续真实状态写入对应队列与acceptance_record。

失败：任一必测用例与预期不符为Failed；缺输入/环境/证据为Blocked；仅完成部分层次为Partial，不升级Accepted。 回滚：候选切回原策略/原配置；已创建房间沿锁定策略完成；不逆向发放资产或退款。

### PR13-B05 特定PVE长尾候选

负责：AG-04。文件：`server/src/FantasyCard.Domain/Combat`、`server/src/FantasyCard.Domain/Rooms`、`server/tests/FantasyCard.Domain.Tests`、`config/FantasyCard_Config.xlsx`、`server/tools/FantasyCard.Numerics`。

#### PR13-B05.1 具体怪物归因

输入：monsterID/config/HP/抗性/节拍/可见意图及有效网络。进入集成前所需子项：PR13-B04.4、PR13-B01.4。

实施：复现白名单长尾并区分高耐久/恢复闭环/克制/控制/目标/通信问题。

| 检查 | 操作/注入 | 预期结果 |
|---|---|---|
| PR13-B05.1-T01 | 流程target错误 | 回正确性不削怪 |
| PR13-B05.1-T02 | 真高耐久且多seed可复现 | 可候选 |
| PR13-B05.1-T03 | 样本不足 | Blocked不全表调参 |

通过：每长尾有具体原因和对照，自动弃战不能充当怪物过强证据。

执行：OFFLINE、EXPERIMENT；命令入口：C-DOMAIN、C-EXPERIMENT；关联门：G2、G4、G5。S5：Required，按所列profile取得真实执行证据；历史结果不能冒充当前集成SHA。

交付：`outputs/pr13-acceptance/<integration_sha>/PR13-B05.1/`，包含report/cases/commands/manifest，命令记录退出码及skip；报告填统一证据字段。本轮规格复核记录：NotRevalidated，历史状态仅作来源：Queued，未签署Accepted；后续真实状态写入对应队列与acceptance_record。

失败：任一必测用例与预期不符为Failed；缺输入/环境/证据为Blocked；仅完成部分层次为Partial，不升级Accepted。 回滚：候选切回原策略/原配置；已创建房间沿锁定策略完成；不逆向发放资产或退款。

#### PR13-B05.2 单因素HP/预告实验

输入：获证据白名单、config override与冻结预算。进入集成前所需子项：PR13-B05.1。

实施：HP1.00/0.95/0.90一轮；首意图预告0/0.25/0.50秒另轮，不组合偷因果。

| 检查 | 操作/注入 | 预期结果 |
|---|---|---|
| PR13-B05.2-T01 | 只改白名单HP | 其他怪/PVP hash不变 |
| PR13-B05.2-T02 | 同时HP/攻击/预告 | 对照无效 |
| PR13-B05.2-T03 | 未白名单 | 不得改源正式值 |

通过：单因素差异manifest可审查，候选仅隔离；不全表降血不掩盖流程缺陷。

执行：OFFLINE、EXPERIMENT；命令入口：C-DOMAIN、C-EXPERIMENT；关联门：G2、G4、G5。S5：Required，按所列profile取得真实执行证据；历史结果不能冒充当前集成SHA。

交付：`outputs/pr13-acceptance/<integration_sha>/PR13-B05.2/`，包含report/cases/commands/manifest，命令记录退出码及skip；报告填统一证据字段。本轮规格复核记录：NotRevalidated，历史状态仅作来源：Queued，未签署Accepted；后续真实状态写入对应队列与acceptance_record。

失败：任一必测用例与预期不符为Failed；缺输入/环境/证据为Blocked；仅完成部分层次为Partial，不升级Accepted。 回滚：候选切回原策略/原配置；已创建房间沿锁定策略完成；不逆向发放资产或退款。

#### PR13-B05.3 强度/经济边界

输入：单/双/精英/Boss与真实reward/death账本。进入集成前所需子项：PR13-B05.2。

实施：保留Boss阶段/PVP，算每局与每分钟收益、药耗和死亡损失；漂移先阻塞。

| 检查 | 操作/注入 | 预期结果 |
|---|---|---|
| PR13-B05.3-T01 | 战斗缩短资源/分钟升 | 独立报告 |
| PR13-B05.3-T02 | PVP数值被间接改 | Failed |
| PR13-B05.3-T03 | 单怪收益好Boss不可识别 | 候选不通过 |

通过：经济投放与损失不改来补偿候选，无未解释资源漂移。

执行：OFFLINE、EXPERIMENT；命令入口：C-DOMAIN、C-EXPERIMENT；关联门：G2、G4、G5。S5：Required，按所列profile取得真实执行证据；历史结果不能冒充当前集成SHA。

交付：`outputs/pr13-acceptance/<integration_sha>/PR13-B05.3/`，包含report/cases/commands/manifest，命令记录退出码及skip；报告填统一证据字段。本轮规格复核记录：NotRevalidated，历史状态仅作来源：Queued，未签署Accepted；后续真实状态写入对应队列与acceptance_record。

失败：任一必测用例与预期不符为Failed；缺输入/环境/证据为Blocked；仅完成部分层次为Partial，不升级Accepted。 回滚：候选切回原策略/原配置；已创建房间沿锁定策略完成；不逆向发放资产或退款。

#### PR13-B05.4 候选推荐判据

输入：实验前冻结draft阈值和primary长尾层。进入集成前所需子项：PR13-B05.3。

实施：用配对区间判断：长尾P95相对改善15%草案、通关率5百分点/资源分钟5%漂移复审；high censoring不按完成样本推断。

| 检查 | 操作/注入 | 预期结果 |
|---|---|---|
| PR13-B05.4-T01 | 点估计15%但区间跨0 | Inconclusive |
| PR13-B05.4-T02 | 任一漂移触阈 | 专项Blocked |
| PR13-B05.4-T03 | 流程修复后无长尾 | NoChangeWithEvidence |

通过：阈值标候选评审而非正式SLO；正收益/副作用/缺证据分别给裁决。

执行：OFFLINE、EXPERIMENT；命令入口：C-DOMAIN、C-EXPERIMENT；关联门：G2、G4、G5。S5：Required，按所列profile取得真实执行证据；历史结果不能冒充当前集成SHA。

交付：`outputs/pr13-acceptance/<integration_sha>/PR13-B05.4/`，包含report/cases/commands/manifest，命令记录退出码及skip；报告填统一证据字段。本轮规格复核记录：NotRevalidated，历史状态仅作来源：Queued，未签署Accepted；后续真实状态写入对应队列与acceptance_record。

失败：任一必测用例与预期不符为Failed；缺输入/环境/证据为Blocked；仅完成部分层次为Partial，不升级Accepted。 回滚：候选切回原策略/原配置；已创建房间沿锁定策略完成；不逆向发放资产或退款。

### PR13-B06 法师返牌资源循环

负责：AG-04。文件：`server/src/FantasyCard.Domain/Combat`、`server/src/FantasyCard.Domain/Rooms`、`server/tests/FantasyCard.Domain.Tests`。

#### PR13-B06.1 CurrentRhythm对照

输入：真实CombatDeck、current策略与可控时间。进入集成前所需子项：PR13-B02.4、PR13-B03.4。

实施：固定同核单张推rhythm至5的返2路径，核对手牌上限/抽牌来源/洗牌/动作节拍。

| 检查 | 操作/注入 | 预期结果 |
|---|---|---|
| PR13-B06.1-T01 | 连续同核单张 | 按当前C/E规则请求返牌 |
| PR13-B06.1-T02 | 满手截断 | 请求数与入手数分开 |
| PR13-B06.1-T03 | 无候选开关 | 默认回归不变 |

通过：仅证明代码资源路径，不把局部路径宣称全卡池无限循环。

执行：OFFLINE、EXPERIMENT；命令入口：C-DOMAIN、C-EXPERIMENT；关联门：G2、G4、G5。S5：Required，按所列profile取得真实执行证据；历史结果不能冒充当前集成SHA。

交付：`outputs/pr13-acceptance/<integration_sha>/PR13-B06.1/`，包含report/cases/commands/manifest，命令记录退出码及skip；报告填统一证据字段。本轮规格复核记录：NotRevalidated，历史状态仅作来源：Queued，未签署Accepted；后续真实状态写入对应队列与acceptance_record。

失败：任一必测用例与预期不符为Failed；缺输入/环境/证据为Blocked；仅完成部分层次为Partial，不升级Accepted。 回滚：候选切回原策略/原配置；已创建房间沿锁定策略完成；不逆向发放资产或退款。

#### PR13-B06.2 CoreCardsSpent候选

输入：已有枚举/真实coreCount和蓄能上限。进入集成前所需子项：PR13-B06.1。

实施：R1/2/3/4/5返0/0/1/1/2，B不作真实消耗；C/E继续既有蓄能0.5上限。

| 检查 | 操作/注入 | 预期结果 |
|---|---|---|
| PR13-B06.2-T01 | R1且高rhythm | 候选即时0 |
| PR13-B06.2-T02 | R3/R5 | 分别1/2 |
| PR13-B06.2-T03 | 只有B加成无实牌 | 不按R多返 |

通过：formal默认CurrentRhythm，房间有效policy显式；不给点击全局冷却掩盖问题。

执行：OFFLINE、EXPERIMENT；命令入口：C-DOMAIN、C-EXPERIMENT；关联门：G2、G4、G5。S5：Required，按所列profile取得真实执行证据；历史结果不能冒充当前集成SHA。

交付：`outputs/pr13-acceptance/<integration_sha>/PR13-B06.2/`，包含report/cases/commands/manifest，命令记录退出码及skip；报告填统一证据字段。本轮规格复核记录：NotRevalidated，历史状态仅作来源：Queued，未签署Accepted；后续真实状态写入对应队列与acceptance_record。

失败：任一必测用例与预期不符为Failed；缺输入/环境/证据为Blocked；仅完成部分层次为Partial，不升级Accepted。 回滚：候选切回原策略/原配置；已创建房间沿锁定策略完成；不逆向发放资产或退款。

#### PR13-B06.3 复合过牌长序列

输入：自然时间暂停、有限最大动作及完整牌实例ledger。进入集成前所需子项：PR13-B06.2。

实施：被动单独/水调节/即时抽/双抽/加速分别及组合，记消耗、请求draw、实际draw、蓄能、洗牌与cap。

| 检查 | 操作/注入 | 预期结果 |
|---|---|---|
| PR13-B06.3-T01 | 无自然时间仅被动 | 不能资源自维持至上限 |
| PR13-B06.3-T02 | 复合形成闭环 | 记录来源不是误写全池无环 |
| PR13-B06.3-T03 | 空库有弃牌 | 洗牌实例总数守恒 |

通过：ledger闭合，触动作上限样本为未结束；局部证明和全卡池测试范围分列。

执行：OFFLINE、EXPERIMENT；命令入口：C-DOMAIN、C-EXPERIMENT；关联门：G2、G4、G5。S5：Required，按所列profile取得真实执行证据；历史结果不能冒充当前集成SHA。

交付：`outputs/pr13-acceptance/<integration_sha>/PR13-B06.3/`，包含report/cases/commands/manifest，命令记录退出码及skip；报告填统一证据字段。本轮规格复核记录：NotRevalidated，历史状态仅作来源：Queued，未签署Accepted；后续真实状态写入对应队列与acceptance_record。

失败：任一必测用例与预期不符为Failed；缺输入/环境/证据为Blocked；仅完成部分层次为Partial，不升级Accepted。 回滚：候选切回原策略/原配置；已创建房间沿锁定策略完成；不逆向发放资产或退款。

#### PR13-B06.4 候选体验和版本

输入：单张/三核/五核/混核同预算和快照/PVP。进入集成前所需子项：PR13-B06.3。

实施：比净卡差、10/30/60秒有效量、空等/死亡/对位，测试restore与PVP持同policy。

| 检查 | 操作/注入 | 预期结果 |
|---|---|---|
| PR13-B06.4-T01 | 三核五核 | 返牌反馈保留 |
| PR13-B06.4-T02 | 单张资源降但空等显著升 | 副作用可见 |
| PR13-B06.4-T03 | 重连/PVP | policy/hash不换 |

通过：默认无退化，候选资源问题与体验都获证据；缺真人只给算法/仿真Partial推荐。

执行：OFFLINE、EXPERIMENT；命令入口：C-DOMAIN、C-EXPERIMENT；关联门：G2、G4、G5。S5：Required，按所列profile取得真实执行证据；历史结果不能冒充当前集成SHA。

交付：`outputs/pr13-acceptance/<integration_sha>/PR13-B06.4/`，包含report/cases/commands/manifest，命令记录退出码及skip；报告填统一证据字段。本轮规格复核记录：NotRevalidated，历史状态仅作来源：Queued，未签署Accepted；后续真实状态写入对应队列与acceptance_record。

失败：任一必测用例与预期不符为Failed；缺输入/环境/证据为Blocked；仅完成部分层次为Partial，不升级Accepted。 回滚：候选切回原策略/原配置；已创建房间沿锁定策略完成；不逆向发放资产或退款。

### PR13-B07 盾职业梯度与余量

负责：AG-04。文件：`server/src/FantasyCard.Domain/Combat`、`server/src/FantasyCard.Domain/Rooms`、`server/tests/FantasyCard.Domain.Tests`、`client/state/game_store.gd`、`client/ui`、`client/data/localization_battle.json`、`client/tests`。

#### PR13-B07.1 当前与定点表

输入：CurrentSteps/FractionalRemainder和+0至+5。进入集成前所需子项：PR13-B02.4、PR13-B03.4。

实施：对照[1,1,2,2,3,3]与十分点[10,14,18,22,26,30]，上限与端点不变。

| 检查 | 操作/注入 | 预期结果 |
|---|---|---|
| PR13-B07.1-T01 | +0/+5 | 均值1/3不变 |
| PR13-B07.1-T02 | +1/+3 | 均值1.4/2.2明确 |
| PR13-B07.1-T03 | 无候选 | 仍旧整数台阶 |

通过：不使用概率触发、不改牌面floor/HP/护盾帽，正式默认不变。

执行：OFFLINE、EXPERIMENT、RENDER；命令入口：C-DOMAIN、C-GODOT-NUM、C-EXPERIMENT、C-RENDER；关联门：G2、G4、G5。S5：Required，按所列profile取得真实执行证据；历史结果不能冒充当前集成SHA。

交付：`outputs/pr13-acceptance/<integration_sha>/PR13-B07.1/`，包含report/cases/commands/manifest，命令记录退出码及skip；报告填统一证据字段。本轮规格复核记录：NotRevalidated，历史状态仅作来源：Queued，未签署Accepted；后续真实状态写入对应队列与acceptance_record。

失败：任一必测用例与预期不符为Failed；缺输入/环境/证据为Blocked；仅完成部分层次为Partial，不升级Accepted。 回滚：候选切回原策略/原配置；已创建房间沿锁定策略完成；不逆向发放资产或退款。

#### PR13-B07.2 存量+2/+4影响

输入：同构筑装备/受伤seed与shield利用事件。进入集成前所需子项：PR13-B07.1。

实施：单独评价2至1.8、3至2.6的生存/溢出/实际盾；记录受影响等级与审核。

| 检查 | 操作/注入 | 预期结果 |
|---|---|---|
| PR13-B07.2-T01 | +2/+4有生存降 | 明确削弱及区间 |
| PR13-B07.2-T02 | +1改善 | 不能掩盖他档下降 |
| PR13-B07.2-T03 | 总体平均 | 不得代替各等级 |

通过：每等级独立结果，不称全等级加强、不自动改强化价/退款。

执行：OFFLINE、EXPERIMENT、RENDER；命令入口：C-DOMAIN、C-GODOT-NUM、C-EXPERIMENT、C-RENDER；关联门：G2、G4、G5。S5：Required，按所列profile取得真实执行证据；历史结果不能冒充当前集成SHA。

交付：`outputs/pr13-acceptance/<integration_sha>/PR13-B07.2/`，包含report/cases/commands/manifest，命令记录退出码及skip；报告填统一证据字段。本轮规格复核记录：NotRevalidated，历史状态仅作来源：Queued，未签署Accepted；后续真实状态写入对应队列与acceptance_record。

失败：任一必测用例与预期不符为Failed；缺输入/环境/证据为Blocked；仅完成部分层次为Partial，不升级Accepted。 回滚：候选切回原策略/原配置；已创建房间沿锁定策略完成；不逆向发放资产或退款。

#### PR13-B07.3 余量提交/清零

输入：五连放/上限/失败/预览/离格/PVP fixture。进入集成前所需子项：PR13-B07.2。

实施：无截断五次贡献5/7/9/11/13/15；逐边界验证余量一次提交及清零。

| 检查 | 操作/注入 | 预期结果 |
|---|---|---|
| PR13-B07.3-T01 | preview/重复/非法 | 余量不增加 |
| PR13-B07.3-T02 | 满盾/精确填满/溢出/零盾 | 已满盾或零牌面盾不生成或消耗既有余量；本次整数盾精确填满或超上限时提交余量0；离格ClearShield同时清余量 |
| PR13-B07.3-T03 | 重连/PVP工作副本恢复 | 余量不复制刷收益 |

通过：定点累计精确，所有cap边界有golden state；默认和candidate分开执行。 (Already-full/zero-card-shield retains the existing remainder; a successful play exactly filling or overflowing the cap commits zero; leaving the cell clears it.)

执行：OFFLINE、EXPERIMENT、RENDER；命令入口：C-DOMAIN、C-GODOT-NUM、C-EXPERIMENT、C-RENDER；关联门：G2、G4、G5。S5：Required，按所列profile取得真实执行证据；历史结果不能冒充当前集成SHA。

交付：`outputs/pr13-acceptance/<integration_sha>/PR13-B07.3/`，包含report/cases/commands/manifest，命令记录退出码及skip；报告填统一证据字段。本轮规格复核记录：NotRevalidated，历史状态仅作来源：Queued，未签署Accepted；后续真实状态写入对应队列与acceptance_record。

失败：任一必测用例与预期不符为Failed；缺输入/环境/证据为Blocked；仅完成部分层次为Partial，不升级Accepted。 回滚：候选切回原策略/原配置；已创建房间沿锁定策略完成；不逆向发放资产或退款。

#### PR13-B07.4 有效盾和余量显示

输入：当前room policy、预览revision和权威余量。进入集成前所需子项：PR13-B07.3。

实施：显示本次整数、实际盾、溢出和候选余量；候选字段不假扮已启正式规则。

| 检查 | 操作/注入 | 预期结果 |
|---|---|---|
| PR13-B07.4-T01 | 旧策略room | 不显示候选余量规则 |
| PR13-B07.4-T02 | 预览到结算 | 数值与权威一致 |
| PR13-B07.4-T03 | 中英/窄屏 | 标签不截关键值 |

通过：预览无副作用、显示不误导概率/平均，数值推荐需独立存量等级裁决。

执行：OFFLINE、EXPERIMENT、RENDER；命令入口：C-DOMAIN、C-GODOT-NUM、C-EXPERIMENT、C-RENDER；关联门：G2、G4、G5。S5：Required，按所列profile取得真实执行证据；历史结果不能冒充当前集成SHA。

交付：`outputs/pr13-acceptance/<integration_sha>/PR13-B07.4/`，包含report/cases/commands/manifest，命令记录退出码及skip；报告填统一证据字段。本轮规格复核记录：NotRevalidated，历史状态仅作来源：Queued，未签署Accepted；后续真实状态写入对应队列与acceptance_record。

失败：任一必测用例与预期不符为Failed；缺输入/环境/证据为Blocked；仅完成部分层次为Partial，不升级Accepted。 回滚：候选切回原策略/原配置；已创建房间沿锁定策略完成；不逆向发放资产或退款。

### PR13-B08 控制、续航与调节边际收益

负责：AG-04。文件：`server/src/FantasyCard.Domain/Combat`、`server/src/FantasyCard.Domain/Rooms`、`server/tests/FantasyCard.Domain.Tests`、`client/state/game_store.gd`、`client/ui`、`client/data/localization_battle.json`、`client/tests`。

#### PR13-B08.1 既有8秒控制合同

输入：Target控制调用链、monotonic边界/快照/PVP。进入集成前所需子项：PR13-B02.4、PR13-B03.4。

实施：分请求/减免后/重叠新增控制和不可操作union，核对full/half/zero边界。

| 检查 | 操作/注入 | 预期结果 |
|---|---|---|
| PR13-B08.1-T01 | 同窗第1/2/3次 | 全/半/零现行合同 |
| PR13-B08.1-T02 | 8秒边界前/后 | Advance to 7.999s: the same target remains in its current diminishing window; Advance to exactly 8.000s: the expired window is removed and the next same-target stun starts a new full-duration window. No second diminishing algorithm. |
| PR13-B08.1-T03 | 新目标/重连 | 目标独立且快照正确 |

通过：不再加第二套递减，控制统计不累计重复重叠时长。

执行：OFFLINE、EXPERIMENT、RENDER；命令入口：C-DOMAIN、C-GODOT-NUM、C-EXPERIMENT、C-RENDER；关联门：G2、G4。S5：Required，按所列profile取得真实执行证据；历史结果不能冒充当前集成SHA。

交付：`outputs/pr13-acceptance/<integration_sha>/PR13-B08.1/`，包含report/cases/commands/manifest，命令记录退出码及skip；报告填统一证据字段。本轮规格复核记录：NotRevalidated，历史状态仅作来源：Queued，未签署Accepted；后续真实状态写入对应队列与acceptance_record。

失败：任一必测用例与预期不符为Failed；缺输入/环境/证据为Blocked；仅完成部分层次为Partial，不升级Accepted。 回滚：候选切回原策略/原配置；已创建房间沿锁定策略完成；不逆向发放资产或退款。

#### PR13-B08.2 同品质单卡边际

输入：五系调节真实表及同seed替换构筑。进入集成前所需子项：PR13-B08.1。

实施：分净卡差、有效伤害/盾/治疗/控制和cap损失，整体输出与稀释一起比较。

| 检查 | 操作/注入 | 预期结果 |
|---|---|---|
| PR13-B08.2-T01 | 换水即时抽 | 实际draw不是理论请求 |
| PR13-B08.2-T02 | 换金控制 | 新增union而非牌面秒数 |
| PR13-B08.2-T03 | 满血满盾 | 有效收益与溢出分列 |

通过：不以静态总V或更频繁动作判平衡，不统一削所有调节牌。

执行：OFFLINE、EXPERIMENT、RENDER；命令入口：C-DOMAIN、C-GODOT-NUM、C-EXPERIMENT、C-RENDER；关联门：G2、G4。S5：Required，按所列profile取得真实执行证据；历史结果不能冒充当前集成SHA。

交付：`outputs/pr13-acceptance/<integration_sha>/PR13-B08.2/`，包含report/cases/commands/manifest，命令记录退出码及skip；报告填统一证据字段。本轮规格复核记录：NotRevalidated，历史状态仅作来源：Queued，未签署Accepted；后续真实状态写入对应队列与acceptance_record。

失败：任一必测用例与预期不符为Failed；缺输入/环境/证据为Blocked；仅完成部分层次为Partial，不升级Accepted。 回滚：候选切回原策略/原配置；已创建房间沿锁定策略完成；不逆向发放资产或退款。

#### PR13-B08.3 主核/抵消/回复合同

输入：当前first-eligible与R/P/B/E0定义。进入集成前所需子项：PR13-B08.2。

实施：调节可定核/计同核不增P不进E0，但其他反牌可经K影响；两类治疗分开。

| 检查 | 操作/注入 | 预期结果 |
|---|---|---|
| PR13-B08.3-T01 | 首张调节 | 按规则定核 |
| PR13-B08.3-T02 | 同核调节加其他反牌 | K间接降低合法 |
| PR13-B08.3-T03 | 向反回复 | 不套普通牧师倍率 |

通过：服务端/preview/proto顺序同输入零合同差异，说明中英同步。

执行：OFFLINE、EXPERIMENT、RENDER；命令入口：C-DOMAIN、C-GODOT-NUM、C-EXPERIMENT、C-RENDER；关联门：G2、G4。S5：Required，按所列profile取得真实执行证据；历史结果不能冒充当前集成SHA。

交付：`outputs/pr13-acceptance/<integration_sha>/PR13-B08.3/`，包含report/cases/commands/manifest，命令记录退出码及skip；报告填统一证据字段。本轮规格复核记录：NotRevalidated，历史状态仅作来源：Queued，未签署Accepted；后续真实状态写入对应队列与acceptance_record。

失败：任一必测用例与预期不符为Failed；缺输入/环境/证据为Blocked；仅完成部分层次为Partial，不升级Accepted。 回滚：候选切回原策略/原配置；已创建房间沿锁定策略完成；不逆向发放资产或退款。

#### PR13-B08.4 帽内有效值和候选条件

输入：元素抗性/抽牌地板/盾cap及真实来源。进入集成前所需子项：PR13-B08.3。

实施：理论/有效/溢出/边际强化并列；只有获证异常提单卡/同来源版本候选。

| 检查 | 操作/注入 | 预期结果 |
|---|---|---|
| PR13-B08.4-T01 | 抗性超60% | 实际增量0且提示 |
| PR13-B08.4-T02 | 装备floor与PVE阻断转加速 | 不同阶段解释 |
| PR13-B08.4-T03 | 无边际异常 | NoChange不全面加速/削牌 |

通过：cap计算与现行规则一致，有候选只隔离且一因素；显示不把不适用职业误称超帽。

执行：OFFLINE、EXPERIMENT、RENDER；命令入口：C-DOMAIN、C-GODOT-NUM、C-EXPERIMENT、C-RENDER；关联门：G2、G4。S5：Required，按所列profile取得真实执行证据；历史结果不能冒充当前集成SHA。

交付：`outputs/pr13-acceptance/<integration_sha>/PR13-B08.4/`，包含report/cases/commands/manifest，命令记录退出码及skip；报告填统一证据字段。本轮规格复核记录：NotRevalidated，历史状态仅作来源：Queued，未签署Accepted；后续真实状态写入对应队列与acceptance_record。

失败：任一必测用例与预期不符为Failed；缺输入/环境/证据为Blocked；仅完成部分层次为Partial，不升级Accepted。 回滚：候选切回原策略/原配置；已创建房间沿锁定策略完成；不逆向发放资产或退款。

### PR13-B09 怪物卡池和构筑连续性

负责：AG-04。文件：`server/src/FantasyCard.Domain/Combat`、`server/src/FantasyCard.Domain/Rooms`、`server/tests/FantasyCard.Domain.Tests`、`client/state/game_store.gd`、`client/ui`、`client/data/localization_battle.json`、`client/tests`。

#### PR13-B09.1 实际怪物pool基线

输入：effective pool policy、合法击杀与牌实例。进入集成前所需子项：PR13-B02.4、PR13-B03.4。

实施：核查已有接纳/跳过/替换能力，再测池大小/关键牌到手/同核/路线稀释。

| 检查 | 操作/注入 | 预期结果 |
|---|---|---|
| PR13-B09.1-T01 | 默认policy关闭 | 不说已启选择 |
| PR13-B09.1-T02 | 杀怪新牌 | 记录合法来源 |
| PR13-B09.1-T03 | 更多牌但关键牌变慢 | 强度与稀释分开 |

通过：从有效room policy出发，牌池实例与来源可追踪，新增数不直接推出强弱。

执行：OFFLINE、EXPERIMENT、RENDER；命令入口：C-DOMAIN、C-GODOT-NUM、C-EXPERIMENT、C-RENDER；关联门：G2、G4、G5。S5：Required，按所列profile取得真实执行证据；历史结果不能冒充当前集成SHA。

交付：`outputs/pr13-acceptance/<integration_sha>/PR13-B09.1/`，包含report/cases/commands/manifest，命令记录退出码及skip；报告填统一证据字段。本轮规格复核记录：NotRevalidated，历史状态仅作来源：Queued，未签署Accepted；后续真实状态写入对应队列与acceptance_record。

失败：任一必测用例与预期不符为Failed；缺输入/环境/证据为Blocked；仅完成部分层次为Partial，不升级Accepted。 回滚：候选切回原策略/原配置；已创建房间沿锁定策略完成；不逆向发放资产或退款。

#### PR13-B09.2 3/5/8位候选

输入：OptionalMonsterPool现有策略与容量override。进入集成前所需子项：PR13-B09.1。

实施：比3/5/8，同基础20，新接纳入弃牌不补抽，非战斗选择，无跳过补偿。

| 检查 | 操作/注入 | 预期结果 |
|---|---|---|
| PR13-B09.2-T01 | 未满接纳 | 弃牌增加1手牌不变 |
| PR13-B09.2-T02 | 满位替换 | 只换monster不删基础牌 |
| PR13-B09.2-T03 | 跳过 | 无资源补偿 |

通过：默认现行rule保留，每profile只有cap差异，种子/策略/成本相同。

执行：OFFLINE、EXPERIMENT、RENDER；命令入口：C-DOMAIN、C-GODOT-NUM、C-EXPERIMENT、C-RENDER；关联门：G2、G4、G5。S5：Required，按所列profile取得真实执行证据；历史结果不能冒充当前集成SHA。

交付：`outputs/pr13-acceptance/<integration_sha>/PR13-B09.2/`，包含report/cases/commands/manifest，命令记录退出码及skip；报告填统一证据字段。本轮规格复核记录：NotRevalidated，历史状态仅作来源：Queued，未签署Accepted；后续真实状态写入对应队列与acceptance_record。

失败：任一必测用例与预期不符为Failed；缺输入/环境/证据为Blocked；仅完成部分层次为Partial，不升级Accepted。 回滚：候选切回原策略/原配置；已创建房间沿锁定策略完成；不逆向发放资产或退款。

#### PR13-B09.3 来源、幂等和状态切换

输入：事务版本、入侵/PVP/快照/终态fixture。进入集成前所需子项：PR13-B09.2。

实施：重复submit、满位、入侵中断、恢复、死亡撤离清理；验证唯一instance和本玩家击杀。

| 检查 | 操作/注入 | 预期结果 |
|---|---|---|
| PR13-B09.3-T01 | 其他玩家候选 | 拒绝 |
| PR13-B09.3-T02 | 重复request | 一个结果不复制 |
| PR13-B09.3-T03 | PVP进入/恢复/结束 | pool与实例边界一致 |

通过：基础20不删、总实例守恒、无跨room污染；操作只有非战斗合法时机。

执行：OFFLINE、EXPERIMENT、RENDER；命令入口：C-DOMAIN、C-GODOT-NUM、C-EXPERIMENT、C-RENDER；关联门：G2、G4、G5。S5：Required，按所列profile取得真实执行证据；历史结果不能冒充当前集成SHA。

交付：`outputs/pr13-acceptance/<integration_sha>/PR13-B09.3/`，包含report/cases/commands/manifest，命令记录退出码及skip；报告填统一证据字段。本轮规格复核记录：NotRevalidated，历史状态仅作来源：Queued，未签署Accepted；后续真实状态写入对应队列与acceptance_record。

失败：任一必测用例与预期不符为Failed；缺输入/环境/证据为Blocked；仅完成部分层次为Partial，不升级Accepted。 回滚：候选切回原策略/原配置；已创建房间沿锁定策略完成；不逆向发放资产或退款。

#### PR13-B09.4 连续性与选择成本

输入：关键牌、路线强度/经济、UI选择打断。进入集成前所需子项：PR13-B09.3。

实施：比有效构筑/选择时长/请求量/资源分钟与可见策略，不自动启用候选。

| 检查 | 操作/注入 | 预期结果 |
|---|---|---|
| PR13-B09.4-T01 | cap5关键牌改善但打断增 | 副作用单列 |
| PR13-B09.4-T02 | 偷库序 | 实验无效 |
| PR13-B09.4-T03 | cap无稳定收益 | 保留正式rule并NoChange |

通过：同预算合法信息可复现，体验Partial不伪称真人，收益需来源和实例守恒通过。

执行：OFFLINE、EXPERIMENT、RENDER；命令入口：C-DOMAIN、C-GODOT-NUM、C-EXPERIMENT、C-RENDER；关联门：G2、G4、G5。S5：Required，按所列profile取得真实执行证据；历史结果不能冒充当前集成SHA。

交付：`outputs/pr13-acceptance/<integration_sha>/PR13-B09.4/`，包含report/cases/commands/manifest，命令记录退出码及skip；报告填统一证据字段。本轮规格复核记录：NotRevalidated，历史状态仅作来源：Queued，未签署Accepted；后续真实状态写入对应队列与acceptance_record。

失败：任一必测用例与预期不符为Failed；缺输入/环境/证据为Blocked；仅完成部分层次为Partial，不升级Accepted。 回滚：候选切回原策略/原配置；已创建房间沿锁定策略完成；不逆向发放资产或退款。

### PR13-B10 选牌顺序、预览和反馈

负责：AG-02。文件：`client/state/game_store.gd`、`client/ui`、`client/data/localization_battle.json`、`client/tests`、`protocol/realtime/v1`。

#### PR13-B10.1 顺序/主核可见

输入：selected_cards顺序、core算法与revision。进入集成前所需子项：PR13-B02.3。

实施：选序编号/主核标识，明确重选/调整；preview绑定target/room/revision/policy不暗中排序。

| 检查 | 操作/注入 | 预期结果 |
|---|---|---|
| PR13-B10.1-T01 | 相同牌重选换顺序 | 协议输入随之改 |
| PR13-B10.1-T02 | 同牌预览旧revision | 拒绝旧结果 |
| PR13-B10.1-T03 | 重连恢复 | 合法当前选择或明确清空 |

通过：客户端推荐/显示/序列化顺序一致，快照不暗排。

执行：OFFLINE、RENDER；命令入口：C-GODOT、C-GODOT-NUM、C-PROTO、C-RENDER；关联门：G2、G3。S5：Required，按所列profile取得真实执行证据；历史结果不能冒充当前集成SHA。

交付：`outputs/pr13-acceptance/<integration_sha>/PR13-B10.1/`，包含report/cases/commands/manifest，命令记录退出码及skip；报告填统一证据字段。本轮规格复核记录：NotRevalidated，历史状态仅作来源：Queued，未签署Accepted；后续真实状态写入对应队列与acceptance_record。

失败：任一必测用例与预期不符为Failed；缺输入/环境/证据为Blocked；仅完成部分层次为Partial，不升级Accepted。 回滚：回退客户端状态/流程提交，保留未确认结算上下文；不清空服务器资产或重放游标。

#### PR13-B10.2 有效值与多语言说明

输入：权威preview字段、理论/有效/溢出及本地化keys。进入集成前所需子项：PR13-B10.1。

实施：展示基础/核倍率/向反/伤害/治疗/盾，随机或不可得阶段不虚构精确值，窄屏折叠。

| 检查 | 操作/注入 | 预期结果 |
|---|---|---|
| PR13-B10.2-T01 | 满血治疗 | 实际0/溢出清楚 |
| PR13-B10.2-T02 | 盾近cap | 本次有效与理论分列 |
| PR13-B10.2-T03 | 中英文及现有locale | 无缺键/错误fallback |

通过：解释数值与实际合同一致，显示变更不改公式、不泄露未来隐藏信息。

执行：OFFLINE、RENDER；命令入口：C-GODOT、C-GODOT-NUM、C-PROTO、C-RENDER；关联门：G2、G3。S5：Required，按所列profile取得真实执行证据；历史结果不能冒充当前集成SHA。

交付：`outputs/pr13-acceptance/<integration_sha>/PR13-B10.2/`，包含report/cases/commands/manifest，命令记录退出码及skip；报告填统一证据字段。本轮规格复核记录：NotRevalidated，历史状态仅作来源：Queued，未签署Accepted；后续真实状态写入对应队列与acceptance_record。

失败：任一必测用例与预期不符为Failed；缺输入/环境/证据为Blocked；仅完成部分层次为Partial，不升级Accepted。 回滚：回退客户端状态/流程提交，保留未确认结算上下文；不清空服务器资产或重放游标。

#### PR13-B10.3 本地按下与权威成功

输入：input/frame/command requestID与确认事件。进入集成前所需子项：PR13-B10.2。

实施：本地选中/按下及时反馈；submitted/confirmed/rejected/recovering不同，合法业务command单条。

| 检查 | 操作/注入 | 预期结果 |
|---|---|---|
| PR13-B10.3-T01 | 快速双击 | 一条合法命令 |
| PR13-B10.3-T02 | await未确认 | 不伪扣HP/奖励/成功音 |
| PR13-B10.3-T03 | 断线重复输入 | 有界队列或拒绝不无界缓存 |

通过：业务去重与视觉状态真实，提交/成功音效沿已有权威事件门。

执行：OFFLINE、RENDER；命令入口：C-GODOT、C-GODOT-NUM、C-PROTO、C-RENDER；关联门：G2、G3。S5：Required，按所列profile取得真实执行证据；历史结果不能冒充当前集成SHA。

交付：`outputs/pr13-acceptance/<integration_sha>/PR13-B10.3/`，包含report/cases/commands/manifest，命令记录退出码及skip；报告填统一证据字段。本轮规格复核记录：NotRevalidated，历史状态仅作来源：Queued，未签署Accepted；后续真实状态写入对应队列与acceptance_record。

失败：任一必测用例与预期不符为Failed；缺输入/环境/证据为Blocked；仅完成部分层次为Partial，不升级Accepted。 回滚：回退客户端状态/流程提交，保留未确认结算上下文；不清空服务器资产或重放游标。

#### PR13-B10.4 帧率/延迟/失效目标

输入：30/60/144fps、0/100/300/1000ms延迟和lossfixture。进入集成前所需子项：PR13-B10.3。

实施：测input至local feedback、command RTT、authority至animation；目标死亡/手牌变化/切room/重连回归。

| 检查 | 操作/注入 | 预期结果 |
|---|---|---|
| PR13-B10.4-T01 | 目标死亡 | 不偷偷换用户目标 |
| PR13-B10.4-T02 | 低FPS | 反馈在下一可呈现帧且不锁合法动作 |
| PR13-B10.4-T03 | 旧ack迟到 | 不新房幽灵伤害 |

通过：三段时间分别报告与设备基线，未预登记UX阈值不写达标；无重复出牌/幽灵结果。

执行：OFFLINE、RENDER；命令入口：C-GODOT、C-GODOT-NUM、C-PROTO、C-RENDER；关联门：G2、G3。S5：Required，按所列profile取得真实执行证据；历史结果不能冒充当前集成SHA。

交付：`outputs/pr13-acceptance/<integration_sha>/PR13-B10.4/`，包含report/cases/commands/manifest，命令记录退出码及skip；报告填统一证据字段。本轮规格复核记录：NotRevalidated，历史状态仅作来源：Queued，未签署Accepted；后续真实状态写入对应队列与acceptance_record。

失败：任一必测用例与预期不符为Failed；缺输入/环境/证据为Blocked；仅完成部分层次为Partial，不升级Accepted。 回滚：回退客户端状态/流程提交，保留未确认结算上下文；不清空服务器资产或重放游标。

### PR13-B11 多局等待和过渡体验

负责：AG-02。文件：`client/state/game_store.gd`、`client/ui`、`client/data/localization_battle.json`、`client/tests`、`client/tests/gameplay_load_client.gd`、`client/state/game_store.gd`、`client/tests`。

#### PR13-B11.1 可见等待状态

输入：ready/deadline、control/draw、target、holds/receipt。进入集成前所需子项：PR13-A03.4、PR13-A04.4、PR13-B01.2。

实施：准备确认/进房/抽牌受控/切目标/终态/资产处理中/待ack各显示真实原因。

| 检查 | 操作/注入 | 预期结果 |
|---|---|---|
| PR13-B11.1-T01 | ready权威deadline | 剩余时间而非预计server finish |
| PR13-B11.1-T02 | holds等待 | 资产处理中 |
| PR13-B11.1-T03 | 等command | submitted非按钮无响应 |

通过：状态与可操作门一致，倒计时有来源，网络/资源未知不编预计秒数。

执行：OFFLINE、POSTGRES、LIVE、RENDER；命令入口：C-GODOT、C-SERVER、C-LIVE、C-RENDER；关联门：G2、G3。S5：Required，按所列profile取得真实执行证据；历史结果不能冒充当前集成SHA。

交付：`outputs/pr13-acceptance/<integration_sha>/PR13-B11.1/`，包含report/cases/commands/manifest，命令记录退出码及skip；报告填统一证据字段。本轮规格复核记录：NotRevalidated，历史状态仅作来源：Queued，未签署Accepted；后续真实状态写入对应队列与acceptance_record。

失败：任一必测用例与预期不符为Failed；缺输入/环境/证据为Blocked；仅完成部分层次为Partial，不升级Accepted。 回滚：回退客户端状态/流程提交，保留未确认结算上下文；不清空服务器资产或重放游标。

#### PR13-B11.2 结算UI恢复

输入：A03真实入口与ack持久事实。进入集成前所需子项：PR13-B11.1。

实施：复用重复NOT_IN_ROOM/旧回调隔离，回大厅不吞未确认receipt；ack丢包有待核实入口。

| 检查 | 操作/注入 | 预期结果 |
|---|---|---|
| PR13-B11.2-T01 | 重复错误 | 保原match |
| PR13-B11.2-T02 | 旧callback在新局 | 不清新UI |
| PR13-B11.2-T03 | 回大厅时ackUnknown | 可恢复receipt/明确状态 |

通过：资产一次且恢复入口可见，动画不阻塞合法新局动作。

执行：OFFLINE、POSTGRES、LIVE、RENDER；命令入口：C-GODOT、C-SERVER、C-LIVE、C-RENDER；关联门：G2、G3。S5：Required，按所列profile取得真实执行证据；历史结果不能冒充当前集成SHA。

交付：`outputs/pr13-acceptance/<integration_sha>/PR13-B11.2/`，包含report/cases/commands/manifest，命令记录退出码及skip；报告填统一证据字段。本轮规格复核记录：NotRevalidated，历史状态仅作来源：Queued，未签署Accepted；后续真实状态写入对应队列与acceptance_record。

失败：任一必测用例与预期不符为Failed；缺输入/环境/证据为Blocked；仅完成部分层次为Partial，不升级Accepted。 回滚：回退客户端状态/流程提交，保留未确认结算上下文；不清空服务器资产或重放游标。

#### PR13-B11.3 有证据才轻量化

输入：Bootstrap route/bytes/SQL/wait剖析及holds安全。进入集成前所需子项：PR13-B11.2。

实施：成本显著才评审轻量查询/单飞/退避，复用LOAD08.4同契约与兼容，不另造接口。

| 检查 | 操作/注入 | 预期结果 |
|---|---|---|
| PR13-B11.3-T01 | 有ID | 单项优先 |
| PR13-B11.3-T02 | 没热点 | NoChange仍保恢复 |
| PR13-B11.3-T03 | 跨玩家/holds未ready | 拒绝/继续等待 |

通过：请求下降不漏资产验证，用户等待原因/恢复无退化，候选收益同profile可重算。

执行：OFFLINE、POSTGRES、LIVE、RENDER；命令入口：C-GODOT、C-SERVER、C-LIVE、C-RENDER；关联门：G2、G3。S5：Required，按所列profile取得真实执行证据；历史结果不能冒充当前集成SHA。

交付：`outputs/pr13-acceptance/<integration_sha>/PR13-B11.3/`，包含report/cases/commands/manifest，命令记录退出码及skip；报告填统一证据字段。本轮规格复核记录：NotRevalidated，历史状态仅作来源：Queued，未签署Accepted；后续真实状态写入对应队列与acceptance_record。

失败：任一必测用例与预期不符为Failed；缺输入/环境/证据为Blocked；仅完成部分层次为Partial，不升级Accepted。 回滚：回退客户端状态/流程提交，保留未确认结算上下文；不清空服务器资产或重放游标。

#### PR13-B11.4 有渲染三局和窄屏

输入：三职业真实会话、1280x720与1920x1080/目标窄布局。进入集成前所需子项：PR13-B11.3。

实施：headless流程另列，录rendered准备至ack三局；长文/语言/断线等待全检查。

| 检查 | 操作/注入 | 预期结果 |
|---|---|---|
| PR13-B11.4-T01 | 第2/3局按钮 | 可用且无旧overlay |
| PR13-B11.4-T02 | 窄屏长英文 | 核心提示/按钮不遮挡 |
| PR13-B11.4-T03 | 再连接/ack失败 | 有明确恢复操作 |

通过：无关键文字溢出/误导状态/动画阻塞；真人反馈缺失标Partial，截图不能替代操作日志。

执行：OFFLINE、POSTGRES、LIVE、RENDER；命令入口：C-GODOT、C-SERVER、C-LIVE、C-RENDER；关联门：G2、G3。S5：Required，按所列profile取得真实执行证据；历史结果不能冒充当前集成SHA。

交付：`outputs/pr13-acceptance/<integration_sha>/PR13-B11.4/`，包含report/cases/commands/manifest，命令记录退出码及skip；报告填统一证据字段。本轮规格复核记录：NotRevalidated，历史状态仅作来源：Queued，未签署Accepted；后续真实状态写入对应队列与acceptance_record。

失败：任一必测用例与预期不符为Failed；缺输入/环境/证据为Blocked；仅完成部分层次为Partial，不升级Accepted。 回滚：回退客户端状态/流程提交，保留未确认结算上下文；不清空服务器资产或重放游标。

### PR13-B12 独立验收、源配置与交付

负责：AG-06。文件：`docs/plans`、`docs/reports`、`.github/workflows`、`config/FantasyCard_Config.xlsx`、`tools/export-config.ps1`。

#### PR13-B12.1 集成来源冻结

输入：code/tool/source/生成包/room policy/seed/策略/网络。进入集成前所需子项：PR13-A08.1。

实施：收集source SHA、配置内容hash与策略版本；原始/派生hash分开，由MAIN核实。

| 检查 | 操作/注入 | 预期结果 |
|---|---|---|
| PR13-B12.1-T01 | 源表与生成包不同步 | Blocked |
| PR13-B12.1-T02 | config版本同但字节不同 | 比较无效 |
| PR13-B12.1-T03 | 候选标签on但room policy off | 实际按off记录 |

通过：code/config/evidence对应同一确定运行输入；candidate标签不能代替有效策略。

执行：OFFLINE、POSTGRES、EXPERIMENT、RENDER、AUDIT；命令入口：C-PLAN、C-BUILD、C-DOMAIN、C-SERVER、C-GODOT-NUM、C-CONFIG、C-EXPERIMENT、C-RENDER、C-AUDIT；关联门：G0、G1、G2、G3、G4、G5。S5：Required，按所列profile取得真实执行证据；历史结果不能冒充当前集成SHA。

交付：`outputs/pr13-acceptance/<integration_sha>/PR13-B12.1/`，包含report/cases/commands/manifest，命令记录退出码及skip；报告填统一证据字段。本轮规格复核记录：NotRevalidated，历史状态仅作来源：Queued，未签署Accepted；后续真实状态写入对应队列与acceptance_record。

失败：任一必测用例与预期不符为Failed；缺输入/环境/证据为Blocked；仅完成部分层次为Partial，不升级Accepted。 回滚：候选切回原策略/原配置；已创建房间沿锁定策略完成；不逆向发放资产或退款。

#### PR13-B12.2 独立off/on和体验矩阵

输入：B02-B11必测、真实PG、多局/资源/控制/顺序。进入集成前所需子项：PR13-B12.1、PR13-A07.4、PR13-B03.4、PR13-B04.4、PR13-B05.4、PR13-B06.4、PR13-B07.4、PR13-B08.4、PR13-B09.4、PR13-B10.4、PR13-B11.4。

实施：独立重跑默认与每candidate及获益组合，真人反馈按skill分层；失效反例回owner。

| 检查 | 操作/注入 | 预期结果 |
|---|---|---|
| PR13-B12.2-T01 | off默认退化 | 候选不通过 |
| PR13-B12.2-T02 | on未跑 | Blocked |
| PR13-B12.2-T03 | 只有bot/headless | 体验Partial不是真人通过 |

通过：当前SHA全部适用层实际执行；每候选有范围/分母/失败/区间，不用历史load CI替代。

执行：OFFLINE、POSTGRES、EXPERIMENT、RENDER、AUDIT；命令入口：C-PLAN、C-BUILD、C-DOMAIN、C-SERVER、C-GODOT-NUM、C-CONFIG、C-EXPERIMENT、C-RENDER、C-AUDIT；关联门：G0、G1、G2、G3、G4、G5。S5：Required，按所列profile取得真实执行证据；历史结果不能冒充当前集成SHA。

交付：`outputs/pr13-acceptance/<integration_sha>/PR13-B12.2/`，包含report/cases/commands/manifest，命令记录退出码及skip；报告填统一证据字段。本轮规格复核记录：NotRevalidated，历史状态仅作来源：Queued，未签署Accepted；后续真实状态写入对应队列与acceptance_record。

失败：任一必测用例与预期不符为Failed；缺输入/环境/证据为Blocked；仅完成部分层次为Partial，不升级Accepted。 回滚：候选切回原策略/原配置；已创建房间沿锁定策略完成；不逆向发放资产或退款。

#### PR13-B12.3 配置生成与版本回滚

输入：source workbook/Exporter/client catalog及room锁定。进入集成前所需子项：PR13-B12.1、PR13-B02.4。

实施：只改受控源定义，经现有export/校验；生成bytes不手改，新房策略锁定，旧房保原。

| 检查 | 操作/注入 | 预期结果 |
|---|---|---|
| PR13-B12.3-T01 | 同源重导 | server/client bytes一致 |
| PR13-B12.3-T02 | 回滚新配置 | 新房旧策略、已存room不静默换 |
| PR13-B12.3-T03 | 禁止候选flags正式on | 默认校验阻止误启 |

通过：源/生成物hash链完整，价格/drop/冻结候选启用须独立决策；资产不倒灌。

执行：OFFLINE、POSTGRES、EXPERIMENT、RENDER、AUDIT；命令入口：C-PLAN、C-BUILD、C-DOMAIN、C-SERVER、C-GODOT-NUM、C-CONFIG、C-EXPERIMENT、C-RENDER、C-AUDIT；关联门：G0、G1、G2、G3、G4、G5。S5：Required，按所列profile取得真实执行证据；历史结果不能冒充当前集成SHA。

交付：`outputs/pr13-acceptance/<integration_sha>/PR13-B12.3/`，包含report/cases/commands/manifest，命令记录退出码及skip；报告填统一证据字段。本轮规格复核记录：NotRevalidated，历史状态仅作来源：Queued，未签署Accepted；后续真实状态写入对应队列与acceptance_record。

失败：任一必测用例与预期不符为Failed；缺输入/环境/证据为Blocked；仅完成部分层次为Partial，不升级Accepted。 回滚：候选切回原策略/原配置；已创建房间沿锁定策略完成；不逆向发放资产或退款。

#### PR13-B12.4 全量最终裁决

输入：LOAD/A/B证据、G0-G5与默认/回滚清单。进入集成前所需子项：PR13-B12.2、PR13-B12.3、PR13-A10.4、PR13-A05.4。

实施：MAIN逐项Accepted/NoChangeWithEvidence/Blocked，原容量与候选体验分开；存在阻塞保持Draft。

| 检查 | 操作/注入 | 预期结果 |
|---|---|---|
| PR13-B12.4-T01 | candidate收益但原容量不足 | G4容量不通过 |
| PR13-B12.4-T02 | 规范完整但未运行 | 执行未验收 |
| PR13-B12.4-T03 | 任何账链未解释告警 | 对应资产门Blocked |

通过：132细项有清楚证据/裁决/风险，未启用不写上线，合并仍由用户决定。

执行：OFFLINE、POSTGRES、EXPERIMENT、RENDER、AUDIT；命令入口：C-PLAN、C-BUILD、C-DOMAIN、C-SERVER、C-GODOT-NUM、C-CONFIG、C-EXPERIMENT、C-RENDER、C-AUDIT；关联门：G0、G1、G2、G3、G4、G5。S5：Required，按所列profile取得真实执行证据；历史结果不能冒充当前集成SHA。

交付：`outputs/pr13-acceptance/<integration_sha>/PR13-B12.4/`，包含report/cases/commands/manifest，命令记录退出码及skip；报告填统一证据字段。本轮规格复核记录：NotRevalidated，历史状态仅作来源：Queued，未签署Accepted；后续真实状态写入对应队列与acceptance_record。

失败：任一必测用例与预期不符为Failed；缺输入/环境/证据为Blocked；仅完成部分层次为Partial，不升级Accepted。 回滚：候选切回原策略/原配置；已创建房间沿锁定策略完成；不逆向发放资产或退款。

## 命令与未实现入口

以下是执行阶段的入口目录，本次只运行C-PLAN文档校验。command为空的条目须先完成指定控制/fixture，再提交真实--help和启动命令；不可猜参数或把未存在的战斗仿真命令写成已执行。

| ID | 工作目录 | 入口/状态 | 用途与约束 |
|---|---|---|---|
| C-PLAN | `.` | `python tools/pr13_plan.py --check`；ImplementedByThisDocumentationUpdate | 只校验文档/JSON/引用/依赖与生成一致性，不执行运行测试。 |
| C-PY | `.` | `python -m unittest discover -s tools/tests -v`；ExistingEntry | Python accounting/process suite；新增case需加入该路径。 |
| C-BUILD | `server` | `dotnet build FantasyCard.Server.slnx -c Release`；ExistingEntry | SDK按global.json；先修B02编译阻塞，不换target framework。 |
| C-DOMAIN | `server` | `dotnet test tests/FantasyCard.Domain.Tests/FantasyCard.Domain.Tests.csproj -c Release --logger "trx;LogFileName=domain.trx" --results-directory ../test-results/pr13-acceptance`；ExistingEntry | 真实Domain/Resolver/Deck/snapshot/pool合同；关键测试不可被filter隐藏。 |
| C-SERVER | `server` | `dotnet test tests/FantasyCard.Server.Tests/FantasyCard.Server.Tests.csproj -c Release --logger "trx;LogFileName=server.trx" --results-directory ../test-results/pr13-acceptance`；ExistingEntry | POSTGRES先设置FANTASYCARD_TEST_POSTGRES为一次性库；记录全套skip，不用现有单匹配filter替代。 |
| C-GODOT | `.` | `& $GodotConsole --headless --path client --script res://tests/run_play_retry.gd`；ExistingEntry | GodotConsole实际位置由工具链manifest记录；网络隔离；同时运行run_gameplay_load_parse.gd。 |
| C-GODOT-NUM | `.` | `& $GodotConsole --headless --path client res://tests/numerical_integration.tscn`；ExistingEntry | 依赖Game的数值/UI测试走真实项目场景，网络隔离。 |
| C-PROTO | `.` | `python tools/generate_network_protocol.py --check`；ExistingEntry | 生成物同步/合同兼容；额外端到端顺序fixture由B02/B10实现。 |
| C-CONFIG | `.` | `pwsh -File tools/export-config.ps1 -InputWorkbook config/FantasyCard_Config.xlsx -ConfigVersion <EXPERIMENT_VERSION>`；ExistingEntry | 在隔离checkout用实验源表；会写生成包，需记录diff/hash并验证默认flags、server/client parity。 |
| C-LIVE | `.` | `python tools/gameplay_load_test.py --run --smoke --smoke-cycles 3 --server-url <AUTHORIZED_URL> --godot <ENGINE_EXE> --prometheus <INSTANCE_METRICS> --max-seconds <FROZEN_LIMIT>`；ExistingSingleClientEntry_ExtensionRequired | 公网添加现有--allow-public-target；当前smoke仅单号，10账号各三局的fixture/控制参数在A09实现后才写真实命令。 |
| C-EXPERIMENT | `.` | 尚需实现/冻结实际步骤；HarnessRequiredByB03 | 现有FantasyCard.Numerics路线命令不能冒充战斗profile；先实现profile/seed/policy/strategy/censor/deadline CLI并登记真实命令与--help。 |
| C-AB | `.` | 尚需实现/冻结实际步骤；HarnessRequiredByA10 | 固定请求/玩法manifest、AB/BA次序、三对、warmup/hold/drain、吞吐/timeout/pending；不臆造当前runner不存在的参数。 |
| C-CAPACITY | `.` | 尚需实现/冻结实际步骤；ControlsRequiredByA02_A10 | 现有group-size/max-groups/group-interval/max-seconds可作启动入口；需补在线/在房时间覆盖/连续hold/尾部验收合同后记录真实启动命令。 |
| C-RENDER | `.` | 尚需实现/冻结实际步骤；ManualScenarioAndFixtureRequired | 真实有界面操作与录屏/截帧、逐状态交互日志；真人外联无授权不自动发送消息。 |
| C-AUDIT | `.` | 尚需实现/冻结实际步骤；RunSpecificReadOnlyProcedureRequired | 每次冻结raw/账链查询/隔离回滚实际步骤；不输出生产连接串或私钥。 |
| C-CI | `.` | 尚需实现/冻结实际步骤；ExistingWorkflows_InspectExactRun | 记录当前集成SHA的run/job/TRX/skip与实际case，新增文件触发路径须补齐；文档CI仅验证规范。 |

## 证据报告与最终关闭

每个阶段report.json至少包含：

`task_id`、`stage`、`integration_sha`、`config_source_hash`、`config_bytes_hash`、`effective_room_policy`、`runtime_image_digest`、`profile_hash`、`algorithm_version`、`case_ids`、`expected`、`actual`、`status`、`sample_population`、`cutoff_monotonic`、`window_or_drain_or_final`、`commands`、`tool_versions`、`exit_codes`、`skip_reasons`、`asset_and_route_postconditions`、`artifact_manifest`、`reviewer`、`rollback`、`remaining_blockers`、`missing_reasons`。

任何拿不到字段必须null并在missing_reasons说明；不写0、推造seed或复制当下context。

raw/账号/密钥只在授权本地artifact；Git提交去敏摘要、fixture、相对名/大小/SHA256。

修改代码/规则/配置/fixture影响相关case，旧证据仅作历史；无运行变更的文档commit可引用runtime_review_sha并说明理由。

MAIN签署每项时给task/stage、证据hash、复跑case、结论/默认值/风险/回滚。Failed/Blocked/Partial必须说明解除条件；NoChange需现行正确且候选无必要/无可靠收益的证据。只有所有适用运行门通过或有效NoChange才可宣称PR13验收完成；完整的规格交付不自动把运行状态改为通过。合并release仍由用户决定。
