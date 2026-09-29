# 2026-09-29 真实对局压测：诊断、修改建议与执行计划

状态：第一批压测统计/判定修复已实现并通过离线单元测试；Godot 对局闭环、HTTP 优化与同负载复测待执行。

基线：`AlenSheng/godot_FanstaryCard`，`release@28c6c7e7d3898e4d2abd186f53361477ba380330`。
修复分支：`fix/gameplay-load-evidence-20260929`。不直接修改 release，不自动合入、部署或扩大线上压测。
报告入口：`docs/reports/gameplay-load-20260929/summary.md`。

## 1. 已读证据与边界

已读取上述报告摘要，以及 `tools/gameplay_load_test.py`、`tools/cloud_load_test.py` 的相关实现、`client/tests/gameplay_load_client.gd`、`client/state/game_store.gd` 和 `client/network/gateway.gd` 的相关函数。

本轮 GitHub 文件接口没有返回大型 `report.json` 的完整正文，未逐客户端重算原始事件。下面的本次压测数字来自已上传的 summary，不是本轮再次运行得到的数据；没有读取云端匹配日志或完整链路追踪。不能将静态风险直接等同于 52 个客户端失败的全部根因。

摘要记录：每组 50 个真实 Godot 进程、间隔 120 秒，启动两组共 100 个客户端，100 个曾成功登录；采样在房峰值 50；累计完成 29 局，包括收尾。HTTP P95 连续三个采样为 6116、3201、2255 ms，越过 1500 ms 停止线。最后采样实时指令 P95 730 ms、CPU 31.53%、可用内存 61.48%、房间排队 P95 约 4.76 ms。最后采样的 HTTP 失败率和命令拒绝率为零，不代表整场全部检查无失败。

52 个客户端报告未完成已确认结算；77 次失败检查包含停止期间未进房检查，不是 77 个独立失败账号。摘要明确临时放宽限流已恢复；本轮没有重新设置限流。

结论：这是 HTTP 延迟红线及负载闭环/证据质量问题，不能据此宣布服务器只能容纳 50 人，也不能宣布 100 人持续同时战斗通过。CPU 和房间排队末次数据不足以定位算力上限、数据库瓶颈或排除瞬时阻塞。

## 2. 原因分析与修改原则

### 2.1 已确认的统计问题

原协调器直接对所有 status 文件的 online/room 求和，没有校验进程存活和状态新鲜度。已退出客户端可保留旧在线标志；成功退出的旧 status 后续又可能被计入 stale。缺报宽限按分组计划时间计算，而不是实际启动时刻。

原协调器对所有 `redline:` 和 `operator_` 停止返回 0；其中包含 workload_or_generator_failure。退出成功与验收通过没有分开。它对这一类停止仍保留原因字符串，并非完全没有错误记录，但仅看进程退出码的自动化可能误判。

共享聚合器的 steady_error_rate 使用全部 HTTP 错误数除以 steady 请求数，分子分母不属同一集合；无 label 的鉴权/bootstrap 请求又可能被当作稳定态。共享聚合器还按路径忽略部分 context 404。新的 gameplay 聚合器不再做隐式 404 豁免；其他 cloud runner 暂未迁移。

### 2.2 进房和第二局：静态风险已确认，运行时因果待验证

Game._on_event 将 match.found、room.ready_required、room.ready_accepted 都写入 ready_prompt；压测驱动看到非空 ready_prompt 后只发一次 room.ready，并忽略 send 的返回值。因而它没有区分“匹配已找到”“此时允许确认”“确认已接受”。匹配事件先后顺序、发送失败或重放下，有提前发送或后续不再确认的风险。

不能仅把等待 30 秒改为更长便宣布修复。应保存 cycle_id、ticket_id、match_id、ready 状态和时间轴，核对服务端从确认到 room.started 的事件链。同一会话不能盲目清空 WebSocket 重放序号，否则会引入新的顺序问题。

停止时，驱动等待循环退出后仍可能追加 room_started=false。应将操作取消单列，不能算成服务端失败，也不能算成完成局。

