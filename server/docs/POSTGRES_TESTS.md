# PostgreSQL 集成验收

`FantasyCard.Server.Tests` 的 `PostgresIntegration` 分类使用真实 PostgreSQL。
环境变量 `FANTASYCARD_TEST_POSTGRES` 必须指向专用测试数据库；不要使用生产连接。
连接账号需要创建/删除 schema 的权限。连接字符串不提交到仓库。

2026-09-10 最终结果：服务测试 **157/157 通过，0 失败、0 跳过**；Release 构建 0 警告、0 错误。该数字是整个 `FantasyCard.Server.Tests` 项目的数量，不是仅 PostgreSQL 分类数量。本轮使用独立数据库 `fantasycard_gameplay_test`，包含最后的地图分组、匣灵实例元素与实时消息更新；领域测试另为 202/202。可查仓库根目录 [gameplay-final.trx](../../artifacts/gameplay-validation/gameplay-final.trx)。最终核验无遗留测试 schema，测试创建的服务进程全部退出。

从 `server/` 运行：

```powershell
dotnet build src/FantasyCard.Server/FantasyCard.Server.csproj -c Release
dotnet test tests/FantasyCard.Server.Tests/FantasyCard.Server.Tests.csproj -c Release --filter Category=PostgresIntegration
```

完整服务回归不加分类过滤：

```powershell
dotnet test tests/FantasyCard.Server.Tests/FantasyCard.Server.Tests.csproj -c Release --logger "trx;LogFileName=gameplay-final.trx" --results-directory ../artifacts/gameplay-validation
```

真实进程用例默认启动 `src/FantasyCard.Server/bin/Release/net10.0/FantasyCard.Server.dll`。若为避开本机旧 DLL 映射占用而使用独立 `bin/obj` 输出，可设置 `FANTASYCARD_E2E_SERVER_DLL` 为同一轮新编译服务 DLL 的绝对路径；不能拿旧服务程序集验证新协议。本轮最终验证使用独立输出目录，未覆盖开发服务的运行文件。数据库连接值只注入测试进程环境，不打印或写入测试报告。

未设置环境变量时用例显示 **Skipped**，不是验收通过。
配置连接后不可达、权限不足或迁移失败均导致测试失败。

测试在随机生成的 `fc_migration_test_<uuid>` / `fc_runtime_test_<uuid>` schema 中执行，覆盖：

