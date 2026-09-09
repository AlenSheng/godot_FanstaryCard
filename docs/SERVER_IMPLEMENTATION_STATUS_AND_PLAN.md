# FantasyCard 服务端现状审计与开发计划

| 项目 | 当前值 |
| --- | --- |
| 审计日期 | 2026-09-09 |
| 服务版本 | `0.4.0-s7-runtime-slice+reward-choice` |
| SDK | `.NET SDK 10.0.400` |
| 规则配置版本 | `gdd-0.67-shop-rotation-1` |
| 当前可联调范围 | 登录 → Bootstrap → 档案/图鉴/编组 → 探索准备 → 商店/市场/强化接口 → 匹配入队/15 秒 Ready/机器人补满/成房 → 混沌地图/独立 PVE/三选一奖励 → WebSocket ping/resume/room.move/battle.play_cards/battle.select_target/reward.choice/duel.leave/duel.escape/relic.take/relic.replace/action.extract/action.spring/action.potion → 结算查询/待展示恢复/确认 |
| 当前不可联调范围 | 市场事务中断、结算操作系统级强杀演练、服务进程强杀演练、生产负载验收 |

本文以 [服务端 0→1 开发指南](./SERVER_0_TO_1_GUIDE.md) 为目标，以仓库当前代码和自动化结果为证据。只有代码、迁移、协议和测试同时存在的能力才标记为已完成。

## 1. 本轮查缺补漏结果

### 已补齐

- S1 统一卡牌配置链路已落地：按 GDD v0.65 将 `FantasyCard_Config.xlsx` 的 `Cards` 扩充为 200 张图鉴卡 + 12 张怪物卡，补齐来源、职业、品质、元素、效果字段、初始解锁、解锁/复制成本；`CardLevels` 补齐 200 张图鉴卡的 0–5 级共 1200 行成长规则，包含 +4/+5 同名卡消耗。卡牌初始落地版本为 `gdd-0.65-cards-1`，当前随商店轮换配置升级到 `gdd-0.67-shop-rotation-1`；服务端/客户端文件使用事务式暂存发布。
- 服务端已消费统一配置包：`FantasyCard.Domain` 嵌入配置二进制并解码 `Cards`/`CardLevels`/`EquipmentQuality`/`LootRules`/`Backpacks`/`Economy`/`ShopCardPrices`，战斗目录从配置创建 212 张定义；装备战斗属性、效果词缀、强化逐级碎片、三选一回血/品质/碎片、PVE 额外金币/魂/碎片、三档刷新价、探索包容量/安全格/价格、市场 Active 上限/挂牌时长/手续费、药剂价格/即时恢复比例及每日单卡槽位/价格/限购均由同包驱动。加载期强校验品质顺序、百分比、概率和、掉落区间、成本合计、背包层级和经济键值边界；保留旧卡 ID 别名保障旧牌组和房间快照恢复。Bootstrap 的 `configVersion` 读取配置包版本。
- 新账号 provisioning 已由 51 张硬编码起始卡改为配置驱动的 200 张图鉴卡：51 张按 GDD 初始解锁并各持有 1 张，其他图鉴卡以未解锁/0 张进入玩家卡表；默认 20 张卡组切换为规范 ID（`C01..C13` + 对应职业 `PRI/MAG/GUA-01..07`）。
- 数据库 V013 已加入：`player_cards.rarity` 支持橙卡等级 5，并将旧 51 张卡牌 ID 原子迁移为规范 ID；客户端映射同时接受规范 ID 与旧 ID。配置导出器修复了 `false` 逻辑值空消息被省略导致的行字段错位问题，并有回归测试覆盖。

