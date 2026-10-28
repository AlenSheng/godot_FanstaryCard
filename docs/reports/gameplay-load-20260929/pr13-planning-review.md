# PR #13 全任务复核与优化证据

日期：2026-09-29。用途：实施前检查；不是新一轮压测结果。
复核代码：`50bce18064cdc08e47c3b5aaa30defae75ae526c`；目标基线：`release@28c6c7e7d3898e4d2abd186f53361477ba380330`。
本轮只更新文档和计划，不修改执行代码，不启动子 agent，不合并、部署或发起线上压测。

## 1. 证据范围

已核对 PR #13 元数据、全部四个变更文件、原 11 项任务、压测 summary，以及客户端准备/进房/结算、HTTP gateway、服务端匹配/ready/Bootstrap/连接发送实现和实时 proto。

GitHub 上 report.json 的已确认 blob 为 `61e44c8367303341dd37ae2b8195b7ee1489aa1c`，文件大小 2,280,577 字节。当前连接的文件读取没有提供完整正文；容器下载也因外网域名解析失败未取得文件。没有逐客户端重算全部原始记录。可见的历史片段不构成完整数据集。下列历史性能数字以 summary 为准；原始 JSON、完整 JSONL 和服务端日志的对账仍是实施前证据任务。

原报告：100 个客户端曾登录、采样在房峰值 50、累计完成 29 局（含收尾）；HTTP P95 连续三个有效窗口 6116/3201/2255 ms；末次命令 P95 730 ms、CPU 31.53%、可用内存 61.48%、actor wait P95 约 4.76 ms。52 个客户端流程未完成；77 次失败检查包含 STOP 期间检查。不能宣称 100 人持续战斗通过、服务器只能支持 50 人，或把全部失败归因于服务端。

`local-release-validation.md` 记录的是先前执行：Godot 15 组 play-retry 测试通过；SettlementEncodingTests 因缺少要求的 .NET SDK 10.0.400 未能启动。本轮没有重跑 Godot/.NET，也没有将历史记录升级为本轮验收。

## 2. 复核中发现的缺口