Game.acknowledge_settlement 在 HTTP 确认之前先清空部分本地状态，失败后恢复；因此回归测试必须覆盖确认失败/重试和迟到事件，不能只检查瞬时 room 为空。ready_prompt 和周期状态需要有显式生命周期约束，但是否为本次二次匹配主因仍需证据。

### 2.3 HTTP：先分解，再优化传输

Gateway._request_page 每次尝试都新建 HTTPRequest，最多三次尝试；总耗时覆盖请求、重试等待和解码，输出 telemetry 只有整体 duration/status/ok 等，未输出每次尝试耗时或现有 decode_ms。当前数据无法区分连接建立、公网传输、重试退避、服务端处理与客户端解码/调度。

连接复用、合并重复 bootstrap/缓存刷新可作为候选，但必须按相同接口、连接条件、配置和负载做 A/B。不能直接把 HTTP 改成 WebSocket，不能增大超时或提高 P95 停止线掩盖问题。扩容必须以分阶段剖析为依据。

### 2.4 发压器和采样仍有待修项

协调器串行执行健康探测和多个 Prometheus 查询，实际采样间隔不保证 10 秒；当前第一批已补充 observed_interval_seconds/sample_collection_ms，但尚未改成异步采样。

驱动每次网络事件都刷新 last_progress_ms，因此网络仍有包不等于玩法有进展。应将 transport_progress 与 gameplay_progress 分离。滚动数组和按毫秒水位去重仍需序列号/完整 JSONL 对账，避免同毫秒或高吞吐窗口遗漏。

## 3. 详细任务清单

| ID | 优先级 / 状态 | 修改范围 | 具体交付与验收 |
|---|---|---|---|
| LOAD-01 | P0 / 首批实现 | gameplay_load_test.py、gameplay_load_validation.py | 在线/在房只计所属存活 PID 的新鲜状态；成功退出不算 stale；缺报宽限使用真实启动时间；死进程、缺报、陈旧、停滞分列。离线回归通过，仍待真实进程集成测试。 |
| LOAD-02 | P0 / 首批实现 | 同上 | 明确 outcome.classification/passed/exit_code，性能红线、负载失效、人工停止不能标验收通过；保存停止前后进程退出状态、清理异常。验收：负载失败优先于容量归因。 |
| LOAD-03 | P0 / 首批实现 | 新聚合器、tests | steady 错误分子分母同集合；兼容无 label 的鉴权/bootstrap 排除；空样本不伪造 P95；拒绝非法耗时；不重复计 HTTP telemetry。其他 cloud runner 不在本批修改范围。 |
| LOAD-04 | P0 / 待实现 | gameplay_load_client.gd、必要的 Game 状态接口 | 事件驱动准备状态机：Queued→ReadyRequired→ReadySent→ReadyAccepted→RoomStarted；send 失败可重试但必须有上界，业务接受不得误计为进房；绑定当前 ticket/match/cycle，忽略跨局旧事件。先核实事件字段契约，不臆造协议。 |
| LOAD-05 | P0 / 待实现 | gameplay_load_client.gd、Game.acknowledge_settlement | 结算确认成功后才完成周期；失败恢复可继续处理；停止、取消、就绪超时、进房超时、结算超时单列；核查下一局前 pending/ready/ticket 清理。每个 cycle 只能有一个终态。 |
| LOAD-06 | P0 / 待实现 | 客户端/服务端遥测 | 以现有 X-Trace-Id 关联逻辑 HTTP、每次 attempt、状态码、重试/退避、响应字节、decode_ms；记录 enqueue→ready_required→accepted→room.started→settlement→ack 时间。不得记录令牌、SSH 密钥或请求私密正文。 |
| LOAD-07 | P1 / 待实现 | 协调器、遥测文件 | 发压机 CPU/RSS、进程数/启动耗时、事件循环延迟；探测异步化并有超时；单调时钟驱动调度；主循环不因探测阻塞批量补发；每条遥测加序号并以 JSONL 对账。 |
| LOAD-08 | P1 / 条件实施 | gateway.gd、bootstrap/缓存调用点 | 先测连接建立和每路由耗时；仅在证据成立后做有界连接复用或读取合并。按会话隔离，保留鉴权失效、幂等键、取消、body 上限、分页与重试语义。无收益或正确性退化即回滚。 |
| LOAD-09 | P1 / 待定位 | 服务端匹配/实时/持久化模块 | 关联实例级 CPU、线程池、GC、数据库连接等待/慢查询、房间队列和匹配日志；只有热点证据成立才改相应代码。先定位实际文件，不凭报告臆造类名或 SQL 瓶颈。 |
| LOAD-10 | P0 / 待验收 | Godot 自动测试与真实压测 | 单账号至少连续三局，覆盖第二次匹配；加入迟到/重复 ready、发送失败、断线、ack 失败、阶段 STOP；再按相同 50/120 秒负载复测。当前 --smoke 仍仅一局，须新增多局入口后才能覆盖循环验收。 |
| LOAD-11 | P1 / 部分实现 | 报告与发布检查 | 首批已有客户端 Git 提交、已跟踪文件 dirty 标志、关键源码 SHA256、Python/OS；补服务器镜像 digest、引擎版本、配置 hash、实际采样区间。原报告只读保存，复测新建目录；不以本轮新统计覆盖历史结果。 |

