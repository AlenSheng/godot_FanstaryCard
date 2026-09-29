# 2026-09-29 压测修复与优化：多子 agent 实施、主 agent 验收计划

版本：2.1。状态：**Draft / InProgress**。实施起点和当前证据见 [implementation-baseline](../reports/gameplay-load-20260929/implementation-baseline.md) 与 [状态清单](GAMEPLAY_LOAD_EXECUTION_20260929.json)。

前一轮交付是计划与复核记录；2026-09-29 已收到实施指令并开始修改。PR #13 保留首批已有代码，但不得因离线测试通过就把 LOAD-01～03 标记为最终验收完成。实施阶段不合并、不部署、不再次放宽线上限流。

仓库：`AlenSheng/godot_FanstaryCard`。
目标：`release`；复核基线 `28c6c7e7d3898e4d2abd186f53361477ba380330`。
实施汇总分支：`fix/gameplay-load-evidence-20260929`；本轮代码复核点 `50bce18064cdc08e47c3b5aaa30defae75ae526c`。
报告：`docs/reports/gameplay-load-20260929/summary.md`。
复核证据：[PR13 复核记录](../reports/gameplay-load-20260929/pr13-planning-review.md)。
执行状态：[状态清单](GAMEPLAY_LOAD_EXECUTION_20260929.json)。

## 0. 决策与边界

先修证据质量和多局闭环，再分段定位 HTTP 延迟，最后小步实施有收益的优化。不是先扩容、增大连接池/线程池、放宽限流或提高停止线。

本计划保留 11 个父任务，拆成 **44 个子条目**。每个子条目必须交付实现或有证据的不实施决定，由主 agent 验收；未运行、阻塞、条件未满足不得写 Done。所有子 agent 的实际运行 ID 初始为空。

不改变现行战斗公式、卡牌顺序、玩法数值、资产冻结/结算规则；不夹带 HTTP 全改 WebSocket、全量 gRPC 或配置表重构。保留已合入的协议迁移、结算重试/序列化修复，不覆盖其他分支或本地未提交修改。

生产动作单独授权。计划通过不代表允许部署、写生产数据、创建无限量测试账号或重新执行无上限压测。所有默认运行目标应改为明确的隔离环境；指向公网/生产必须显式指定、确认范围，并预设人数/时长/停止与清理条件。

## 1. 已检查的事实与仍缺的证据

摘要记录：每组 50 进程、120 秒间隔、累计 100 客户端曾登录、在房采样峰值 50、累计 29 局含收尾。HTTP P95 连续三个有效窗口 6116/3201/2255 ms 超过 1500 ms 停止线；末次命令 P95 730 ms、CPU 31.53%、可用内存 61.48%、actor wait P95 约 4.76 ms。52 个客户端流程未完成，77 次失败检查含停止期检查，不能互换统计口径。

这些不是本轮新压测结果。report.json blob `61e44c8367303341dd37ae2b8195b7ee1489aa1c` 已定位，但未完整读取/逐客户端重算；完整 JSONL、匹配日志、服务端镜像与客户端当时的确切版本仍需对账。功能修复可先从可复现缺陷推进；性能归因和容量验收不得跳过这项证据。

本轮扩展检查发现：已有统计 helper 仍有畸形输入异常、非所属遥测聚合风险、bootstrap 阶段分类和在房定义缺口；结算轮询会拉取全量 Bootstrap；ready 通知串行发送有慢连接阻塞风险；enqueue 回放 match_id 未按 preparation 关联；无界并行 launch 不是安全方案。详细证据等级见复核记录 F01～F15。

重要修正：服务端先提交 Starting，再通知 match.found/ready_required，所以 match.found 后发送 ready 不必然非法。当前 RoomReadyCommand 为空，ready 事件有 match_id/room_id/deadline，无 ticket_id。计划不得臆造字段或把“发得早”写成已确定根因。

## 2. 子 agent 与文件写入所有权

建议 6 个子 agent，**同时最多 3 个 worker**。每个 worker 使用独立 worktree；共享文件只有一个写入者。角色名称是待分派设计，本轮没有实际启动。