| ID | 证据等级 | 具体问题与定位 | 处理任务 |
|---|---|---|---|
| F01 | 已离线复现 | `workload_snapshot` 对非字典状态抛 AttributeError，对字符串 last_progress_age_ms 抛 TypeError；`aggregate_window` 在 ok=true 且 status='oops' 时抛 ValueError。已有非法 duration 检查不能代替完整 schema 校验。 | LOAD-01、03 |
| F02 | 已静态确认 | runner 在线计数经过 PID/新鲜度校验，但遥测窗口和 completed_cycles 仍遍历原始 statuses；不能认为首批已解决所有证据归属问题。已退出进程的合法历史事件可以纳入累计值，但必须先核验 run/client/process_epoch 与序号。 | LOAD-01、03 |
| F03 | 已离线复现 | `_steady()` 按 path 永久排除 bootstrap，即便 label='settlement_poll'。这符合当前 helper 的字面定义，却不能代表对局稳定期流量。需要保留旧口径并新增 lifecycle-phase 口径，不悄悄改历史对照。 | LOAD-03、06 |
| F04 | 已离线复现 | online=false、room=true 的新鲜状态可产生 online=0、in_room=1。room 当前只是本地房间状态，不等于连接着的战斗人数。应分 room_state_clients、active_in_room、server_confirmed_in_room；不能仅靠布尔字段认定同时战斗。 | LOAD-01、11 |
| F05 | 已静态确认 | runner 以状态快照 now_unix_ms 推进水位并用严格大于筛选；同毫秒事件和滚动 300 条数组可能造成遗漏。重复/非所属状态也可能污染聚合。 | LOAD-03、07 |
| F06 | 已静态确认 | `_on_event` 连 pong/快照等都会刷新 last_progress_ms；有网络包不等于玩法推进。STOP 后仍可能产生 room_started=false。 | LOAD-04、05、07 |
| F07 | 已静态确认；因果未定 | 驱动只发一次 room.ready 且不检查 send 结果；但服务端 TryCreateMatchAsync 先提交 Starting 状态，再 NotifyRequiredAsync 依次发送 match.found/ready_required。故“收到 match.found 就确认一定太早”不是已证实根因。 | LOAD-04、09 |
| F08 | 已核对契约 | RoomReadyCommand 是空消息；ready 事件有 match_id/room_id/deadline，没有 ticket_id。客户端可用本地 cycle/preparation/ticket 与事件 match_id 关联，不能向空 proto 偷塞字段并假设服务器会校验。 | LOAD-04、协议门控 |
| F09 | 已静态确认；收益待测 | `_poll_ready_settlement()` 每次调用完整 bootstrap；BootstrapRepository.GetAsync 同时启动 decks/cards/core/inventory/shop/market/mail/activePreparation 八个任务，core 又包含多结果集。只等结算也会读其他模块，适合研究轻量查询和读取合并。不能据此认定数据库连接池已经耗尽。 | LOAD-06、08、09 |
| F10 | 已静态确认；收益待测 | gateway 每次 attempt 创建 HTTPRequest，遥测不含完整 attempt/退避/现有 decode_ms。仅复用节点不等于证明 TCP/TLS 复用；须验证底层连接和实际引擎。 | LOAD-06、08 |
| F11 | 已静态确认；影响待复现 | ready coordinator 和通知循环 await 每个玩家发送；RealtimeConnection.SendAsync 单次含发送门等待最多 5 秒。慢连接可能延迟后续通知/launch，不能直接改为无限并发。 | LOAD-09 |
| F12 | 已静态确认；历史命中待复现 | EnqueueAsync 的 request_id 回放分支以 player_id + LIMIT 1 获取 match_id，未像 GetTicketAsync 那样关联 preparation_id。存在历史多局/重试下返回非对应 match_id 的风险；需数据库回归后定向修复。 | LOAD-09 |
| F13 | 已静态确认 | ClaimReadyMatchAsync 提交 Launching 后在事务外建房/注册；已有单协调器路径。直接增加多个 launch worker 可能重复认领 Launching，不能把加 worker 当安全扩容方案。 | LOAD-09 |
| F14 | 已静态确认 | runner 仍串行健康/Prometheus 查询；CPU 查询未按 instance 约束，其他查询取第一条结果；actor_wait 的 5 分钟窗口与短客户端窗口不同。现有 source 哈希列表未含 game_store.gd。 | LOAD-06、07、11 |
| F15 | 已静态确认 | 固定 1/2 秒退避缺少抖动；压测遥测逐条打开/关闭文件并每 5 秒重写滚动数组，100 进程发压机开销需单列。不能从服务端 CPU 推断发压机没有瓶颈。 | LOAD-07、08 |

## 3. 候选优化：先测量，再决定是否实施

| 优化 | 实现方向 | 对照指标与安全边界 |
|---|---|---|
| O01 结算轻量读取 | 有 settlement_id 优先已有单项查询；没有 ID 时评审最小只读查询或轻量状态入口，替代全量 bootstrap 轮询；事件优先、单飞、有限退避。 | 每局 HTTP/SQL 数、返回字节、连接等待、ack 延迟；必须保留 asset hold 完成后才可见、玩家鉴权与结算幂等。 |
| O02 真正的连接复用 | 按 origin/会话隔离的有界 HTTPClient 连接池或经实际引擎验证的等效 transport；保留旧实现可切回。 | 新建连接率、TLS/网络阶段、逐路由 P95/P99、池等待；不能牺牲 TLS 校验、响应上限、分页、401 清会话或原有写入幂等键。 |
| O03 重复读取合并 | 同会话、同路径/参数、同缓存版本的 GET 共享结果；收到写入或版本失效后拒绝旧结果覆盖；不同玩家绝不共享私有缓存。 | GET 数/响应字节与大厅状态新鲜度；不合并不同幂等键的写请求，不将“请求正在处理”伪装成功。 |
| O04 重试去同步 | 同一逻辑请求保留幂等键，有限次数、总 deadline、可取消；抖动不得早于 Retry-After 最低等待。 | 重试放大倍数、重试并发峰值、用户端总延迟；不能只统计最后成功 attempt。 |
| O05 采样与发压隔离 | 有界后台探测、单调时钟、按真实启动记录负载；JSONL 缓冲批写并限内存/文件尺寸，异常时记录丢失量。 | 实际发压率、采样延迟、Godot 帧/轮询延迟、磁盘 I/O；不丢证据换性能。 |
| O06 慢连接隔离 | 优先测 per-player send wait；必要时在一个 match 内有界并发发送，不改变每个玩家的事件顺序/重放。 | ready→started、通知队头阻塞、正常玩家受慢玩家影响；保持 16 KiB/32 pending sends 等保护。 |
| O07 服务端小步优化 | 对明确的 Bootstrap 扇出、SQL 热点、快照构建/发送做分段 trace；只改有证据的热点。 | 单核/容器限额、GC、DB 等待、命令执行与队列分开；不凭全机平均 CPU 加线程/实例/索引。 |
| O08 准确的容量口径 | 登录、排队、就绪、活跃战斗、结算分别计；固定在房活跃人数保持期，记录实际命令发送率和完成率。 | 累计登录量不作为 CCU；故障/退出导致发压下降时，延迟变好不算容量提升。 |

