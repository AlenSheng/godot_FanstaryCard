# PR13 云端接管当前收据

MAIN 已签 16 项，新增 LOAD-02.2 `Accepted/NoChangeWithEvidence` 绑定原源 `dfb3f88a73efd85cc4ed12b8d49038bebbb1f953`，独立审查 `bcc3c1c7b6764149fccd64d52ade47a1afee374a`。此前 15 项的来源、profile 和 S6 未改写。[新增裁决登记](MAIN_S6_two_ready_20261001.json)同时保留 A05 的独立失败；ROOT 没有代签。

当前代码候选是 `0d4ec7f23df806da7a86f9d954033a718349de7e`，基于 controller 正常集成 `419961a8` 和 release `65361bcc27c51c28651c86c5dbba4f083a9b39e0`。这一提交只改测试 relay 的 Unix/TCP 上游连接：既有本地目标限制、事务丢回复规则、断言、10s/30s 和 180s 窗口均保持。没有新增业务、UI 或 workflow 修改。

真实隔离 Program/Godot/PG 的 Unix 两例、TCP 两例分别 `2Passed/0Failed/0Skipped`。两种连接均实际覆盖提交前失败和提交后丢回复；同 ACK 重复三次、23gold/2potions、原装备 owner/Equipped、单次 ledger/movement 及四个最终只读审计通过。442 私有文件 26,632,169 字节逐 SHA 匹配，967 固定源码和 167 新编译产物核对；六对 host 启停、四 relay 目录和本 task PG 已清理。[去敏报告](a05-relay-0d4ec7f2/report.json)、[重放](a05-relay-0d4ec7f2/REPLAY.md)、[只读原始索引](a05-relay-0d4ec7f2/PRIVATE_ARTIFACT_MANIFEST.json)。原 raw/构建仅本地保留。

同候选一次自动 CI 已终态：4 workflow 成功、Gameplay 失败，无 rerun。CI 实际 checkout 合成提交 `36f0a7b7a17e22968f36d6be49fe9d110f8098d5`，父提交为 release653 和候选0d4e；client/server/tools/workflow 字节与0d4e相同。完整 acceptance 为 Domain317/0/0、Server302/0/0；Gameplay PG 为301/1/0，Windows offline 为206/0/96，Python122通过。两 Linux 全套里的 A05 事务故障两例都通过。[CI终态及真实时长](a05-relay-0d4ec7f2/CI_TERMINAL.json)保留不同分母，未相加作 canonical 覆盖。8 jobs 实际时间总和51.15分钟，计费分钟未知；额外 budget$0/StopYes 未改。

Gameplay 的新失败是 LOAD02 T01 在 `ProcessLifecycleLoad02TimeoutStopTests.cs:60` 读到空的 `.stop-observed.json`。原 Godot observer 先创建最终文件再写/关闭，C# 只等待 File.Exists；保留产物最终为1877字节合法 JSON，partition 为 started1/failed1，其余0。另一完整 acceptance 同源该例通过，不能替代 Gameplay 失败。这是新候选的收据发布/读取窗口，未修改原 MAIN 的 dfb3 裁决。最小后续方案为同目录临时文件关闭后原子发布，并在真实三窗口重验；当前仅定位和提出方案，没有应用或无效重跑 CI。

A05.1 当前为 Partial。原 ROOT62772 全套299/0/0、MAIN独立三个 canonical/guard/MN/ACK/资产通过均保留，但 MAIN 完整298/1/0在 MarkRunning line75期望Running、实际Launching；同源单项通过及新CI该例通过均不关闭首次失败。[只读因果与最小实测计划](a05-relay-0d4ec7f2/MARKRUNNING_READONLY.json)明确假设尚未动态确认，等待父任务分配，未改生产或该代理。LOAD03.3/.4 telemetry 未启动；B06/B03 的另一个冻结离线报告仍在独立本地分支，没有混入本修复。

132 项当前 16Accepted/41Partial/72NotRevalidated/3Blocked；选定19项16Accepted/3Partial，无 Ready；48 case 由 MAIN 原源裁决，G0–G5未签署。[登记](register.json)、[逐项清单](TASK_CHECKLIST.md)、[case映射](CASE_MAPPING.json)、[下一队列](NEXT_QUEUE.json)一致。历史27 runner回执、dirty/多cohort/容量失败、50/100历史raw缺口和全局ledger mismatch=1保持，owned审计不关闭全局异常。历史收据与日志未覆盖。

四份原始模拟 ZIP 已获保存到本人私有 Library 的明确授权。本轮按批准流程再作一次有界尝试，仍在返回 ID 前报 network；累计三次均没有 ID，原31,096,278字节及四 SHA未变。[最新失败收据](RAW4_LIBRARY_RETRY2_20261001.json)。没有另换目的地或自动连续重试。server_create mandatory技能实际缺失按已授权例外记录；没有测试服操作、部署、release/main写入、PR合并或数据库恢复。