- S3 Ready 阶段按方案 A 闭环：匹配成功进入 15 秒 `Starting`，全体真人确认可提前启动；超时真人转 `Removed` 并释放 preparation，机器人补齐到 4 席。新增 `match.found`、`room.ready_required/accepted/removed/started` Protobuf 协议与在线推送，`room.started` 携带玩家隔离首快照；`Launching` 中间态和首快照保证启动崩溃可恢复，结算完成判定忽略已剔除席位。
- S5 三选一账号金币补扣改为持久 Saga：先写 `Reserved` 并扣账号金币，RoomActor 以 requestId 幂等刷新并把完整回执写进房间快照，快照成功后转 `Applied`；进程中断留下的预留由恢复任务根据快照回执确认或原事务退款。临时金币仍优先消耗，价格与每局次数不变。
- S7 结算完成通知已改为持久 outbox：V012 与结算记录同事务写通知，只有全部资产 hold 成功提交后才允许发布兼容事件 `settlement.ready` 与 `match.settled`；在线玩家即时接收，离线玩家的行保留到下次连接，成功投递后才标记 published。迁移会为旧结算回填待投递行，客户端按 settlementId/eventId 去重。
- S6/S7 协议缺口继续收口：独立 `battle.select_target` 权威更新当前活目标并进入快照，`relic.replace` 显式承载“旧物原子回当前堆”语义且保留旧 `relic.take.replaceItemId` 兼容；RoomActor 快照转换现在向双方发布 `duel.ended`、`duel.escape_interrupted/failed`，向死亡本人发布 `player.died`，并发布撤离/泉水完成或被 PVP 打断事件，全部进入 sequence 缓冲并携带 roomRevision。
- S9 房间随机源已从单流拆为玩家牌堆种子、奖励、额外掉落、逃脱、机器人决策、决斗牌堆六条独立可持久流；快照恢复逐流续播，旧单流快照继续以兼容模式运行，不因迁移伪造随机状态。奖励刷新测试证明不会推进其他子流。
- 防具属性已从 preparation 不可变快照贯通 matchmaking、RoomActor 和房间恢复：品质/强化元素增伤与抗性、破击/载壁/生息套阈值与帽、抽牌间隔、鞋子强制逃脱均由服务端权威计算；橙红携带上限在换装、准备和领域入口三层校验。默认抽牌间隔下限按 GDD 修正为 1.8 秒，仅“疾抽”降至 1.5 秒。玩家打怪使用怪物抗性向量，怪物出手校验玩家装备抗性；载壁减伤仅盾职业。旧 preparation/room 快照按无新增加成兼容恢复。
- 湮核阶段状态已进入怪物快照：生命降至 140 后等待当前意图完成或被眩晕取消，再切到 3.8 秒金蚀循环、主金邻土抗性；未打出的阶段一蓄力不会带入阶段二。生息回复同时覆盖卡牌、三选一和生命泉，仍按有效生命上限 L′ 截断。
- 生命泉按玩家分别记录使用次数：同一口泉每名玩家可各用一次；1.2 秒读条按外/中/核心恢复 18%/25%/35%，满血仍消耗，PVP 入侵取消且不治疗。旧快照的全局已用泉记录保守迁移到所有玩家；命令、Protobuf、关键快照与并发房间入口均已接入。
- 场外生命药剂按 GDD v0.66 接入：仅行动栏可用，点击即时消耗 1 瓶并按 L 的 20% 基础值恢复，再吃生息回复比例并截在 L'，没有读条；满 L' 仍消耗。`action.potion/action.potion_used`、Protobuf、玩家快照 `allowed_actions` 与机器人兜底使用均已接入。
- S1/S2 大厅读取补齐：`GET /api/v1/inventory` 现返回背包与已穿戴装备完整属性、仅按背包装备计算的 50 格容量摘要，以及药剂/高级包/顶级包仓库数量；新增 `GET /api/v1/loadouts/{class}`，固定按 Head/Chest/Hands/Legs/Feet 返回职业五槽。真实 PostgreSQL 用例验证起始绑定鞋可由配装 ID 解析、背包计数与消耗品一致。
- S2 市场并发购买已在真实 PostgreSQL 验收：同一 listing 两买家并发只成功一次，失败者不扣金，获胜者扣标价、卖家收到扣除 10% 手续费后的净额，装备只转移一次。修复上架/成交遗漏 `inventory_movements`，成交装备更新增加卖家所有权与 `MarketListed` 状态条件，买卖双方 `economy_ledger` 和库存移动均关联获胜 requestId。
- S2 商店/强化异常事务已在真实 PostgreSQL 验收：商店同键重放只扣款发货一次，同键改请求、日限、余额不足和付费探索包仓库合计超过 3 个均整笔拒绝；商店金币流水关联 requestId。防具强化碎片不足时目标、材料和账本全部回滚，成功重放不二次消耗；按 GDD 允许仓库中的绑定同品质防具作为 +4/+5 材料，材料移动与碎片流水关联 requestId。
- S8 每日三张单卡轮换已完成：UTC+8 04:00 日切，同一 configVersion/resetKey 通过稳定哈希在所有实例生成一致的三张不重复 White～Purple 图鉴卡，Orange 不入池；价格 80/150/280/500、每张限购 1 均来自 `ShopCardPrices`。轮换创建在单事务内，既有日档不因重启改写。真库覆盖双实例并发、跨日、精确发卡、超限回滚与幂等回放；真实 HTTP 进程已验证读取和购买。同步修复随机礼包仍引用迁移前旧卡 ID 导致成功但未发货的问题，现按 50/30/15/5 权重实际增加三张并在零行更新时整笔回滚。
- S2/S7/S8 已将现有 `Backpacks`/`Economy` 发布表接入运行时：准备、临时背包、商店、市场和行动栏药剂不再各自复制 20/28/36、0/1/3、800/2200、8、48h、10%、100 与 20% 常量；配置缺项或非法值在服务启动加载期失败。此次仅收口配置消费，冻结玩法数值与药剂点击即时结算行为均未改变。
- V015 已建立全服红装自然周配额：以服务器时区周一 04:00 为周界，数据库每周键只允许 `red_dropped_this_week=0/1`，并记录渠道、玩家、对局、装备和领取时间。未来红装生成必须在同一个 PostgreSQL 事务中调用配额占用与装备落库，避免崩溃吞配额或并发多产；8 路并发仅一个成功、跨周可再次领取及审计快照已通过真实 PostgreSQL。原型仍锁定标准难度，当前没有调用产出路径。
- 真实网络冒烟验收已落地：测试在随机独立 schema 上启动真实 `FantasyCard.Server` 子进程，经 TCP 等待 `/health/ready`，完成 Development 本地登录、Bearer Bootstrap、WebSocket `access_token` 鉴权、`session.connected` 及带 requestId 的 `ping/pong` Protobuf 往返；无论成功失败都会回收其创建的服务进程并清理 schema。该用例证明网络入口和序列化契约可工作，不代表完整房间客户端纵向或进程强杀恢复已完成。
- GDD v0.67 红装强化材料已改为同品质：红装 +4/+5 只接受红装材料，橙装会被拒绝且不扣碎片；真实 PostgreSQL 已验证红装材料单次消费和审计。当前原型不产红装，强化入口随红装掉落/周配额开放，正常玩家路径不可达。
- S7 结算资产提交已补真实 PostgreSQL 验收：背包装备、穿戴装备、生成装备、遗物拾取装备、金币、勇士魂、职业魂、装备碎片和药剂九个 hold 可原子提交；相同 settlement 重试不重复入账，全部提交前 outbox 不可见，发布后不重复投递。任一非法资产会使整批余额、账本和 hold 状态回滚并保留 Pending 供后台重试。
- S3/S7 永久资产托管已贯通：创建 preparation 时所选装备切到 `PreparationLocked`，主动取消、排队取消、到期或 Ready 超时剔除均恢复 `Equipped`；正式开房原子转为 `InMatchEquipped` 并扣除带入药剂，付费包保持逻辑预留。撤离把穿戴件恢复 `Equipped`、背包件入 `Inventory`、未用药剂返仓并释放付费包；死亡防具转 `RelicPile`、从职业配装解绑并原子消耗付费包。所有装备位置变化写 `inventory_movements`。
- S3 准备/匹配/Ready/房间入口已在真实 PostgreSQL 纵向验收：重复 enqueue 只返回原 ticket，同键改 preparation 返回幂等冲突；4 真人立即成组并在全员 Ready 后生成首份房间快照、注册 RoomActor、推进 Running。未满 4 真人等待 30 秒后进入 Ready，15 秒未确认者转 Removed 并取消 preparation，保留真人转 Active、机器人补到固定 4 席后启动。
- S9 Running 房间启动恢复已补停机计时：恢复查询携带 `room_snapshots.updated_at`，重建 Actor 后在单读队列内按 100ms 权威 tick 回放停机时长，最终快照只观察/落库一次；失败会移除半注册 Actor。真实 PostgreSQL 已验证玩家与 matchId 映射、15 秒断线超时、RNG 子流保持和补偿快照回写。
- S7 RoomActor→结算纵向已通过真实 PostgreSQL：权威撤离完成触发状态观察器，幂等创建 settlement/holds/outbox，后台提交金币、药剂和穿戴防具；数据库终局后从 RoomRegistry 移除 Actor 与玩家映射，避免已结束房间继续 10Hz tick。Pending 提交失败仍由数据库后台重试，不依赖 Actor 常驻。
- S7 死亡纵向已通过真实 PostgreSQL：RoomActor 断线满 15 秒后权威判死，安全格资产与遗物堆按冻结规则分离；后台仅返还安全金币，把背包装备和穿戴防具转为 `RelicPile`、解绑配装、消耗付费包并发布可恢复 outbox，终局 Registry 随后清理。
- 新增玩家隔离的 `room.snapshot`：连接活动房间、显式读取、事件缓存缺口或客户端房间 revision 落后时下发；只暴露 Boss/泉水/本人位置等允许情报，同时恢复本人战斗、背包、PVE/PVP、奖励、读条和可操作列表。`session.resume` 向后兼容新增可选 roomId/roomRevision。
- S8/S9 基础切片已落地：金币商店 UTC+8 04:00 日切、市场到期后台回收、经济跨表与账本链只读对账、REST/WS 分层限流、输入上限、WS token 链路追踪脱敏、过期会话/幂等记录/房间事件清理、房间关键节点即时快照与 Running 房间启动恢复/停机计时补偿。OTLP 指标现覆盖登录成功/失败、无效/过期令牌、WS 在线/消息大小/resume/命令拒绝、排队时长、活动房间与人数、快照失败、结算创建/幂等命中/失败/Pending holds、经济对账及周期清理。房间恢复失败、活动房间快照落库失败、结算首次恢复扫描失败或存在提交失败项都会拉低 readiness；发布/回滚/备份恢复/告警 runbook 已建立。数据库迁移/聚合、结算资产提交原子性、Pending hold 应用级冷启动恢复及 Running 房间应用级恢复已在真实 PostgreSQL 验收；市场事务强杀、结算操作系统级强杀、服务进程强杀与负载验收仍未完成。
- 配置发布改为两端文件全部暂存后提交；发布异常会清理暂存并恢复已有文件，避免服务端与客户端遗留半套配置。
- 准备快照过期生命周期已闭环：到期的 Active/Queued preparation 会转为 Expired，关联排队 ticket 同步取消，不再永久占用玩家唯一准备/排队锁；Matched 局不按准备 TTL 误清理。
- 取消准备、取消排队和市场撤单支持安全重复调用；市场撤单恢复装备时补写 `inventory_movements`，并在装备托管状态不一致时整笔回滚。
- 取消准备、取消排队和市场撤单已进一步接入持久 `Idempotency-Key`；同键改目标会拒绝。实时事件流增加可配置闲置 TTL 与并发安全后台回收，过期后重连按既有协议回退 `session.snapshot`/`room.snapshot`。
- S3 补位机器人已进入房间 tick：按层模拟 PVE 固定时长/损血、自动三选一、泉水优先、撤离概率与向内移动；真人对战使用中等卡牌 AI，机机对战 10 秒模拟，机器人不进入掉线流程。真人全部终局时关闭机器人席位，结算不生成机器人资产；准备快照中的真人专属武器等级与真人均值机器人等级已传入战斗。
- Bootstrap 现在返回活动中的 `unfinishedMatch`（matchId、roomId、状态、roomRevision、configVersion），客户端可据此优先恢复实时房间。V014 为结算增加首次确认时间；只有资产 hold 全部离开 Pending 且尚未确认的最新结算才进入 `unfinishedSettlement`。新增玩家归属校验的 `POST /api/v1/settlements/{id}/acknowledge`，重复确认稳定返回首次时间，确认后 Bootstrap 不再展示；迁移前历史结算会按创建时间回填为已确认，避免升级后误弹旧记录。
- 修复重复卡同时打出时以卡定义作字典键导致的重复键异常；改为按实际出牌槽位结算。
- 档案、卡组、穿戴、防具强化和专属武器强化均接入持久 `Idempotency-Key` 响应回放，避免成功响应丢失后的重试重复变更；穿戴只迁移实际变化的装备并写 `inventory_movements`。大厅与匹配 REST 写入口统一接入写限流。
- 业务 REST 写入口已统一使用公共 `Idempotency-Key` 读取与错误响应：认证后统一执行 trim、8–80 字符及控制字符校验；档案、卡组、穿戴、强化、准备、商店、市场、匹配和结算确认继续在各自 PostgreSQL 业务事务内持久回放。商店/市场同键改请求统一抛出 `IdempotencyConflictException` 并返回明确 409；登录按外部身份天然幂等，不要求业务写键。
- 市场购买按玩家 ID 固定顺序锁定买卖双方，结算资产提交复用同一玩家锁；结算金币/材料写经济流水，已有装备回库补库存移动轨迹。
- Production 对 Local Auth 做环境级硬关闭；新增默认关闭的 Steam `AuthenticateUserTicket` 服务端验票入口，外部 SteamID 只采用平台响应并映射内部 UserId，Publisher Key 仅从配置注入。真实 Steamworks 联调仍需 AppId/Key/identity。