HTTPClient 可在一次连接上发多次请求、单个 HTTPRequest 不应承担同时请求的依据为 Godot 官方文档。实施时必须以项目实际引擎版本核对，不把 stable 文档视为部署版本证明：
`https://docs.godotengine.org/en/stable/classes/class_httpclient.html`
`https://docs.godotengine.org/en/stable/classes/class_httprequest.html`

## 4. 本轮实际检查结果

使用上一轮附件中四个文件的字节副本，并逐个计算 Git blob SHA1，与本次 GitHub 返回的 blob 比对一致后，运行离线测试。不是从未核实的附件推断远端状态。

| 文件 | 核验 blob |
|---|---|
| tools/gameplay_load_validation.py | d31430e4bfc8d6b5f4b3d96ef3ee7394ea14d39b |
| tools/gameplay_load_test.py | 44b9f1590285966e771c2f4f3418222297e80d3f |
| tools/tests/test_gameplay_load_validation.py | fc5309472f7a5bcec7cabfe156769df9f6773b36 |
| 原计划文件 | badd7b28dee392a062e0057743b053b84091d175 |

Python 3.13.5，`python -m unittest discover -s tools/tests -v`：22/22 通过。另用直接函数调用复现 F01/F03/F04；未修改 helper 来消除这些缺口。示例：

```python
aggregate_window([{'operations':[{'duration_ms':1,'status':'oops','ok':True}]}])
# ValueError；应改为 invalid_schema 分类，并保留错误样本计数。
workload_snapshot([owned_process], [None], now_ms)
# AttributeError；应被输入校验拦截。
```

已有 22 项通过仅证明原有用例通过，不代表所有父任务完成。新的负例必须成为后续回归用例，由主 agent 在集成提交上独立重跑。

本轮没有完整 raw 对账、Godot/.NET 测试、真实协调器进程回归、网络阶段剖析、生产压测或性能收益实测。检查到的协议与性能风险不等同于已发生的线上根因。

## 5. 源码锚点

固定复核提交下：`tools/gameplay_load_test.py::main/metrics`；`tools/gameplay_load_validation.py::workload_snapshot/aggregate_window/_steady`；`client/tests/gameplay_load_client.gd::_run_expedition/_on_event/_on_telemetry/_finish`；`client/state/game_store.gd::_on_event/_poll_ready_settlement/acknowledge_settlement/prepare/enqueue`；`client/network/gateway.gd::_request_page/_decode_http_response/_save_session`；`protocol/realtime/v1/realtime.proto::RoomReadyCommand/RoomReadyRequiredEvent`；`server/src/FantasyCard.Server/Matchmaking/MatchmakingRepository.cs::EnqueueAsync/TryCreateMatchAsync/ClaimReadyMatchAsync/MarkReadyAsync`；`RoomReadyCoordinator.cs::NotifyRequiredAsync/LaunchAsync`；`server/src/FantasyCard.Server/Bootstrap/BootstrapRepository.cs::GetAsync/GetCoreStateAsync`；`server/src/FantasyCard.Server/Realtime/RealtimeConnection.cs::SendAsync` 与 `ConnectionRegistry.cs::SendIfConnectedAsync`。

下一步以 `docs/plans/GAMEPLAY_LOAD_REPAIR_20260929.md` 的 44 个子条目实施；本 PR 继续 Draft，等待实现指令。