| 角色 | 负责范围 | 独占写入范围/约束 |
|---|---|---|
| MAIN 主 agent | 冻结输入、拆分任务、解决依赖、集成、独立验收、最终报告 | 本计划/状态清单/验收汇总；只有 MAIN 能变更 Accepted、集成到 PR 分支或申请 Ready for review；不以子 agent 自述代替测试。 |
| AG-01 发压器与统计 | LOAD-01～03、07，11 的生成器来源记录 | tools/gameplay_load_test.py、gameplay_load_validation.py、cloud_load_test.py 中明确允许的共用辅助函数；对应单元测试。不得修改真实玩法逻辑。 |
| AG-02 客户端生命周期 | LOAD-04～05、06.2、08.2 | client/tests/gameplay_load_client.gd、client/state/game_store.gd；相关就绪/结算测试。gateway/proto 不得越权写入。 |
| AG-03 HTTP 与遥测 | LOAD-06.1、08.1/08.3/08.4 的客户端部分 | client/network/gateway.gd、必要的新 transport helper/其测试；先遥测后候选优化。共享 header/telemetry schema 必须先确认。 |
| AG-04 服务端匹配与观测 | LOAD-06.3、09、08.4 服务端部分 | Matchmaking/RoomReadyCoordinator.cs、MatchmakingRepository.cs、Bootstrap/BootstrapRepository.cs、Realtime/ConnectionRegistry.cs、RealtimeConnection.cs 及经 MAIN 锁定的指标/结算模块；不默认改部署或数据库 schema。 |
| AG-05 协议与兼容 | LOAD-04/08/09 有协议需求时参与，负责契约验收 | protocol/http/v1 与 realtime/v1、endpoints 清单、生成器/生成物和序列化兼容测试。没有必要的协议变更则提交 NoChangeWithEvidence，不为凑任务修改 proto。 |
| AG-06 独立 QA | LOAD-10、11.3，先设计反例再做集成复测 | 新增 client/tests/load_acceptance/、tools/tests/load_acceptance/、独立服务端验收测试和证据；既有测试需修改时向所有者交接，不与实现者抢同一文件。 |

跨文件协作：AG-03 提出 GET 单飞接口，AG-02 调整调用点；轻量结算接口先由 AG-04 提议、AG-05 定契约，再交 AG-02/03 接入。指标公共文件/Program.cs/项目文件先由 MAIN 显式授权一个所有者。协议生成物只由 AG-05 提交，不能手改生成文件。

## 3. 全量任务与文件级修改方案

各父任务下四个子条目为最小追踪单元；`待实现` 包含对首批代码的补修。优先级 P0 表示阻塞可信验收或正确性；P1 为证据驱动的性能优化与持续治理，不是故障严重性的未经验证结论。

### LOAD-01｜P0｜状态与进程归属｜AG-01｜首批部分实现，待补修/集成验收

前置：11.1 的代码/工具链冻结；不依赖性能剖析。

- **01.1 输入边界**：为状态、PID、时间戳、progress、计数和数组元素做 schema/type/有限值校验；非法数据记录 invalid_schema，不抛异常终止整轮采样。覆盖 None、list、bool-as-int、字符串、NaN、未来时间及重复 ID。
- **01.2 归属统一**：在线、累计周期、遥测都先核对 run_id/client_id/process_epoch/PID。活跃指标仅取存活且新鲜状态；合法已退出进程的最终事件仍可纳入累计值，不能简单丢掉所有死进程历史。
- **01.3 拆分人数**：同时记录 spawned/alive/fresh/online/room_state_clients/active_in_room/server_confirmed_in_room；offline+room 不计活跃战斗。服务器字段采不到就标 unavailable，不捏造；PID 重用以进程 epoch 隔离。
- **01.4 进程回归**：真实轻量子进程覆盖启动慢、成功退出、异常退出、PID 不符、陈旧/缺报、重复/异源状态、时钟跳变；启动宽限按 monotonic 实际启动计。

验收：活跃计数不受历史文件虚增；各类失效可归因；原 22 测试与新负例全过。回滚仅统计 helper/runner，不改业务数据。

### LOAD-02｜P0｜停止、退出与清理语义｜AG-01｜首批部分实现，待补修/集成验收

前置：01.1～01.2；与 AG-02 的周期终态契约一致。

