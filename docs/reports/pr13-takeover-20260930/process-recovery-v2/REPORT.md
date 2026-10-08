# PR13 独立 OS 服务进程恢复批次

基线源码 `d266d9db6b03e23b3d73f23d03731d02429e0bb6`，生产逻辑与
`cc6da2e7b8a2c7ba46d867af74ce28a58ccfeac3` 相同。独立源码提交
`0f523b86` 只新增 `ProcessLifecycleRecoveryTests.cs`，`e9129643` 仅补 5 行真实 PB 名称断言。
最终运行用 tests `e9129643` 加父任务受审 v2 生产 overlay，patch SHA-256
`66a551c5ff9e586cc00d3b7e6ba3c1531ee96a95d08c9696560f6911f5dbd0d9`。
该组合明确是 dirty 来源，不冒充纯提交或父任务最新 v3。
本目录保留原尝试，不用复跑结果覆盖失败或 skip。

最终 5 项完整 Program host 矩阵通过：5 passed / 0 failed / 0 skipped，耗时 97 秒，
`final-matrix-v2-attempt8/process-matrix.trx`。原 PB500 先单独复跑转绿（1/0/0，8 秒），
再以同一新鲜程序集 `--no-build` 执行完整矩阵。所有实际期望与收据见 `EXPECTED_ACTUAL.json`。

## 已完成的独立结果

| 用例 | 已证明的边界 | 当前结果 |
| --- | --- | --- |
| 既有 host 正控 | 完整 Program host：PVP/遗物/撤离中强杀、重启；默认 PB 准备/READY/入房 | 2 passed / 0 failed / 0 skipped，`existing-db/existing-host.trx` |
| PROC-01 | 持久 Running 夹具经 host 启动、WS resume，强杀后不同 PID 再恢复同 room/match/手牌/RNG，无 settlement | Passed，final v2 |
| PROC-02 | 真实 WS 撤离后同 owner 防具、药剂、金币、holds 和 receipt；两次冷启动、重复 ACK | Passed，final v2；原 P0 红色证据独立保留 |
| PROC-03 | 测试进程先创建持久 Pending hold，完整 host 冷启动提交，第二个 host 仍只一笔 credit | Passed，final v2 |
| PROC-04 | 旧终态收据与快照矛盾时 live 200 / ready 503；旧 actor 不可读，同玩家下一 room WS 可恢复 | Passed，final v2 |
| PROC-05 | 默认 PB 登录/准备/排队、4 真人 READY/入房，共 3 次不同 match；每次首 READY replay，断线终态、ACK replay；实际强杀/重启后 12 条 settlement/ACK、0 Pending、0 活动准备锁 | Passed，final v2 |

PROC-01/02/03/04 的起点是本地独立数据库中的明确持久夹具。它们真实启动完整生产
Program host，使用实际 HTTP/WebSocket/恢复工作器；夹具本身不声称来自 HTTP 入房。
PROC-03 的 Pending 起点来自测试进程中的真实 Repository 事务，并未声称在生产 host 的
某个不可控 await 中截断。PROC-05 的三次是入房和断线终态路线，未执行完整 Boss 玩法。
已有 actor reconstruction 与本批真正的 OS 进程边界分开记录。

## 新发现的 P0

`extraction-red-attempt5` 在第一次默认 PB 查询前，真实 SQL 已确认：+23 Gold、+2 药剂，
同 owner 防具 `Equipped`、Mage loadout 的 Feet 恢复，match `Completed`，1 条 settlement、
4 条 Committed holds、0 条 Pending、1 条 ledger 和 1 次装备 movement。
随后 `/api/v1/matches/{id}/settlement` 返回 500。