- 用 `V001–V003` 嵌入式 SQL 迁移替代启动时整段建表；包含 checksum、PostgreSQL advisory lock、逐迁移事务和篡改检测。
- 旧数据库兼容：V001 使用 `CREATE TABLE IF NOT EXISTS` 接管已有 identity 三表，不要求删库。
- 首次登录幂等初始化：钱包、材料、51 张起始解锁卡、三职业默认 20 张编组、三把 +0 专属武器、三职业绑定白鞋、空消耗品账户。
- 新增 `GET /api/v1/bootstrap`，一次返回大厅首屏所需的玩家、钱包、材料、武器、穿戴、编组和背包摘要。
- 新增图鉴和编组接口；编组保存校验 20 张、持有数量、职业限制、怪物卡和橙卡上限，并使用版本冲突保护。
- 新增探索准备快照；校验卡组版本、五个位置、装备归属/状态、包档、安全格、药剂、Standard 难度和 `Idempotency-Key`。
- 实时协议新增 `eventId`、`sequence`、`requestId`、`occurredAt`、可选 `roomRevision`；保留旧 `type/traceId/payload` 字段。
- 新增最近 256 事件重放、请求响应去重、`session.resume`、缓存缺口快照和同账号新连接接管。
- Local Auth 默认关闭，仅 Development 配置开启；生产配置不会暴露本地伪造身份入口。
- 服务根接口返回版本、配置版本、里程碑和真实 capability 列表。
- 结算托管后台处理 Pending holds：按事务锁定并提交装备、金币、魂、碎片和药剂；资产不在匹配托管状态时整笔回滚并重试。单个异常 settlement 已隔离，失败会记录指标与日志且不会阻塞后续 settlement。进程启动后首次扫描完成前 readiness 保持失败；扫描异常或本轮存在失败 settlement 时继续拒绝就绪，后续无失败扫描可自动恢复。
- `RoomActor` 状态观察器已把 Extracted/Dead 玩家提交到幂等结算协调器；死亡只提交安全格物资，遗物仍由房间持有。
- 新增房间快照仓储：按 revision 节流写入 `room_snapshots`，关键节点即时写入；六类 RNG 子流与玩家牌堆 RNG 状态可恢复，启动扫描可按快照更新时间补偿停机 tick 并重建 Running 房间。应用级恢复已过真实 PostgreSQL 验收，操作系统级服务强杀演练仍未完成。