- **02.1 结果模型**：区分 Passed/Failed/Cancelled/InvalidEvidence/PerformanceRedline/Incomplete；保存首个触发、全部触发、证据有效性及清理结果，不用一个 stop_reason 覆盖全部原因。
- **02.2 STOP 时间边界**：记录发出 STOP 的 monotonic 时刻，区分之前的业务失败、之后的正常取消与清理失败。正常取消不计完成也不计服务端错误；不能把异常退出统一洗成取消。
- **02.3 有界清理**：分阶段取消排队/等待结算/关连接；只管理本轮拥有的进程。grace period 到期后强制退出必须记 forced_termination/incomplete_cleanup；finally 写报告失败保留应急摘要，不能返回通过。
- **02.4 自动化兼容**：明确已有退出码 0/1/2/3/130；preparation-only 的 0 不是通过。新增固定时长/固定周期验收模式只有验证合同满足才返回0；更新调用者并加子进程/故障注入测试。

验收：人工停止、红线停止、证据失效绝不变成成功；实际清理异常和停止前失败不可丢失。父任务仅在真实协调器集成通过后 Accepted。

### LOAD-03｜P0｜统计完整性与阶段口径｜AG-01｜首批部分实现，待补修

前置：01.1～01.2；06 的事件字段冻结后完成03.1～03.2。

- **03.1 事件序号**：以 run/client/process_epoch/event_seq 唯一标识，增量读取 JSONL 或带明确起止序号的缓冲；不用 now_unix_ms 当消费水位。检测重复、乱序、缺口、截断和滚动数组覆盖；记录 lost_count 与证据无效原因。
- **03.2 阶段分类**：显式 phase=login/initial/matchmaking/playing/settlement/cleanup。对局/结算中的 bootstrap 保留在相应阶段；旧无标签数据标 unknown/legacy，不推断成明确阶段。保留旧 auth/bootstrap-excluded 口径供对照，但不再将其命名为真实稳定态。
- **03.3 全部结果计数**：HTTP/实时的成功、拒绝、超时、取消、解码错误、开始未完成分别计；非法 duration 不能顺便消除已知请求失败，使用 all_attempt_count、valid_latency_count 和 invalid_count 分开。相同事件不能在 operations/telemetry 双算。
- **03.4 分布与错误率**：错误分子分母同集合；输出 count、逐路由/阶段 P50/P95/P99/max、总吞吐及实际发压率。全场分位数从原样本/可合并直方图计算，不平均窗口 P95；对N<20/空窗口标 insufficient，不声称恢复正常。历史红线算法版本保留用于同口径对照。

验收：同毫秒、跨状态快照、重复、重启和丢行反例可检测；JSONL 与汇总守恒；末窗零错误不能代表全程。其他 cloud runner 的兼容改动单列测试。

### LOAD-04｜P0｜准备确认与进房｜AG-02，AG-04/05 支持｜待实现

前置：11.1、实时 proto/服务端 ready 行为已核对；不以提升 timeout 代替修复。

- **04.1 匹配状态机**：增加明确阶段 Queued→MatchFound→ReadyRequired→ReadySent→ReadyAccepted→RoomStarted，以及取消/超时终态。保存当前 cycle/preparation/ticket；事件使用真实 match_id/room_id/deadline 关联，不以 ready_prompt 非空作为唯一推进条件。
- **04.2 可靠确认**：处理 send=false、连接恢复/冷却期、重复 required、accepted-before-local-send-observed、late required after accepted。重发有次数与deadline上界；不得在已 accepted 时因迟到消息回退、向其他 match 确认，或用无限发送冲过校验。
- **04.3 进房与恢复**：分别测排队、ready等待、accepted→started；使用服务端 deadline 并记录时钟误差；核对 snapshot/resume 恢复路径。room_started 缺失时做有界权威状态恢复，不盲目重置 WebSocket 全局 sequence；房间快照必须属于当前 match。
- **04.4 反例矩阵**：事件重复/乱序/丢失、match.found先到、required很晚、发送失败、accepted后无started、断连/恢复、STOP、第二局旧事件均测试；明确 ready_not_found/ready_timeout 等分类。

验收：可独立复现并证明修复；单账号三局含第二次匹配；不改变15秒ready与bot填充等服务端规则。RoomReadyCommand 目前为空；需要新增匹配关联字段时由 AG-05 走兼容设计，不私塞字段。

### LOAD-05｜P0｜结算、多局与取消闭环｜AG-02｜待实现

前置：04.1；02 的终态合同。