- 两个迁移器并发启动，验证迁移锁和迁移记录数量。
- 再次启动，验证迁移记录（含 applied_at）完全不变。
- 修改测试 schema 的 V001 校验和，验证启动拒绝且不自动覆盖篡改记录。
- 同一外部身份 8 路并发首次登录，只生成一个玩家聚合，并完整补齐钱包、材料、消耗品、200 张图鉴卡（其中 51 张初始解锁）、三套编组/穿戴与三把专属武器。
- 旧版 identity 三表原地升级后，已有玩家首次登录幂等补齐聚合，重复登录不重复资产。
- V013 将旧卡 ID 与卡组引用原地迁移为规范 ID，并把卡牌品质约束扩展到橙卡 rarity=5。
- 同版本卡组并发写入只有一个成功，失败方得到版本冲突；成功请求可按 `Idempotency-Key` 回放原响应。
- 卡牌升级逐一验证四种魂分账、等级和品质保持、当前/下一等级效果、同键重放与冲突、余额不足回滚，以及并发同键只扣一次。+4/+5 仅消耗所有已保存职业编组以外的多余同名卡；+5 拒绝继续升级。准备快照冻结每个槽的等级，同名重复槽只给一张养成等级，后续大厅升级不改变已有准备。
- 探索准备并发重试只创建一份预留；同键改请求被拒绝；所选装备只锁为一次 `PreparationLocked`，主动取消可重复调用并原子恢复 `Equipped` 与活动准备占用。
- Bootstrap 返回完整大厅聚合，并保持未完成房间/结算为空时的兼容形状。
- 完整库存读取返回背包与已穿戴装备属性、50 格摘要和药剂/高级包/顶级包数量；按职业读取配装保持固定五槽顺序。
- 同一市场挂单由两个买家并发购买时只允许一个成功；验证失败者不扣金、买家只扣一次、卖家只到账一次、10% 手续费、装备只转移一次，并核对交易、账本和库存移动审计。
- 市场列表的嵌套 `equipment` 对应真实装备部位、品质、等级、绑定、位置、元素和词缀；校验其与持久装备记录一致。
- 商店购买验证同键重放、同键改请求、日限、余额不足与高级/顶级探索包合计 3 个仓库上限；所有拒绝路径都不扣金、不发货、不写购买/账本，成功金币流水关联 requestId。
- 每日单卡商店验证两个仓储实例并发建档仍得到同一 resetKey、三张不重复报价和总计 12 个商品；逐档价格/限购来自统一配置包，购买后只增加指定卡一次，同键重放不重复发货，超限回滚。跨日生成新档；随机礼包必须使玩家卡牌复制总数实际增加 3，防止旧卡 ID 静默零行更新。
- 紫色防具 +4 验证碎片不足时目标、绑定同品质材料、幂等记录和审计全部回滚；补足碎片后只消费一次材料，重放不再次扣除，库存移动与碎片流水关联 requestId。
- 红色防具 +4 验证橙装材料被拒绝且不扣碎片，只有红装材料能被消费；该测试使用直接注入资产验证未来规则，不代表当前原型开放红装投放。
- 专属武器 +1 验证碎片不足完整回滚，补足后只扣碎片、不产生材料库存移动；成功响应可重放且流水关联 requestId。
- 强化报价验证护甲成本、可用同品质材料数量与实际扣除一致，专武 +1 至 +5 报价为 8/16/32/64/128 且不需要材料，满级不再报价升级。低级防具附带多余材料、试图消费他人装备和强化局内锁定装备均被拒绝，资产保持不变。
- 四名真人从 preparation、enqueue、Ready 贯通到首份 `room_snapshots` 和 `matches.status=Running`；重复 enqueue 不新增 ticket，同键改 preparation 被拒绝。
- 两名真人排队不足四席时，首票满 30 秒才成组；Ready 满 15 秒后未确认真人转 Removed、preparation 取消，已确认真人保留并由三个机器人补到四席启动。
- 四真人开房同时验证穿戴装备从 `PreparationLocked` 转 `InMatchEquipped`、带入药剂在同一事务扣除、高级包保持逻辑预留，并写入 `match.start` 库存移动审计；Ready 超时剔除者的装备恢复 `Equipped`。
- 撤离结算验证背包装备、穿戴装备、新生成装备、从遗物堆拾取的已落库生成装备、金币、勇士魂、职业魂、装备碎片和药剂九个 hold 原子提交；重复结算与重复 commit 不会重复入账，穿戴件恢复 `Equipped`，全部 hold 提交后 outbox 才可见，发布确认后不再投递。
- 结算批次含非法资产时验证整批回滚：钱包与账本不变、全部 hold 保持 Pending、outbox 不提前发布，后台可继续重试。
- 死亡结算验证穿戴防具转为 `RelicPile`、从职业配装槽解绑、付费包只在此时消耗，并写入 `settlement.death` 库存移动审计。
- 局内换装结算验证新生成穿戴防具、脱下的旧防具与被回收装备在同一可回放事务中提交；非法最终配装使生成装备、金币和全部托管整批回滚。拾取者不能冒领死者尚未提交的奖励装备，死亡归属提交后才能按真实装备继续换装/结算。
- Running 房间恢复验证从 PostgreSQL 最新快照重建 RoomActor、玩家与 matchId 映射；按 `updated_at` 将 16 秒停机时长以 10Hz 权威 tick 补偿，使 15 秒断线玩家死亡，同时保持 RNG 子流并把补偿结果重新持久化。
- RoomActor 撤离纵向验证从权威 3 秒读条完成开始，经状态观察器创建 settlement/Pending holds，再由结算后台提交金币、药剂与穿戴防具；确认 match/player 终局、outbox 可投递，并从 RoomRegistry 原子释放房间和玩家映射，重复后台迭代不重复提交。
- RoomActor 死亡纵向验证断线满 15 秒触发权威死亡：安全格金币返还，非安全金币/药剂/背包装备及穿戴防具保留在该格遗物堆；结算后台只提交安全资产、将两件防具转 `RelicPile`、解绑配装并消耗高级包，随后释放终局 Registry，重复迭代不重复入账。
- 结算冷启动恢复验证旧实例只留下 PostgreSQL Pending hold；此时 Bootstrap 不展示且确认返回冲突。重建仓储、后台与恢复状态后只提交一次并保留 ready outbox，Bootstrap 返回该玩家的待展示结算；确认接口按玩家隔离，状态更新与 `idempotency_records` 回放记录同事务提交，重复调用保持首次确认时间，确认后 Bootstrap 清空。再次重建执行不会重复入账。配套 `settlement-recovery` readiness 在首次扫描前拒绝就绪，扫描成功后恢复，扫描异常或存在失败 settlement 时保持失败。
- 真实网络冒烟在独立 schema 上启动 Release `FantasyCard.Server` 子进程，通过回环 TCP 验证 readiness、本地登录、Bearer Bootstrap、每日单卡报价与购买，以及 WebSocket 查询令牌鉴权、`session.connected` 和带 requestId 的 Protobuf `ping/pong`；测试退出时回收其创建的完整进程树。