### 本轮验证

- 2026-09-08 已连接本机 PostgreSQL 18 开发容器真实执行集成验收：补充 V013 旧卡 ID（`common-01` → `C01`）与卡组引用原地升级、橙卡 rarity=5 约束、V014 结算确认升级、大厅资产事务、红装同品质强化材料、准备/战局资产托管、结算资产原子提交/失败回滚/死亡掉装、Pending hold 冷启动恢复与 Bootstrap 待展示/确认闭环、四真人/超时补机器人匹配纵向、Running 房间停机恢复及 RoomActor 撤离/死亡结算终局清理；PostgreSQL 分类共 21 项全部通过、0 跳过。
- 完整 `dotnet test FantasyCard.Server.slnx -c Release` 在真实 PostgreSQL 分类开启时通过：领域测试 129/129、服务测试 120/120、0 跳过。覆盖统一配置包装备/掉落映射与概率边界、统一 REST 幂等键校验、药剂即时使用、大厅资产事务、红装同品质强化、准备锁、结算 hold/outbox/遗物去向、结算确认持久回放、结算恢复 readiness、Pending hold 冷启动幂等恢复、RoomActor 撤离/死亡到结算与终局清理、匹配/Ready/首快照/Running、停机 tick 补偿、V014 升级及既有房间/经济链路。