- **05.1 完成依据**：一局只在正确 settlement_id/match_id 的服务端 acknowledge 成功后记 completed；不依据乐观清空的 room/settlement 判断。返回明确结果供驱动使用；失败、busy拒绝和stale-session必须可区分。
- **05.2 状态生命周期**：成功结算后清理ready/ticket/preparation、pending/latest/queued命令、选牌/预览、结算poll句柄和跨局任务；不清同会话全局重放序号。用 cycle epoch/匹配ID拒绝迟到HTTP和WS回调污染新局；失败恢复保持原资源与状态。
- **05.3 停止与清理**：所有 await 等待点检查取消；STOP 导致未进房记 cancelled，不追加 room_started=false；排队取消按权威状态执行，结算中停止保留未确认信息与可恢复证据，清理不能重复结算/领奖。
- **05.4 幂等与循环回归**：ack失败/超时后查询确认状态再恢复、重复ack、重复settlement.ready、旧快照、不同match、重连和三局循环。校验 completed/failed/cancelled/incomplete 守恒且每cycle仅一终态。

验收：无二次领奖、资源增殖、卡死或上一局覆盖下一局；加入已有结算编码与play-retry回归。涉及生产资产异常不得用删数据让测试通过。

### LOAD-06｜P0｜端到端遥测契约｜AG-03/02/04，各写各自文件｜待实现

前置：11.1；MAIN 先冻结遥测字段和单位，再并行写入。

- **06.1 HTTP遥测（AG-03）**：记录 logical_request_id/trace_id、attempt_no、route模板、phase、session_generation、result类型、body_bytes、decode_ms、retry_backoff_ms、总耗时。未完成/超时必须有终态事件；不只记录最终成功。保留 X-Trace-Id 与同一写请求幂等键。
- **06.2 生命周期遥测（AG-02）**：记录prepare/enqueue/required/send/accepted/started/settlement_ready/ack各阶段和cycle/匹配关联，分 transport_progress 与 gameplay_progress；pong/重复快照不能续命玩法停滞计时器。命令发送/拒绝/超时与阶段变化分开。
- **06.3 服务端分段（AG-04）**：trace HTTP处理、数据库连接获取/执行/事务锁等待、claim→snapshot→register→running→started-send，以及命令排队/执行/发送等待。限制指标label基数；player/match/trace ID只进入受控日志/trace，不作为无限增长的Prometheus label。
- **06.4 时间和缺失合同（MAIN+各owner）**：每个耗时以本机monotonic计；UTC用于关联，不用不同机器时钟相减制造精确网络时延。DNS/TCP/TLS/TTFB阶段无法可靠拆分时标 unavailable；外部curl探测单列，不能冒充Godot同一请求。明确采样率、窗口、trace覆盖和脱敏。

验收：能把一个失败cycle关联到请求/服务端阶段；指标单位和起止一致；凭现有API不能测出的阶段不填0；关联ID不泄漏token/票据/私钥/私密正文。

### LOAD-07｜P1（影响证据时按P0处理）｜发压器自身优化｜AG-01，AG-02提供客户端字段｜待实现

前置：01、03与06字段合同。

- **07.1 调度隔离**：健康/Prometheus探测用有界worker和deadline；固定monotonic采样节奏，记录scheduled/actual/startup lag。探测阻塞不得集中补发多组客户端，不能因后台future无限积累引入新泄漏。
- **07.2 发压资源**：记录发压机总/每进程CPU、RSS、活跃进程数、线程/句柄可得值、磁盘吞吐、启动耗时、Godot帧/轮询延迟、实际发包率；固定引擎/启动参数。是否设置headless FPS上限须单独A/B，不能暗中改变0.4秒玩法动作节奏。
- **07.3 遥测写入**：有界缓冲批写JSONL、小状态快照、文件轮转/退出flush；溢出/写失败计lost_count并使证据失效，不丢记录换性能。检查多个Godot进程共享user://session.cfg的启动期写入；需要隔离时在autoload前生效而非_ready后才禁用persist。
- **07.4 压力与故障验证**：模拟慢磁盘、慢探测、时钟跳变、单进程hang、文件损坏、信号终止；同时设置非生产测试的人数/时长上限与独立安全STOP。采样器失败不能继续无监控扩大发压。

验收：采样准时性/证据守恒可量化；生成器资源瓶颈不被误判为服务器容量；维护旧50/120负载对照。

### LOAD-08｜P1｜HTTP与读取优化｜AG-03/02/04/05分工｜有证据后实施

前置：05、06、07达到可解释基线。允许以 NoChangeWithEvidence 关闭无收益候选，但必须有剖析和MAIN裁决，不能跳过任务。