实际持久原数据在 `P0-persisted-details.json`：装备 `slot="Feet"`、`quality="White"`、
`element="Fire"`。`protocol/http/v1/game.proto:419` 的 `SettlementEquipment` 三字段为
int32，`HttpDtoMapper.ToWire:218` 对字符串直接 `Convert.ToInt32`，发生 FormatException。
`P0-assets-receipt.json` 保存 SQL 后的原始 receipt；红日志与 TRX 另存。
父任务接管 mapper 生产修复与单元回归，本子任务没有换 legacy JSON 或删除装备绕过。
v2 保留原 numeric 标签 1–3，新增名称标签 8–10。修复后的真实 PB 名称字段保留
Feet / White / Fire / DrawInterval；同一持久 details_json 在三次 startup 字节完全一致，
资产/receipt 不增加，重复 ACK 返回原 timestamp。
`P0-fixed-assets-receipts.json` 和 final `EXPECTED_ACTUAL.json` 保存每次实际 SQL 观察。
父任务随后 v3 追加合法 catalog 的 Red 名称；本子任务未将已跑 v2 证据重标 v3。
最新 v3 的 281 PostgreSQL / 317 Domain 回归由父任务独立负责。

## 尝试记录与来源

初次新鲜构建遗漏 HasDB 环境，两个正控均 skip，保留为非通过记录；设置明确私有连接后
两正控独立通过。18 个旧 bin/obj 目录全部删除；实际基线包含 2427 个 tracked bin/obj
文件，构建输出仍在源码内部，故构建后的 Git dirty 明确为 true。原逐文件状态、程序集
与配置哈希在 `SOURCE_AND_BUILD.json` 和 `build-dirty-status.txt`。

matrix-attempt1 是新测试缺 using 的编译错误。attempt2 为 3 passed / 2 fixture failed：
缺 ExpectedRevision、ACK 键太短。attempt3 为 3 passed / 2 failed：PB500 真实反例，以及
第三组中途遇 429、等待后正确触发 30 秒 bot fill，夹具只剩 2 真人。attempt4 改为整组
入队前等待默认窗口，得到 4 passed / 1 fixture failed（UUID SQL 参数误传 text）。
attempt5 修正 UUID 参数并持久原数据取证，稳定复现真实 PB500。
attempt6 是父任务 v1 patch 的 Wire alias 编译失败；v2 更正后 attempt7 原反例通过，
attempt8 完整 5 项矩阵通过。每个失败阶段仍保留原日志与 TRX。

生产 bot fill 30s、HTTP/WS 默认限流、超时和验收阈值均未改变。
新 child 清空继承环境，只接受 Unix socket 或精确 loopback host，且必须使用 fixture
创建的 `fc_runtime_test_*` schema。CI 的 PostgreSQL service 在 loopback，故 gate 也明确
支持 localhost / 127.0.0.1 / ::1；远端 host 被拒绝。
具体命令、进程 argv/PID/强杀退出码、实际期望/结果、日志、TRX 与失败阶段见
`COMMANDS.json`、`ATTEMPTS.json`、各尝试的 `receipts.jsonl`。

## 映射和剩余范围

`CANONICAL_SUPPORT_MAPPING.json` 明确映射下一队列 9 个 task 的 27 个 canonical case，
均保持 `NotExecutedByThisBatch`、SupportOnly、Accepted=false；父任务的 27 Passed /
369 NotExecuted 计数不由本批自动变更。

尚缺：required 丢失/重连的精确注入、每个 await 的 STOP、缺失/迟到 READY、host 边界的
ACK 已提交响应丢失、旧客户端 callback 和序号精确矩阵、夹失败重试的完整三局玩法、
LIVE 服务器时段/自有账号、RENDER/UI 与真人证据。本批本地进程不替代 LIVE 验收。
`.agents/skills/server_create/SKILL.md` 仍缺失；按用户既有明确例外继续，不假称已读取。

私有 PostgreSQL 只监听 Unix socket；最终停止前随机 schema=0、其他 fixture DB 连接=0。
36 个新 host PID 的 start/stop 收据完整，核对无同一 host executable 仍存活；PG 已停止，
私有 data/socket 目录已删除。清理状态见 `CLEANUP.json`，产物哈希见 `MANIFEST.json`。