- PostgreSQL 运行时验收现有 21 项：迁移并发/重启/checksum 篡改拒绝、同一身份 8 路并发首次登录、旧 identity 三表升级并幂等补齐、V013 旧卡 ID/卡组引用/橙卡约束升级、同版本卡组并发写与响应回放、探索准备并发幂等/冲突/装备锁释放、完整库存与职业配装读取、市场并发购买、商店异常事务、防具/专属武器强化回滚与幂等消费、红装拒绝橙材料并消费红材料、结算九个 hold 幂等提交/outbox、结算非法资产整批回滚、死亡装备转遗物并解绑、旧实例仅留下 Pending hold 后由新实例提交且再次重启不重复入账、四真人立即成组/Ready/资产托管/开房、30 秒成组/15 秒 Ready 超时剔除/装备释放/机器人补位、Running 房间停机 tick 补偿恢复、RoomActor 撤离和死亡到结算/资产提交/终局 Registry 清理；Bootstrap 完整聚合随登录用例断言。所有用例使用内部生成的随机独立 schema，失败也清理；2026-09-08 已真实执行且全部通过。

- 200 卡配置源验收：GDD §4.3 与客户端领域表已有完整 200 张具名及效果，双语描述覆盖 212 张（含 12 张怪物卡）；工作簿现已扩充为完整 212 张卡牌配置和 1200 条等级规则，服务端已从发布包加载，客户端保留规范/旧 ID 双向兼容。V013 旧 ID 升级和新账号 200 卡聚合已在真实 PostgreSQL 通过。

- 最新完整隔离构建结果：领域测试 130/130、服务测试 128/128；其中 PostgreSQL 集成测试 25/25，0 跳过。每日单卡/随机礼包、真实进程商店 HTTP/WS 冒烟以及既有迁移、身份、资产、市场、匹配、房间恢复和结算链路均完成回归。

- 房间乐观并发校验已收口到 `RoomActor` 单读队列：三选一领取、双方离开、强制逃脱、撤离、遗物检索不再在入队前校验旧快照；两个同版本命令排队时，前一个成功后后一个会在队列内以版本冲突拒绝且不改状态。移动、出牌和刷新继续使用领域内版本校验。新增排队竞态测试；最新结果为领域 73、服务端 24 通过 / PostgreSQL 1 跳过。

- 职业魂结算映射修复：实际掉落 `class_soul:Priest/Mage/Guardian` 与旧托管标识 `PriestSoul/MageSoul/GuardianSoul` 映射至各自固定账户列，未知标识不猜测、不提交。新增三职业实际清怪掉落到结算映射测试及未知输入拒绝测试。最新结果：领域 73、服务端 23 通过 / 数据库 1 跳过；资产 SQL 提交仍待真实 PostgreSQL 验收。

- 快照计时 P0 修复：此前不存在的断线/撤离计时被序列化为零，恢复后下一 tick 会误判死亡。新增失败回归后修复为 null；旧快照零值不重新注册计时器，有效正值继续倒计时。测试覆盖在线玩家恢复、15 秒断线倒计时和旧零值行动栏快照。最新结果领域 73、服务端 19 通过 / 数据库 1 跳过；仍不等同于真实进程重启验收。

- 移动/PVE 链路修复：进入未清格创建该玩家的新 PVE，再执行同格配对；新进入者为后手；离格取消原撤离读条。玩家已清格集合进入快照，返回已清格保持行动栏且不再次发奖。刷新预算测试已改为实际调用移动并清第二格，另验证同格决斗存活后恢复目标格 PVE。领域 70、服务端 19 通过，数据库集成 1 跳过。此处是领域连续流程验证，未代表真实网络/数据库联调完成。

- P0 数据库验收入口：`PostgresMigrationTests` 在随机独立 schema 中覆盖并发迁移、重复启动、校验和篡改拒绝；运行时测试覆盖聚合、升级、幂等与准备事务。执行说明见 [POSTGRES_TESTS.md](../server/docs/POSTGRES_TESTS.md)。2026-09-07 已在 PostgreSQL 18 真实执行通过。