- **08.1 连接复用（AG-03）**：先测新连接比例和网络耗时，再实现按origin/会话隔离的有界连接池或验证过的等效transport。确认底层TCP/TLS被复用，不把复用HTTPRequest节点当证据；单连接不做不受支持的并发。验证连接失效、服务端close、取消、TLS校验、超限响应/解压、401、分页和session generation隔离。
- **08.2 GET单飞（AG-02调用点+AG-03接口）**：相同origin/session/path/参数/缓存版本的只读请求合并；调用方拿真实结果，不能把“正在处理”当成功。写入或版本变化后隔离旧响应。bootstrap/refresh_lobby/inventory读取分别测；不能合并写入或跨玩家缓存。
- **08.3 重试策略（AG-03）**：有界尝试、总deadline、可取消抖动；保留同一逻辑写入的Idempotency-Key；Retry-After为最小等待。解码失败、资产写入不确定、跨会话不能任意重放；A/B保留整体用户等待及每attempt指标。
- **08.4 结算轻量化（AG-04+AG-05契约→AG-02/03接入）**：优先已有settlement_id单项查询；无ID时评审最小只读状态接口/响应，不反复拉卡库/商店/市场/邮件。必须保留玩家鉴权、match约束、Pending asset holds不对外就绪、ack幂等。没有兼容支持时保留旧fallback；不直接删除Bootstrap字段或绕过冻结资产校验。

验收：同接口/同负载/同网络路径对照，记录每局请求/字节、连接新建率、池等待、SQL数与P95/P99；至少三轮成对实验报告离散度。不得预先承诺百分比收益；无明确收益/正确性退化立即回退候选，不删除监控或提高红线。

### LOAD-09｜P1；复现的正确性问题升P0｜服务端匹配与性能｜AG-04｜待定位/定向修复

前置：11.1。09.1～09.2可先做；09.3～09.4的性能改动等06/07剖析。

- **09.1 SQL回放关联**：复现 EnqueueAsync 相同request_id重放、玩家历史多局、不同preparation 情况；match_id须对应返回ticket/preparation，与GetTicketAsync一致。仅修复已证实的关联错误，保留幂等冲突和玩家锁；加入数据库集成负例。
- **09.2 ready/launch恢复**：trace Starting→Launching→Running每段，注入snapshot保存/注册/MarkRunning失败和断线；验证重试不复制房间/扣两次资源、取消者获正确终态。未建立claim lease/fencing前不得增加多个launch worker；区分纯客户端超时和真正服务端卡住。
- **09.3 慢连接隔离**：测NotifyRequiredAsync/LaunchAsync串行发送的等待；如证实队头阻塞，在同match内有界并发或经审查的有界投递，保证每玩家found→required等顺序、event sequence与重放。保留发送上限和关闭保护；不对所有事件fire-and-forget。
- **09.4 热点最小改动**：使用实例/容器与每核CPU、线程池、GC、Npgsql连接等待、慢SQL/执行计划、快照构建/序列化/发送来决定优化。Bootstrap并行扇出、DB批次和快照合并分别A/B；不凭全机均值加连接/索引/机器，不改变房间actor单写顺序。

验收：数据库状态、持有资产、room registry和客户端终态一致；故障注入可恢复；perf修改对应可定位热点和回滚点。schema变更必须独立迁移、锁/回滚审查，不直接生产DDL。

### LOAD-10｜P0｜独立验收自动化与复测｜AG-06执行，MAIN重跑裁决｜待实现/验收

前置：先制定测试，不等待实现者自报完成；执行门控见第6节。

- **10.1 离线及契约**：补F01～F08负例、runner进程集成、统计守恒、退出码、协议未知/可选字段与旧客户端兼容；已有测试不可删除或放宽断言。比较前后生成代码和schema变化。
- **10.2 多局真实闭环**：新增可配置cycle数的本地/隔离smoke，至少同账号三局且按确认结果计完成；覆盖三职业、PVE/PVP相应场景，失败/取消不计完成；已有单局--smoke不能代替本项。
- **10.3 故障矩阵**：发送false、重复/迟到ready、无started、断线恢复、旧match消息、ack失败/重复、pending asset holds、慢客户端、各阶段STOP、生成器进程损坏，逐一记录预期终态和资源校验。
- **10.4 性能复测**：先单客户端测网络基线，再10/50客户端校验，最后保持50/120秒的首两组对照；另设固定目标活跃在房保持期用于容量验证。区分诊断规模与原基线规模；记录累计/当前/在房、实际发压率、完成率、端到端及服务端延迟。未确认生产授权不得运行公网目标。