## 本轮真实 HTTP / WebSocket 证据

`EndToEnd/RealNetworkGameplayTests.cs` 新增两个真实服务进程用例，均在专用数据库的随机 schema 中运行：

1. `Real_http_concurrent_card_upgrade_retries_spend_once`：通过真实 HTTP 读取 C01 报价，16 路并发提交同一个 `Idempotency-Key` 与 `expectedVersion`。所有响应一致，只升到 +1、只扣 5 点勇士魂，数据库只有一条升级流水。这是明确的并发重试验收，不是持续吞吐/容量压测。
2. `Real_process_pvp_relic_replay_and_extraction_survive_forced_restart`：先在测试 schema 中预置可重复的同格 PVP 战局和真实装备，再启动服务恢复该战局。经 HTTP Bootstrap 与双客户端 WS 完成 PVP 出牌击杀、分类伤害反馈、同 requestId 出牌回放、`relic.read`、拾取 29 金币和死者装备、两次拾取回放、撤离请求及回放。确认关键快照保存了撤离倒计时、装备和唯一 +2 养成卡后，强制结束该测试服务的完整进程树。

第二个用例随后启动新服务进程，验证恢复撤离并提交赢家合计 36 金币、装备所有权与库存位置，两个玩家恰好各有一条结算且没有 Pending hold；再启动一次服务，余额和结算数量保持不变。它证明已保存的房间状态、遗物归属、养成实例及结算能够跨真实进程恢复。初始战局由测试构造，不把该用例描述为从 Godot 登录、随机匹配、整张地图探索到撤离的完整人工通关。

同一轮完整服务测试还包含最新 Protobuf 可选字段、`combat.preview`/`combat.hit` 的分类伤害与速度字段、房间被动/PVP 投影，以及两个慢连接用例；后者检查 250ms 表现推送超时与旧连接清理不会移除新接管连接。

## 可靠性边界

正常结束或断言失败都会清理该次创建的 schema；强制终止进程可能留下测试 schema，需管理员核对后清理。

本轮强杀发生在**已验证关键快照落盘之后、撤离倒计时仍未完成时**，验证了真实服务进程中断和恢复。当前 RoomActor 命令完成通知可能早于后续快照观察器写盘；因此收到任意操作 ACK 后立刻杀进程、机器掉电或数据库不可用时“零状态丢失”不在该通过结论内，也不能用请求幂等替代房间持久性保证。

尚未覆盖任意数据库事务指令处强杀的市场购买/结算注入、PostgreSQL 自身崩溃或主机掉电、长期多人容量与延迟验收、真实 Steamworks 发行票据登录，以及 Godot 全 UI 从登录到随机地图通关。现有结算事务回滚、Pending hold 冷启动重试和这次进程恢复证据分别成立，不把它们扩大为这些未执行场景已经通过。