- 协议复核补充：修复 `reward.choice_claimed` 编码为空的问题，保留 optionId/applied；补齐现有事件 schema 和 Boss 标识字段。新增覆盖 9 种事件样例的完整信封/载荷往返测试。最新结果：领域 68、服务端 19 项通过。
- 验收限制：现有通过用例不能证明 S2–S9 全部完成。刷新扣款与房间更新已具备持久预留、房间回执和崩溃补偿，但尚未在真实 PostgreSQL 中执行进程中断验收。登录→Bootstrap→WebSocket ping 的真实进程网络冒烟与 RoomActor→撤离/死亡结算的应用级真实 PostgreSQL 纵向已通过；完整大厅事务/房间客户端纵向及操作系统级进程强杀恢复仍待专项验收。
- 刷新次数修复：新增玩家整局计数，领取后仍保留，新奖励集继承计数，快照恢复校验计数一致性；PVP 阶段拒绝刷新。领域测试覆盖三档扣费、领取/恢复/下一场奖励继承次数、第四次拒绝且不扣款、玩家互不占用，以及 PVP 拒绝不改状态。下一格战斗由测试快照构造，尚不代表移动端到端完成。最新测试：领域 70、服务端 19 项通过。
- 旧快照兼容限制：未包含玩家计数时可读取当前奖励集计数；旧实现已丢弃的历史奖励集计数无法从该快照还原，仍需运行期迁移/恢复验收。

- `.NET SDK 10.0.400` 下完整解决方案编译：0 warning / 0 error。
- 领域测试 68 项通过：在原有房间/战斗覆盖上新增三选一固定三类、层级回血比例、刷新次数上限测试。
- 服务测试 18 项通过：sequence、事件重放、缓存缺口、requestId 响应缓存、命令路由、RoomActor、决斗路由和 Protobuf 房间/奖励命令。
- 本机 Docker/PostgreSQL 已可用，数据库迁移、基础聚合、房间应用级恢复及登录/Bootstrap/WebSocket ping 真实进程冒烟已执行；完整房间网络纵向和经济事务中断仍未执行。

## 2. 阶段完成度

| 阶段 | 状态 | 已有 | 主要缺口 | 下一完成门 |
| --- | --- | --- | --- | --- |
| S0 基础 | 基本完成 | 迁移、协议外壳、生产禁 local auth、统一业务 REST 幂等键入口与事务内持久回放、分层限流与输入上限、服务测试、25 项随机 schema PostgreSQL 真实验收（含真实 HTTP/WS 进程冒烟） | 负载验收 | 客户端补 Bootstrap 200 卡状态测试 |
| S1 玩家聚合 | 服务端主体完成 | provisioning、bootstrap、钱包/材料、完整库存与消耗品读取、按职业五槽配装读取、200 卡图鉴与 1200 条等级配置、初始/未解锁卡、规范 ID 迁移、编组、专属武器、白鞋、双端同包配置编译与事务式文件发布、真实 PostgreSQL V013/聚合验收 | 客户端大厅状态测试 | 新/旧账号登录后大厅资产一致 |
| S2 大厅业务 | 基础完成 | 五部位换装、配置驱动强化、商店/市场基础事务、每日三张单卡与随机礼包、经济流水、档案/卡组/穿戴/准备/交易/强化/取消持久幂等、市场并发购买及商店/强化异常事务 PostgreSQL 验收；商店读取/购买真实 HTTP 验收 | 其余大厅写接口真实 HTTP 客户端联调 | 大厅资产事务闭环 |
| S3 准备/匹配 | 服务端纵向完成 | 队列、取消队列、1–4 人成房、15 秒 Ready、超时真人剔除与机器人补满、Launching 恢复、装备 PreparationLocked→InMatchEquipped 托管、带入药剂扣除与付费包逻辑预留、机器人 PVE/选择/移动/泉水/即时药剂/撤离/PVP 驱动、match 表、RoomActor、不可变防具战斗快照、真实 PostgreSQL Hall→Room 纵向验收 | 真实 HTTP/WebSocket 客户端联调 | Hall → RoomStarted |
| S4 地图 | 基础完成 | 服务端 6×6 生成、玩家隔离投影、合法移动、格状态、房间初始化、快照持久化 | 真实房间联调 | RoomStarted → PVE started |
| S5 PVE | 基础完成（奖励切片） | 独立 PVE、怪物意图、抽牌/满手限制、装备元素增伤/抗性与效果套、怪物抗性向量、湮核两阶段、固定三选一、层级回血、满包显式替换、刷新上限/价格、奖励快照、账号金币持久预留与崩溃补偿、标准层级金币/魂/碎片额外掉落、Boss 32% 回血 | 真实 PostgreSQL 进程中断验收 | 单人打怪 → 选奖励 → 行动栏 |
| S6 PVP | 基础完成 | 配对入口、同格自动配对、冻结/恢复、后手锁、双方离开、逃脱读条/打断/失败/冷却、停战缓存、掉线双方停手与超时死亡、`duel.ended`/`player.died` 可重放增量事件 | 真实房间验收 | 两人同格时序验收 |
| S7 背包/遗物/结算 | 运行时纵向完成 | 临时包容量/安全格、资源堆叠、行动栏即时药剂、三选一待回收令牌、遗物堆版本交互、显式 `relic.replace`、3 秒撤离、断线死亡、房间状态观察器、结算协调器/commit worker/outbox、七类资产原子提交与失败回滚、Pending hold 应用级冷启动幂等恢复、Bootstrap 待展示结算与幂等确认、RoomActor 撤离/死亡→结算→终局 Registry 清理真实 PostgreSQL 纵向 | 真实 HTTP/WebSocket 客户端纵向、操作系统级强杀恢复验收 | 完整一局回大厅 |
| S8 经济完善 | 基础完成 | 商品日轮换、每日三张单卡、随机礼包、限购、市场上架/购买/取消/48h 到期、10% 抽成、经济流水、周期性跨表/账本链只读对账与结构化告警、V015 红装周配额与审计占位 | 历史异常处置流程 | 原型经济闭环 |
| S9 可靠性 | 基础恢复完成 | 内存 sequence/replay/resume、闲置事件流 TTL 回收、房间断线 15 秒宽限与 PVP 停手/超时死亡、快照写入/读取、Running 房间启动扫描/停机 tick 补偿/RoomActor 重建真库验收、六类独立 RNG 子流及旧快照兼容、房间恢复/持久化/结算恢复 readiness、Pending hold 冷启动不重结算真库验收、HTTP/WS 限流、输入上限、日志脱敏、登录/WS/匹配/房间/RoomActor 队列与 tick/快照耗时/PVE-PVP 时长与异常关闭/结算/经济/清理/迁移 OTLP 指标、Npgsql 10 连接池与查询时长指标、运维 runbook | Redis 可选缓冲、容量目标与负载、操作系统级强杀/备份恢复演练 | 重启和断线不丢局/不重结算 |