验收：MAIN必须在集成SHA上亲自重跑关键用例并核对证据；QA pass不是自动发布。压力降低/客户端退出导致P95下降不算优化收益。

### LOAD-11｜P1（基线缺失阻塞比较）｜来源、CI与交付｜MAIN，AG-01/06支持｜部分记录已存在

本任务分前置和收尾，不让整个LOAD-11成为依赖环。

- **11.1 基线冻结（最先）**：读取当前release/PR head、working tree、现有代码与原报告的版本关系；收集完整raw及log清单/hash和测得server image digest/config hash。核对实际Godot版本、.NET SDK与数据库版本。先前SDK10.0.400缺失是已记录阻塞，不通过换target framework掩盖。
- **11.2 来源与脱敏**：加入game_store.gd、proto/生成物、工具配置/关键新增文件的hash；记录dirty含相关untracked、启动参数、功能开关、测试种子、硬件/区域与监控selector。证据不可包含token、票据、密钥；Git只放精简报告和可复现输入，完整日志存授权artifact并附清单/hash。
- **11.3 CI与可重复性**：新增或扩展独立load-test CI覆盖Python、Godot流程/协议与.NET相关测试；报告执行命令、版本、退出码、耗时、跳过原因及artifact。CI路径需覆盖新文件；离线测试不需要生产凭据，不在fork/不可信PR执行生产操作。
- **11.4 PR交付与回滚**：更新任务状态、证据索引、迁移/兼容影响、候选开关、回滚提交与未完成项。只MAIN签署Accepted；任一阻塞保持Draft。关闭未合并PR不影响release；合入后的回滚分别处理代码和迁移，不能声称关闭PR就撤销部署。

验收：任何收益可追溯到确定版本/负载/时间区间；源数据不被新统计覆盖；无未经运行的通过记录。

## 4. 调度顺序与依赖

W0：MAIN执行11.1，冻结遥测/周期合同与文件所有权；AG-06准备反例矩阵。读不到全量raw不阻止纯函数修复，但标记性能/逐客户端归因阻塞。

W1：最多并行 AG-01（01～03/07）、AG-02（04～05/06.2）、AG-04（09.1～09.2/06.3）。合同先冻结；必要时一个实现槽位让给AG-03完成06.1，不能偷偷超并发。同一agent按任务内部依赖串行。

W2：MAIN集成并通过G1/G2后，AG-03做transport/重试候选；AG-02做GET调用点/多局补修；AG-04做服务端热点定位。需要新协议时AG-05占一个槽位先交付契约，服务端和客户端再接入；不让三方同时改生成物。

W3：AG-06在固定集成SHA做独立验收，MAIN复跑、检查diff和证据、处理失败再派回对应owner。只有G0～G5的适用项通过或有证据的NoChange裁决，才结束实施；不自动合并/部署。

每次交接必须包含：task_ids、base/head SHA、changed_files、schema_changes、repro_before、test_commands/exit_codes、artifact_paths/hashes、before_after_metrics、risks、rollback、remaining_blockers。缺证据不得Accepted。

## 5. 共用契约与判定规则

### 5.1 事件最小字段

run_id、client_id、process_epoch、event_seq、cycle_id、phase、event_type、monotonic时间、UTC时间；业务ID只在实际可得时记录；HTTP加logical_request_id/attempt_no/route/result，实时加request_id/response_type。不可得字段为null+原因，不伪造ticket_id/网络分段。

统计维持：started_cycles = completed + failed + cancelled + incomplete/active（按报告时点定义）；HTTP所有已开始请求最终归到success/error/timeout/cancelled/pending。latency_count另计，不能通过抛弃错误样本降低失败率。

### 5.2 连接与会话

一个逻辑写请求的幂等键在transport重试期间固定；不同业务操作不共用键。origin或session_generation变化时旧请求结果不更新新会话。协议/transport改造必须保留消息顺序、资产幂等、响应限制、分页与TLS验证。

### 5.3 遥测窗口与性能