## 4. 依赖、分工和实施顺序

先完成 LOAD-01～03，使结果可解释。随后流程修复（LOAD-04～05）和观测（LOAD-06～07）可并行；同一 Game/gateway 文件只允许一个实现者写入。取得剖析证据后，再进入 LOAD-08～09，最后 LOAD-10～11 汇总验收。

建议角色：A 负责驱动/匹配闭环，B 负责 HTTP/发压机观测，C 独立做回归与报告。角色是任务分工建议，本轮没有启动或伪称启动 Codex 子 agent。每个任务提交 diff、运行命令、退出码、证据路径和回滚说明；未运行的测试标明未运行。

## 5. 验收与复测

第一道门：离线统计/判定回归全部通过，不允许将人工 STOP 或 workload_failure 判作通过。
第二道门：隔离测试环境单账号至少连续三局完成真实结算确认；注入的取消不是失败也不是完成；迟到事件不能推进下一局。仅一次 smoke 通过不够。
第三道门：同硬件、同引擎、同配置、同公网路径、同 50/120 秒负载；保留既有 HTTP P95 1500 ms 连续三次等停止线，不因失败调高红线。临时放宽限流需要单独明确授权并具备恢复验证；本代码不设置限流。

必须同时报告累计登录、存活进程、当前新鲜在线、当前在房、已确认完成周期、取消周期、失败周期，并区分登录/初始读取/稳定态 HTTP。最后一个窗口的零错误率不能替代整个过程的成功率。性能门槛是项目本次停止条件，不是行业标准，也不等同于已经确定的正式 SLO。

退出码兼容性：未启动测试的 preparation-only 保持 0；实际测试只有已验证 smoke 使用 0；不完整/失败 1、性能红线 2、负载或证据无效 3、人工停止 130。下游自动化需要读取 outcome，而不是继续把所有受控停止视作通过。

## 6. 本轮实际执行记录

修改/新增：
- `tools/gameplay_load_test.py`
- `tools/gameplay_load_validation.py`
- `tools/tests/test_gameplay_load_validation.py`
- 本计划文件

已执行：Python 3.13.5 下 `python -m unittest discover -s tools/tests -v`，22/22 通过；三个 Python 文件 `py_compile` 通过。测试使用虚拟进程对象验证纯统计/判定逻辑，没有联网、没有启动 Godot，也不是完整协调器或服务端性能验收。

尚未执行：Godot 编译/多局闭环、完整真实协调器运行、.NET 测试、云端同负载复测、HTTP 连接复用或服务端性能代码修改。不能据此宣称 HTTP P95 已下降、52 个客户端问题已修复或容量提高。

回滚：第一批改动只在独立分支，保持草稿 PR；直接关闭未合入 PR 即不影响 release。后续合入时可按提交回滚统计工具及 helper/tests，不需要数据迁移。没有修改生产限流、数据库、GDD 战斗公式或正式部署。