## 3. 已上线协议清单

| 模块 | 接口/命令 | 状态 |
| --- | --- | --- |
| Service | `GET /`、`GET /health/live`、`GET /health/ready` | 可用 |
| Identity | `POST /api/v1/auth/local`；`POST /api/v1/auth/steam` | Local 仅 Development；Steam 默认关闭、配置平台密钥后可用 |
| Player | `GET/PUT /api/v1/players/me` | 可用，乐观并发 |
| Bootstrap | `GET /api/v1/bootstrap` | 可用 |
| Cards | `GET /api/v1/cards` | 可用 |
| Decks | `GET /api/v1/decks`、`PUT /api/v1/decks/{class}` | 可用 |
| Inventory/Loadouts | `GET /api/v1/inventory`、`GET/PUT /api/v1/loadouts/{class}` | 可用；库存含 Inventory/Equipped 装备与药剂/付费包数量，容量摘要只统计 50 格养成背包 |
| Preparation | `GET/POST /api/v1/preparations`、`DELETE /api/v1/preparations/{id}` | 可用 |
| Realtime | `/ws/v1/session`：`ping`、`session.resume`、`room.ready`、`room.snapshot.read`、`room.move`、`battle.play_cards`、`battle.select_target`、`choice.refresh/pick`（兼容 `reward.choice.*`）、`duel.leave`、`duel.escape`、`relic.take/replace`、`action.extract`、`action.spring`、`action.potion` | Ready、决斗终止、死亡、结算事件与玩家隔离 `room.snapshot` 已接入；真实进程已验证鉴权、连接和 ping/pong，RoomActor 撤离→结算→终局清理已过真实 PostgreSQL 纵向；完整房间客户端联调仍待完成 |
| Match/Room/Battle | `match.*`、`room.*`、`battle.*`、`duel.*`、`action.extract`、`action.spring`、`action.potion` | 基础命令、同格自动配对、机器人运行时和结算落库已接入 |

## 4. 后续开发计划

### P0：完成 S0/S1 运行时验收（数据库基线已通过，客户端状态测试待执行）

1. [x] 安装并启动 Docker Desktop / PostgreSQL 18。
2. [x] 在随机空 schema 验证 V001→V014、重复启动不重复执行、checksum 变更阻止启动。
3. [x] 验证旧版三表升级、V013 旧卡 ID/卡组引用迁移、橙卡 rarity 约束和已有玩家幂等补齐 200 卡资产。
4. [x] 持续扩充至 21 项 PostgreSQL 集成测试，覆盖并发首次登录、卡组版本冲突/回放、准备装备锁/取消释放、旧 identity 与 V013 升级、Bootstrap 完整聚合、大厅资产事务、结算原子提交/死亡掉装与 Pending hold 冷启动幂等恢复、匹配到成房资产托管纵向链路、Running 房间停机恢复及 RoomActor 撤离/死亡终局结算清理。
5. [ ] 将 `GET /api/v1/bootstrap` 的 200 卡资产与 `configVersion` 加入客户端大厅状态测试。

完成门：空库和旧库都能启动；相同 deviceId 并发登录只有一个玩家聚合；重复准备不重复预留。

### P1：S2 大厅资产事务（基础实现已落地）