记录window_start/end/count、client/group phase、有效样本量、采样器健康及生成器实际负载。短窗口客户端P95不能直接减5分钟actor P95来计算网络耗时；CPU要说明实例/每核/容器口径。P95只统计已完成会漏掉未完成尾延迟，必须另报timeout/pending和等待年龄。

保留原停止线用于可比重放：HTTP count>=20且P95>1500ms、HTTP错误率>=10%；实时count>=10且P95>2000ms、命令拒绝率>=10%；health失败或>5000ms；CPU>85%、可用内存/磁盘<15%、actor wait>100ms，按原连续3次规则记录。以上为项目诊断停止条件，不是行业标准或正式SLO。

新增安全上限/证据失效停止与旧性能规则分开版本化。样本不足是Unknown而非Pass；不得利用低流量窗口或删除失败样本规避停止。为了保护环境可更早停止，但不得把更早停止的实验伪装成原负载通过。

## 6. 主 agent 验收门

| 门 | 必须检查 | 通过凭证 |
|---|---|---|
| G0 基线/安全 | 来源、工具链、raw缺口、隔离目标、文件锁；没有生产写入授权不启线上动作 | baseline/manifest、阻塞清单、固定SHA |
| G1 离线正确性 | 原22项+新增负例、真实轻量进程、统计守恒、退出码、schema兼容 | MAIN重跑命令/exit0、测试报告；负例先失败后通过 |
| G2 玩法闭环 | Godot同账号至少三局；第二次匹配、ack与资产边界；相关.NET/协议测试 | cycle时间轴、服务端状态、无重复资产、回归日志 |
| G3 可观测性 | trace关联、时间/窗口一致、生成器健康、timeout/pending、数据丢失可检测 | 抽样逐请求/逐cycle对账、脱敏审查 |
| G4 性能/稳定性 | 同口径A/B，实际负载未下降；慢连接和长时间资源回收；原停止线不提高 | 前后报告、三轮成对实验及波动；无收益候选NoChangeWithEvidence |
| G5 交付 | 整体diff无无关改动、候选默认/回滚、CI适用项、证据完整 | MAIN验收结论、未完清单清零或明确阻塞；仍需人工决定合入/部署 |

MAIN不可仅检查文件存在或接受子agent的“测试通过”一句话。至少重跑统计/流程负例、三局闭环、协议与结算幂等关键测试；其余检查真实命令、退出码和artifact。环境不能执行时写Blocked，不能换成静态检查后称实装通过。

已存在可用命令入口：`python -m unittest discover -s tools/tests -v`；Godot `client/tests/run_play_retry.gd`；`dotnet test server/tests/FantasyCard.Server.Tests/FantasyCard.Server.Tests.csproj --filter FullyQualifiedName~SettlementEncodingTests`。新增三局/性能脚本入口由对应任务实现后记录实际命令，不写不存在的启动参数当作已可用。

## 7. 待实现时的主 agent 启动指令

> 阅读本计划、复核记录和状态JSON；检查仓库当前release与PR #13 head、工作树，保留未提交修改。先执行11.1并冻结契约和文件所有权，最多3个worker，各用独立worktree按W0～W3分派。既有LOAD-01～03按部分实现处理，先加负例再修。AG-02只改生命周期，AG-03只改gateway/transport，AG-04改服务端；需要proto由AG-05先出兼容契约。每项交回diff、命令/退出码和证据hash；MAIN在集成SHA独立执行G0～G5。无性能证据不盲目扩容，无生产授权不部署/放宽限流/线上压测。完成后更新草稿PR的逐项状态和验收报告，等待用户决定合入。

上述文字保留为原始交接指令；实施以当前状态清单和实际测试记录为准。未启动的 agent ID 仍为空，不以计划中的角色名称冒充实际执行。

## 8. 本轮记录与历史保留

历史首批4个文件/4次提交已存在，Python纯统计/判定22项通过，并曾做三个Python文件py_compile；没有Godot/.NET/真实协调器或云端压测验收。

本轮在与GitHub blob一致的副本上用Python3.13.5重新运行现有22项，22/22通过；另复现畸形字段异常、阶段分类和offline+room口径缺口，细节见复核记录。没有修改代码消除新缺口，也没有宣称52个流程问题已解决或HTTP P95已下降。

本轮新增/更新：本计划、PR13复核记录、待实施状态JSON、PR正文。所有新增实施项保持Planned/Blocked/Conditional，accepted_by为空，dispatch_enabled=false。PR继续Draft。
