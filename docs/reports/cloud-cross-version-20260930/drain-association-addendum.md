# 排空探针关联缺口追加验证

固定应用输入仍为旧源码 `8489fe97c7da71e1a5bfe1a860faf86fd4e0a4af`、新源码 `cc6da2e7b8a2c7ba46d867af74ce28a58ccfeac3`；只修改独立 harness 和报告。没有修改应用、部署 guard 或 Environment，没有线上操作。真实旧镜像仍不可用，替代物边界不变。

原探针从 `snapshot.players` 出发，再用 `p.settlement_id` 找 receipt，会漏掉整行 snapshot 不存在和玩家关联未同步两类状态。这是**测试/排空提案的证明缺口**，不改变已证实的热回滚风险。原 attempt-6 的 15/58 和追加 attempt-7 的 18/67 全部原样保留。

新版只读探针从 `match_players FULL OUTER JOIN match_settlements` 的 `(match_id, player_id)` 关联出发，不依赖玩家保存的 receipt 指针发现 receipt；再校验该指针与实际 receipt 一致、Settled 状态、snapshot 存在、唯一玩家成员及 terminal phase/result。它检查无玩家对应的 receipt、snapshot 中孤立玩家，以及 hold 的 player_id 与 receipt owner 一致。机器人无需人类 receipt，但仍需合法终态 snapshot；Completed 状态下残留 Active 玩家拒绝；Pending/Held 均视为未完成资产 hold。未知/不支持的终态关系保守拒绝。SQL异常同样中止探针，不能据此放行。

最终 [attempt-8](cross-version/attempt-8/report.json) 为 **22 场景 / 79 次顺序运行**，全部指定观察通过，各阶段 migration checksum/DDL 相等，私有 PG 已停止。四个原有旧版 runtime unsafe 场景仍被复现。新增以下七个关联/阳性对照场景均在同一隔离数据库顺序执行新版、旧版 harness：

| 新增 fixture | 原 SQL | 新检查 | 隔离性 |
| --- | --- | --- | --- |
| Settled 玩家缺整行 snapshot | 错误允许 | 拒绝，association error=1 | snapshot 从未写入；不删除任何历史行 |
| receipt 存在，玩家 Active 且指针 NULL | 错误允许 | 拒绝，association error=1 | receipt 保留，snapshot phase=Extracted，active matches=0、holds=0 |
| 玩家 Settled、receipt 存在但指针 NULL | 错误允许 | 拒绝，association error=1 | 单独证明指针一致性，终态 snapshot 完整 |
| receipt 的玩家没有 match_players 行 | 错误允许 | 拒绝，association error=1 | 已有合法终态与历史保持；另插入明确的孤立 receipt fixture |
| snapshot 中另有无 match_players 的成员 | 错误允许 | 拒绝，orphan member=1 | 正常 receipt/玩家关联不变，仅增加孤立成员 fixture |
| Committed hold 的 owner 与 receipt 不同 | 错误允许 | 拒绝，wrong hold owner=1 | 原 hold/receipt/ledger 保留，Pending=0，单独注入 owner 错配 |
| 完整的 Completed/Settled/Extracted/receipt/Committed hold | 允许 | 允许，所有 error=0 | 使用真实 SettleAsync/CommitHoldsAsync；不是空库对照 |

六个负向场景均为 active matches=0、unresolved holds=0、关联问题=1，避免其他条件掩盖所测缺口。receipt/状态/owner 错配是在新创建的受限 fixture 中明确注入，并非声称正常交易流程自然产生该状态。无 DB restore、无历史删除或修复；数据目录和 0600 私有 dump 留在云工作区且未上传。

这是有界补测，**仍不证明排空 guard 完备**：生产历史的全部状态组合、并发新写入/锁内稳定窗口、Aborted/Removed 等业务关系、线上真实旧镜像/旧数据都尚未完整验收。`drain_guard_completeness_proven=false` 与 `unconditional_application_rollback_safe=false` 同时保留。当前只能继续审阅排空方案，不能启用线上 guard 豁免、热回滚或部署。