1. [x] 实现 `GET /api/v1/inventory` 与 `GET/PUT /api/v1/loadouts/{class}`，库存包含背包/穿戴装备及药剂、两档付费包数量。
2. [x] 实现防具/专属武器强化，建立 `inventory_movements` 与 `economy_ledger`；防具失败回滚与重放已过真实 PostgreSQL 验收。
3. [x] 实现每日金币商店、限购和配置版本；余额/日限/付费包合计上限失败原子性已验收。
4. [x] 实现金币市场上架、购买、取消、过期退回和 10% 抽成；并发成交已过真实 PostgreSQL 验收。
5. [x] 所有业务写端点接入统一 `Idempotency-Key` 读取/错误响应，并在各自业务事务内执行持久回放；身份登录按外部身份天然幂等。

完成门：并发购买只能成功一次；余额永不为负；专属武器无法卸下、交易、掉落或当材料。

### P2：S3 匹配与房间入口（基础实现已落地）

1. [x] 新增 V004：`match_tickets`、`matches`、`match_players`、`room_snapshots`。
2. [x] 实现 `match.enqueue/cancel`；仅接受 Active preparation；enqueue 同键改 preparation 返回 409。
3. [x] 实现 1–4 人 Standard 队列：满 4 立刻开，否则 30 秒后按 `BotRules` 补机器人到 4。
4. [x] 建立 `RoomActor` 单读者 Channel、房间 revision、定时调度和独立 RNG 流。
5. [x] 实现 `room.ready_required/ready/started`，开始后 preparation 变 Matched；首快照与 Running 已过真实 PostgreSQL 验收。

完成门：客户端可从大厅准备进入 RoomStarted；重复 enqueue 不生成多张 ticket。

### P3：S4/S5 地图与 PVE

1. 移植并校验 6×6 三层地图生成，锁定 seed/configVersion。
2. 实现每玩家隐藏投影和合法四邻移动。
3. 实现独立 PVE 实例、三堆、手牌上限 5、满手轮空、弃牌洗回。
4. 实现怪物意图调度、权威连放计算和三选一。
5. 共享黄金向量同时验证服务端与客户端纯 C# 规则。

完成门：E2E-01 的单人部分可从出生打赢一格并进入行动栏。

### P4：S6/S7 PVP 与结算

1. 实现同格配对、进格豁免、PVE/三堆冻结恢复、后手 0.8 秒。
2. 实现双方离开、2 秒逃脱、12 秒冷却、45 秒停战和距离解除。
3. 实现临时背包、安全格、三选一替换、遗物堆版本并发。
4. 新增 V005：settlement、ledger、inventory movement、relic tables。
5. 实现撤离/PVE 死/PVP 死原子结算和 `UNIQUE(match_id, player_id)` 防重。

完成门：E2E-01 至 E2E-06 全部自动化通过；重连不重复发奖励。

### P5：S8/S9 发布候选

1. 商店轮换、市场过期和只读经济对账已实现；在真实 PostgreSQL 执行并发与异常样本验收。
2. 房间关键节点快照、启动恢复和超时补偿。
3. WS/HTTP 限流、输入大小、WS token 日志脱敏，以及登录/WS/匹配/房间/RoomActor/PVE-PVP/结算/经济/清理/迁移指标已实现；Npgsql meter 提供连接池状态和查询时长，慢查询阈值由监控后端配置；待补负载验收。
4. 加入协议兼容、房间模拟、并发、负载、备份恢复测试。
5. Staging/Production 发布、回滚、迁移、备份恢复和告警 runbook 已编写；执行一次演练并留存证据。

完成门：进程重启可恢复 Running room 或安全结算；生产 local auth 关闭；容量和告警达到发布指标。

## 5. 不得提前宣称完成的能力

- `session.resume` 可重放会话事件，并在缓存缺口或 roomRevision 落后时补玩家隔离的 `room.snapshot`；Running 房间应用级启动恢复已过 PostgreSQL 验收，操作系统级服务强杀/重启仍待演练。
- `idempotency_records` 已用于档案、卡组、穿戴、防具/专属武器强化及取消操作响应回放；准备、商店与市场创建/购买使用各自持久幂等记录。真实 PostgreSQL 并发重放仍待集成验收。
- Bootstrap 已返回 `unfinishedMatch`，并在资产提交完成后返回最新一条尚未确认的 `unfinishedSettlement`；确认接口按玩家隔离且幂等，Pending 阶段拒绝确认。当前返回单条待展示结算，不提供分页历史收件箱。
- `configVersion` 已下发；200 卡/怪物卡、装备品质/词缀/强化成本、标准难度掉落及每日三张单卡价格/限购已形成 `gdd-0.67-shop-rotation-1` 独立配置包并由服务端运行时消费。地图权重仍待发布表定义；红装开放概率仍待未来配置，但 V015 周配额并发闸门与审计字段已经落库，原型不会调用红装产出。
- V013 规范卡 ID/卡组引用迁移、橙卡 rarity 约束和新账号 200 卡聚合已在 PostgreSQL 18 随机 schema 中通过；尚未做生产备份副本演练。
- PostgreSQL 基础迁移/聚合/卡组/准备、市场并发、结算资产原子提交/失败回滚、Pending hold 应用级冷启动幂等恢复及 Running 房间应用级启动恢复验收已执行；市场事务中断、结算操作系统级强杀与服务进程重启仍需专项演练。
