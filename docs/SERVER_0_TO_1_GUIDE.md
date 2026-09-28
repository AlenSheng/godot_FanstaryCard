# FantasyCard 服务端 0→1 开发指南

| 项目 | 内容 |
| --- | --- |
| 目标 | 从登录/档案/WebSocket 骨架发展为支持完整在线原型的权威模块化单体 |
| 技术 | ASP.NET Core / .NET 10 LTS、.NET SDK 10.0.400、PostgreSQL、Redis 按需 |
| 通信 | 第一方登录/玩法 HTTPS REST 使用 Protobuf，外围 JSON；WebSocket 使用 Protobuf v1 二进制帧。旧游戏 JSON 由显式兼容开关控制，迁移验收见 network-protobuf-migration/PLAN.md |
| 部署 | Linux + Docker |
| 数据原则 | PostgreSQL 是永久资产唯一权威；Redis 不保存唯一业务数据 |

本文描述目标架构与实施顺序。权威、tick、冻结快照、掉线与匹配窗口以 [服务器设计规范](./SERVER_SPEC.md) 为准。当前已实现接口以 [当前客户端联调协议](../server/docs/CLIENT_INTEGRATION.md) 为准，目标命令/事件以 [端到端流程与协议](./END_TO_END_FLOW_AND_PROTOCOL.md) 为准。代理改服务端时遵循 [server_create](../.agents/skills/server_create/SKILL.md)：先读 GDD 与本稿，规则冲突先停手。

本地开发、自动化测试和 Docker 构建统一使用 `.NET SDK 10.0.400`。版本由 `server/global.json` 锁定，Docker 构建阶段使用同版本 SDK 镜像；不得仅升级个人开发机而不更新这两处基线。

## 1. 当前服务端基线（0.2.0-s1-preparation）

### 已有

- `POST /api/v1/auth/local`。
- `GET/PUT /api/v1/players/me`，带乐观并发 version。
- V001–V003 版本化 SQL 迁移，带 checksum、advisory lock 和逐迁移事务。
- PostgreSQL：身份、钱包/材料、卡牌/编组、专属武器、装备/穿戴、消耗品、准备快照与幂等记录。
- Bearer 会话、token 哈希、30 天默认有效期。
- 新玩家幂等 provisioning：30 通用白卡、三职业各 7 白卡、默认 20、+0 专属武器、五部位配装全空。不发放绑定白鞋。
- `GET /api/v1/bootstrap`、`GET /api/v1/cards`、`GET/PUT /api/v1/decks`。
- `GET/POST/DELETE /api/v1/preparations`，带版本、资产与 `Idempotency-Key` 校验。
- `/ws/v1/session`：session.connected、ping/pong、sequence、256 事件重放、session.resume、同账号接管、16 KiB 上限。
- ProblemDetails + traceId。
- 健康检查、OpenTelemetry 接口、Docker Compose。
- 领域与实时协议自动化测试。

### 未有

- 最终 200 卡静态目录、完整库存/穿戴写接口和配置发布包。
- 强化、商店、市场与通用经济流水。
- 商店/市场。
- 匹配、房间、地图、PVE/PVP。
- 权威抽牌/战斗/奖励/遗物/撤离/死亡结算。
- 房间级 WebSocket 快照、事件持久缓冲和进程恢复。
- 房间崩溃恢复、资产预留、幂等命令和经济总账。

当前详细完成度、差距与下一阶段完成门见 [服务端现状审计与开发计划](./SERVER_IMPLEMENTATION_STATUS_AND_PLAN.md)。数据库代码已编译，但本机缺少 Docker/PostgreSQL，V001–V003 的进程级集成验收仍是 P0 必做项。

## 2. 服务端总原则

1. 服务端权威：客户端只发意图，不提交伤害、抽牌、掉落、骰点、金币结果。
2. 模块化单体：按业务模块分目录和边界，不提前拆微服务。
3. 房间串行：同一 room 的状态命令严格串行处理，避免用大量细粒度锁补竞态。
4. 永久资产事务化：购买、强化、市场、准备锁、结算均在 PostgreSQL 事务内完成。
5. 所有写操作幂等：REST 使用 Idempotency-Key；WS 使用 requestId。
6. 版本化：持久实体 version，房间 roomRevision，事件 sequence，静态配置 configVersion。
7. 可恢复：进房后定期/关键节点持久化房间快照；结算落库不依赖客户端在线。
8. 隐藏信息按玩家投影：同一内部房间状态为不同玩家生成不同响应。
9. 不记录秘密：访问令牌、平台票据、微信 code 不进入普通日志。
10. 冻结规则先确认：程序不能私自改 GDD `0.2 行为。

## 3. 目标解决方案结构

保留当前三个项目，在模块化单体内部扩展：

```text
server/
  src/
    FantasyCard.Contracts/
      Common/
      Identity/
      Players/
      Progression/
      Economy/
      Matchmaking/
      Rooms/
      Combat/
      Settlement/

    FantasyCard.Domain/
      Players/
      Cards/
      Equipment/
      Inventory/
      Economy/
      Matches/
      Rooms/
      Combat/
      Loot/

    FantasyCard.Server/
      Common/
      Persistence/
        Migrations/
        Transactions/
      Identity/
      Players/
      Bootstrap/
      Progression/
      Shop/
      Market/
      Matchmaking/
      Rooms/
      Combat/
      Loot/
      Settlement/
      Realtime/
      Observability/

  tests/
    FantasyCard.Domain.Tests/
    FantasyCard.Server.IntegrationTests/
    FantasyCard.Protocol.Tests/
    FantasyCard.LoadTests/
```

每个模块内部建议：

```text
Module/
  Domain or domain types in FantasyCard.Domain
  Contracts in FantasyCard.Contracts
  Endpoints.cs
  Service.cs / CommandHandlers.cs
  Repository.cs
  Mappings.cs
  ModuleExtensions.cs
```

不要把所有业务继续堆进 `Program.cs`。Program 只注册模块、中间件和端点。

## 4. 数据库迁移与事务基础

### 4.1 迁移

采用版本化 SQL 迁移即可，不要求引入重量 ORM：

```text
Persistence/Migrations/
  V001__identity.sql
  V002__player_progression.sql
  V003__equipment_inventory.sql
  V004__shop_market.sql
  V005__match_room.sql
  V006__settlement_ledger.sql
```

建立 `schema_migrations(version, applied_at, checksum)`。启动时：

- 按版本排序。
- 校验已应用 checksum。
- 使用 PostgreSQL advisory lock 保证多实例只迁移一次。
- 每个迁移事务执行。
- 生产环境迁移失败则停止启动，不带病提供服务。

已有三表作为 V001 基线纳入迁移，避免先删表重建。

### 4.2 通用数据库规则

- 所有业务时间使用 `timestamptz` 和服务器 UTC。
- 金币、魂、碎片、数量用整数，数据库约束 ≥0。
- 装备、订单、结算用 UUID/UUIDv7 或 ULID；全局唯一且日志可检索。
- 业务枚举落 smallint/varchar 时有 CHECK；协议枚举使用英文字符串。
- 可变聚合带 bigint version。
- 金额扣减使用条件更新或行锁，不能先 SELECT 再无条件 UPDATE。
- 所有 SQL 参数化。
- 事务内写业务表和审计流水；外部事件在提交后发布。

### 4.3 幂等

建议表：

```text
idempotency_records
  player_id
  scope
  request_id
  request_hash
  status
  response_json
  created_at
  expires_at
  PRIMARY KEY(player_id, scope, request_id)
```

同 requestId + 同请求体返回原结果；同 requestId + 不同请求体拒绝。购买、强化、上架、市场购买、准备、奖励确认、撤离结算全部适用。

## 5. 持久数据模型

以下是目标逻辑模型。字段可按迁移细化，但约束不能丢。

### 5.1 玩家与资产

| 表 | 关键字段/约束 |
| --- | --- |
| players | 已有档案、selected_class、version |
| player_wallets | gold、diamond；非负；diamond 原型只记账 |
| player_materials | warrior_soul、priest_soul、mage_soul、guardian_soul、equipment_fragments |
| player_cards | player_id、card_id、unlocked、copy_count、level 0–5、version |
| player_decks | player_id、class、version、updated_at |
| player_deck_cards | deck_id、slot_index 0–19、card_id；恰好 20 在应用层+约束事务校验 |
| class_weapons | player_id、class、level 0–5；每职业唯一，不可删除 |
| equipments | instance_id、owner_id、slot、quality、element、affix、red_affix、level、bind_state、location、version |
| player_loadouts | player_id、class、五个 equipment_id；武器不放可卸槽 |
| player_consumables | health_potion_count、advanced_bag_count、top_bag_count |
| player_daily_counters | reset_key、商品购买次数等 |

装备 location 状态建议：

```text
Inventory
Equipped
MarketListed
PreparationLocked
InMatchEquipped
InMatchBackpack
RelicPile
EnhanceMaterialConsumed
```

同一装备同一时刻只能有一个 location。所有状态转换由服务完成，客户端不能直接更新 location。

### 5.2 商店与市场

| 表 | 关键字段/约束 |
| --- | --- |
| shop_rotations | date/reset_key、3 个单卡、config_version |
| shop_purchases | player_id、product_id、reset_key、count、request_id |
| market_listings | listing_id、seller_id、equipment_id、price_gold、status、version、expires_at |
| market_transactions | listing_id、buyer_id、seller_id、price、fee、seller_net、completed_at |

市场约束：

- 设备必须属于卖家、Inventory 状态、未绑定、未穿戴、未锁定。
- 卖家 Active listing ≤8。
- 价格为正，原型只金币。
- 购买事务锁 listing；检查 Active/version/未过期；扣买家；转装备；入卖家净额；写手续费。
- 到期任务把装备退回资产；不得丢失。

### 5.3 准备与匹配

| 表 | 关键字段/约束 |
| --- | --- |
| preparations | preparation_id、player_id、snapshot_json、status、config_version、expires_at |
| preparation_assets | preparation_id、asset_type、asset_id、quantity |
| match_tickets | ticket_id、player_id、preparation_id、status、queued_at |
| matches | match_id、room_id、mode、difficulty、seed、config_version、status |
| match_players | match_id、player_id、spawn、state、settled_at、settlement_id |

preparation snapshot 是不可变战局快照。进入队列后不能继续读取玩家当前装备来改变本局属性。

准备创建时把快照内防具从 `Equipped` 切到 `PreparationLocked`；取消、过期或 Ready 剔除时恢复。正式开房事务把防具转为 `InMatchEquipped` 并扣除带入药剂；付费包保持逻辑预留。撤离结算按来源恢复 `Equipped`/`Inventory`、返还未用药剂并释放付费包；死亡防具转 `RelicPile`、解绑配装，并原子消耗付费包。

### 5.4 房间、遗物和结算

| 表 | 关键字段/约束 |
| --- | --- |
| room_snapshots | room_id、revision、snapshot_jsonb、rng_state_jsonb、updated_at |
| room_event_buffers | 可选短期；sequence、event_json、expires_at，用于重连，不作为事件溯源 |
| relic_piles | pile_id、room_id、grid、dead_player_id、version、status |
| relic_items | pile_id、asset_kind、asset_snapshot/ref、quantity |
| match_settlements | settlement_id、match_id、player_id、result、details_jsonb、created_at、acknowledged_at，UNIQUE(match_id, player_id) |
| economy_ledger | ledger_id、player_id、match_id/request_id、currency、delta、balance_after、reason、created_at |
| inventory_movements | movement_id、item_id、from_location、to_location、reason、match_id |

结算唯一约束是防重的最后一道保险。即使客户端重复请求或服务重启，同一 match/player 只能有一条结算。

## 6. 新玩家初始化

`PlayerProvisioningService` 在新内部 UserId 创建事务中幂等执行：

- 创建钱包和材料账户。
- 解锁共用初始 30 张。
- 解锁三职业各 7 张白职业卡。
- 创建三职业默认 20 张编组。
- 创建三把 +0 专属武器。
- 创建三职业五部位空配装。不发放绑定白鞋或任何起始防具。
- 创建空的 50 格养成背包视图。

起始金币、钻石、药剂和付费包数量 GDD 未规定，不应由程序员随意赠送；保持配置化并由策划确认。

同一身份并发首次登录时只能初始化一次。使用唯一键+事务，不依赖“先查不存在”。

## 7. 静态配置与规则版本

### 7.1 配置分类

| 配置 | 例 |
| --- | --- |
| 卡牌 | 200 图鉴、怪物卡、等级效果 |
| 装备 | 品质、元素、词缀、强化 |
| 地图 | 层、泉水/撤离/宝箱权重 |
| 怪物 | O/M/E/Boss 组和意图 |
| 掉落 | 三选一、金币/魂/碎片 |
| 经济 | 商店商品、价格、限购、市场费率 |

防具强化材料规则属于服务端权威校验：+4/+5 各消耗 1 件同品质仓库装备，绑定材料允许；红装只接受红装材料。当前原型不投放红装，红装强化随未来红装掉落/周配额一同开放，不得仅在客户端隐藏后由接口提前投放。

每次发布生成：

- `configVersion`。
- 内容 hash。
- 服务端强类型加载结果。
- 客户端只读配置包。
- GDD 验收黄金向量。

房间开始锁定 configVersion，运行中不能被热配置改变。大厅商店可按新版本刷新，但进行中房间继续使用入房版本。
Excel 策划源表采用固定五行元数据：字段名、`string/int64/double/bool`、是否必填、`both/server/client`、说明；第六行起为数据。首列为稳定主键。`tools/export-config.ps1` 先校验后输出同字节的前后端 Protobuf 配置包、版本文件与 SHA-256；不得输出运行时 JSON 副本。权威状态机、公式执行、权限、事务、协议字段号和数据库 schema 留在代码/迁移中。

### 7.2 两端规则一致

GDD 要求部分公式两端各实现一份，PVP 服务端为准。做法：

- 服务端在 `FantasyCard.Domain.Combat` 实现权威算法。
- 客户端保留 Game.Domain 做预览。
- 两端共同消费同一版本化配置。
- 维护同一份 JSON 黄金用例：A0=41、A=46、A2=32、A4=23/46、燃料 12/14/16；A5 装备对位和载壁按 GDD §3.6 现行逐牌取整向量。
- CI 分别跑两端，任一不一致阻止合并。

## 8. REST 模块

### 8.1 当前保留

- `POST /api/v1/auth/local`。
- `GET/PUT /api/v1/players/me`。
- 健康检查。

生产构建必须禁用或强保护 local auth，不能让公网用户伪造 deviceId 登录。

### 8.2 目标端点

| 模块 | 端点 |
| --- | --- |
| Bootstrap | `GET /api/v1/bootstrap`（当前已实现基础大厅快照） |
| Cards/Decks | `GET /api/v1/cards`；`GET/PUT /api/v1/decks/{class}`（当前已实现） |
| Inventory | `GET /api/v1/inventory`；`GET/PUT /api/v1/loadouts/{class}` |
| Enhance | `POST /api/v1/equipment/{id}/enhance`；`POST /api/v1/class-weapons/{class}/enhance` |
| Shop | `GET /api/v1/shop`；`POST /api/v1/shop/purchases` |
| Market | `GET /api/v1/market`；`POST /listings`；`POST /{id}/purchase`；`DELETE /{id}` |
| Preparation | `POST/GET/DELETE /api/v1/preparations`（当前已实现创建/当前查询/按 ID 取消） |
| Settlement | `GET /api/v1/settlements/{id}`；`GET /api/v1/matches/{id}/settlement`；`POST /api/v1/settlements/{id}/acknowledge` |

普通业务不要塞进 WebSocket。市场搜索、图鉴、商店、强化都走 REST。

## 9. WebSocket 会话与可靠性

### 9.1 ConnectionRegistry

按 playerId 管当前连接：

- 同账号多连接策略必须明确。原型建议“最后连接接管实时会话”，旧连接收到 session.replaced 后关闭。
- 连接对象只负责传输，不持有永久业务状态。
- 断线 15 秒内不等于离房/死亡，可 resume；满 15 秒按死亡结算（SERVER_SPEC）。1v1 断线等待期间双方停手。

### 9.2 协议路由

`RealtimeCommandRouter`：

1. 解析外壳。
2. 鉴权并绑定 playerId。
3. 校验 requestId/大小/速率。
4. 根据玩家状态路由 Matchmaking 或 RoomActor。
5. 返回 ack/业务事件/error.command_rejected。

### 9.3 sequence 与重连

- 每玩家会话/活动房间维护单调 sequence。
- 近期事件缓存在内存，可选同步 Redis；缓存丢失时用 room snapshot。
- `session.resume(lastSequence, roomId, roomRevision)`。
- 事件投递至少一次，客户端去重。
- 状态改变本身只执行一次，依赖 requestId 幂等。

## 10. 匹配与房间 Actor

### 10.1 匹配

原型只一个队列：

- mode = ChaosRealm。
- difficulty = Standard。
- 1–4 名真人。
- 满 4 立刻开；否则等待 **30 秒** 后按 GDD 5.14 补位机器人到 4。

匹配入队前重新校验 preparation 仍有效且资产锁仍在。成房事务把 tickets 置 Matched，创建 match/match_players，生成 seed。

### 10.2 RoomActor

每房一个串行命令队列，可用 `Channel<RoomCommand>`：

```text
WebSocket commands
    → validate session
    → enqueue RoomCommand
    → one reader mutates RoomState
    → increment revision
    → build per-player events
    → checkpoint when required
```

优点：

- 同格配对、奖励替换、遗物争抢天然串行。
- 不需要给每个怪、手牌、遗物加独立锁。
- 所有计时和随机顺序可复现。

RoomActor 不直接在内存里永久加金币。涉及账号资产的动作通过事务服务完成，再把结果回写房间。

### 10.3 计时器

统一 `TimeProvider` + 房间调度队列：

- 抽牌到点。
- 怪意图/前摇。
- 后手 0.8 秒。
- 双方离开 8 秒。
- 逃脱读条 2 秒/冷却 12 秒。
- 停战 45 秒。
- 泉水 1.2 秒。
- 药剂不进入计时队列：行动栏点击后立即消耗 1 瓶并恢复。
- 撤离 3 秒。

不要为每个计时器创建长期 Task.Delay。RoomActor 每次处理命令/最早到期任务后计算下一个唤醒点。

### 10.4 随机数

服务端生成 room seed，并为不同子系统派生独立流：

- map。
- spawn。
- monsterGroups。
- treasure。
- per-player deck PVE。
- per-duel deck。
- reward。
- escape。

保存流计数/状态到 room snapshot。客户端永远不提交随机结果。只下发种子也不能替代服务端权威，尤其隐藏信息和 PVP。

## 11. 地图与玩家投影

### 11.1 MapState

房间创建时一次生成并钉死：

- 6×6、三层。
- Boss 核心格。
- 全部泉水。
- 1–2 随机外/中撤离。
- 外层 0–3 匣灵格。
- 1–4 出生格，互异且尽量分散。
- 每格怪物组。

每玩家独立：

- 当前格。
- 已喝泉水集合。
- 每格 PVE 实例和已清状态。
- 手牌/库/弃/蓄能。
- HP/盾/本命/临时包。
- 冻结快照槽（切 1v1 时写入，见 SERVER_SPEC）。
- 进格豁免。

共享：

- 房间格子配置。
- 同格玩家集合。
- PVP duel。
- 停战缓存。
- 遗物堆。

### 11.2 隐藏信息

实现 `RoomProjectionBuilder.BuildFor(playerId)`。给客户端的全图只含：

- 6×6 形状。
- Boss。
- 全部泉水。
- 自己位置和合法邻格。

进入格子后才在“本格上下文”返回随机撤离、匣灵、可操作遗物等。不要因为内部 MapState 有全部数据就直接序列化。

## 12. PVE

### 12.1 独立实例

同一格的怪物组模板共享，但每个玩家创建独立 `PveInstance`：

- monsters：HP、盾、意图 index、nextActionAt、控制窗口。
- player battle state。
- deck state。
- target。
- status：Active/Frozen/Cleared/Dead。

A 对 Boss 的伤害绝不写到 B 的实例。

### 12.2 战斗命令

`battle.play_cards` 只接受：

- battleId。
- targetId。
- 当前手牌实例 ID 列表。
- expectedRevision/requestId。

服务器验证状态、所有权、手牌、目标、控制、后手锁，再调用权威 CombatService。不要接受客户端的 expectedDamage、comboMultiplier、rngResult。

### 12.3 抽牌

- 进图本局池洗牌抽 3。
- 基准 4 秒，装备间隔服务端计算。
- 满 5 到点：不抽、蓄能清零、不累计。
- 打出入弃；库空洗弃。
- 焚弦/即时抽也受 5 上限。
- 临时池原型为空。
- 怪物击杀卡进弃牌，不占包。

抽牌计时只在战斗/规则允许的状态推进。切 PVP 时冻结 PVE deck 和 timers。

### 12.4 怪物意图

按 GDD `5.13：

- 每只独立意图循环。
- 间隔、前摇、眩晕取消、蓄力/强化。
- 两怪同帧按左到右。
- 服务端发 intent updated/resolved，不依赖客户端帧。
- PVE 不能逃。

## 13. PVP

### 13.1 配对

在以下时机调用同一 `TryPairIdlePlayers(grid)`：

- 玩家进入格。
- PVP 结束后变空闲。
- PVE/三选一结束进入行动栏。

按进入格更早优先。排除：

- 正在 PVP。
- 双方成对停战。
- 双方进格豁免。

若进格时其他人全在 PVP，为新进者和当时交战双方写双向豁免。

### 13.2 开始

- 冻结双方 PVE 怪物实例，并按 GDD 2.2 / SERVER_SPEC 写入完整快照（生命、护盾、三堆、蓄能、焚弦 C、加速、眩晕窗口）。
- PVE 实例必须深拷贝全部怪物运行态：生命、护盾、意图索引、间隔/前摇、蓄力、强化、眩晕和其他状态计时；1v1 期间完全暂停，不能只冻结对象引用。
- 1v1 工作副本：生命/护盾从快照拷贝；各自本局池新洗抽 3；蓄能 0；焚弦 C=0。
- 后进入者锁 0.8 秒；同帧随机先手。
- PVP 关闭临时抽。

### 13.3 结束

- 击杀：败者死亡结算（不恢复快照）；胜者留格并可能继续被匹配，并恢复己方快照。
- 双方离开：8 秒内双方都点，写停战，双方恢复快照。
- 强制逃脱：权威读条和掷骰，成功写停战，双方恢复快照。
- 非死亡结束：丢掉 1v1 副本，恢复冻结快照（含生命/护盾与三堆）。不要把 1v1 结束时的血条写回 PVE。
- 恢复后重新跑一次匹配判断。

逃脱公式中的 G 是百分点，不是 0–1 小数；必须有黄金测试。

## 14. 三选一、背包与遗物

### 14.1 临时背包

RoomState 中用明确 slot 模型：

- 容量 20/28/36。
- safe slots 0/1/3。
- 金币、勇士魂、当前职业魂、碎片各自可堆 1 格。
- 装备每件 1 格。
- 药剂每瓶 1 格。
- 药剂仅行动栏可用；按职业基础生命 L 的 20% 先取整，再吃生息回复比例并截在 L'，点击即结算、无读条。
- 卡牌和专属武器不进格。

安全标记只作用临时包格，不作用穿戴五件。

### 14.2 三选一

每次 PVE 胜利固定：

1. 装备。
2. 碎片。
3. 按层即时回血。

服务端生成并保存 rewardSet；客户端刷新/选择都引用该 ID。每玩家每局刷新次数独立，价格 60/180/450，先临时金币再账号金币。

账号金币参与刷新时，需要数据库事务扣账；临时金币和账号金币扣减必须形成一个不可分割业务结果。可先在事务中锁账号钱包，再由 RoomActor 提交临时包变化。

### 14.3 两种替换

三选一：

- 确认后旧物进入 pending recycle。
- 离开界面/已确认后被 PVP 打断即系统回收。
- 不进遗物。

遗物检索：

- 包满时自己的旧物原子放回正在检索的同一堆。
- 堆 version 增加。
- 多人并发由 RoomActor 串行。

必须使用两个不同命令/领域类型，禁止一个通用 `ReplaceItem` 通过布尔参数混用。

## 15. 撤离、死亡与结算事务

### 15.1 SettlementService

接口应是幂等领域用例：

```text
SettleExtraction(matchId, playerId, requestId)
SettleDeath(matchId, playerId, deathContext, requestId)
```

流程：

1. 打开数据库事务。
2. 锁 match_player 和相关玩家资产。
3. 查询 UNIQUE(match_id, player_id)；已有则返回原结算。
4. 验证房间提交的签名/内部调用上下文。
5. 应用资产转移。
6. 写经济流水、物品移动、结算详情。
7. 更新 match_player settled。
8. 提交。
9. RoomActor 收到成功结果后发布 match.settled。

当前运行时把步骤 5–9 拆成持久托管：RoomActor 终局快照先由结算协调器幂等创建 settlement、Pending holds 与 outbox；后台原子提交 holds 后才允许发布 `settlement.ready`/`match.settled`。数据库确认 match 为 `Completed`/`Aborted` 后，后台从 RoomRegistry 移除 Actor 和玩家映射，停止终局房间 tick；资产提交失败仍由 PostgreSQL Pending holds 重试，不依赖 Actor 常驻。服务冷启动时，`settlement-recovery` readiness 在后台完成首次扫描前保持失败；扫描异常或任一 settlement 提交失败时继续拒绝就绪，后续无失败扫描会自动恢复。

### 15.2 撤离

- 五防具仍归玩家。
- 临时资源入账号。
- 临时装备入养成背包。
- 未用药剂回仓库。
- 付费包释放预留，不消耗。
- 本局怪物卡清除。

### 15.3 死亡

- 安全格入账号。
- 五防具+非安全临时物资移动/快照到房间遗物堆。
- 专属武器不动。
- 卡牌不动，怪物卡清除且不进堆。
- 付费包数量 -1；默认免费包无消耗。
- 不补鞋、不补防具；配装栏保持空。

遗物仍属于进行中房间，直到被捡或本局结束清空。死亡结算必须先持久记录这些物品的所有权/托管状态，不能只留在易失内存。

### 15.4 待策划确认的边界

GDD 未完全规定以下情况，进入 S7/S8 前确认，不由服务端自行删除物品：

- 50 格养成背包已满时成功撤离的新装备如何安置。
- 市场到期退回时养成背包已满如何安置。
- 买市场装备时最后一个格被并发占用的玩家提示。
- 服务器崩溃且房间长时间无法恢复时，带入资产的补偿/回滚策略。
- ~~PVP 长时间断线的最终处理时限~~：已锁，见 SERVER_SPEC（15 秒等待双方停手，超时断开方死亡）。
- 起始金币/药剂/付费包数量。

推荐工程上预留“待领取/托管”能力，但是否展示收件箱、是否占 50 格需产品确认后再实装。

## 16. 商店与市场事务

### 16.1 商店

服务端使用服务器时区周/日重置键，当前商品日刷新为 04:00。

购买事务：

1. 幂等记录。
2. 锁钱包和 counter。
3. 校验商品开放、限购、价格。
4. 条件扣金币。
5. 服务端随机礼包结果。
6. 入卡/材料/消耗品。
7. 写 ledger/purchase。
8. 返回余额和具体结果。

钻石商品在原型配置中根本不发布，不只是在客户端隐藏。

### 16.2 市场

购买同一 listing 的并发测试是上线门：

- `SELECT ... FOR UPDATE` 或单条条件 UPDATE 抢占。
- 只有 Active + version 匹配者成功。
- 买家扣款、卖家入账、10% 费、装备转移、listing 完成同事务。
- 失败者不扣款。

市场搜索读模型可缓存，但购买必须回 PostgreSQL 验证。

## 17. 房间快照与进程恢复

### 17.1 快照时机

- room.started。
- 玩家进入新格。
- PVP 开始/结束。
- PVE 胜利/死亡。
- 奖励确认、遗物移动。
- 撤离开始/完成。
- 每隔短周期做脏状态节流快照。

快照包含：

- revision/configVersion。
- 地图、所有玩家私有实例。
- deck 三堆顺序和抽牌进度。
- RNG 各流状态。
- duel/豁免/停战。
- 临时背包、奖励、遗物。
- 所有计时截止时间。

### 17.2 恢复

1. 服务启动先恢复 `Launching` match（按已持久化席位重建首份快照），再扫描 Running match。
2. 取得 room ownership/advisory lock。
3. 加载最新快照。
4. 根据 serverTime 推进已过期计时任务，严格按截止时间顺序。
5. 重建 RoomActor。
6. 玩家重连时给 snapshot。

当前实现读取 `room_snapshots.updated_at` 计算停机时长，在恢复后的 RoomActor 单读队列中按 100ms 权威 tick 回放，再将最终关键快照写回 PostgreSQL；恢复中途失败会移除半注册 Actor 并拉低 readiness。该链路已用随机 schema PostgreSQL 测试覆盖 Running 房间、玩家映射、matchId、断线超时、RNG 状态与补偿快照持久化。

这不是事件溯源：无需靠全量历史事件重建；事件缓冲只服务短期重连。

## 18. 安全

- Production 禁止 local auth。
- Steam/微信票据必须由服务端向平台验证，不能信客户端 UserId。
- access token 只存 hash；支持撤销/过期清理。
- WS query token 从访问日志和代理日志中脱敏。
- 对登录、市场搜索、购买、WS 命令做分层限流。
- 名称去首尾空格并做 NFKC 规范化，按数据库小写规则全局唯一。本地开发登录按名称绑定内部 UID：同名重登，新名称注册独立账号；设备 ID 不决定账号。本地账号名不能经档案更新改为另一个名称，Steam 等平台账号仍按已验证的平台身份登录。
- REST 严格限制 JSON 深度；WebSocket Protobuf 严格限制消息≤16 KiB、集合长度和 cardInstanceIds≤5。
- 房间命令验证 playerId 来自连接上下文，不从 payload 信任。
- 管理端与玩家端路由隔离；红装/发货等未来运维动作要审计。
- 依赖和容器镜像定期扫描；开发密码不能用于生产。

## 19. 可观测性

### 19.1 日志字段

`traceId`、`requestId`、`playerId`、`sessionId`、`matchId`、`roomId`、`battleId`、`roomRevision`、`eventSequence`、`commandType`、`resultCode`、耗时。

经济日志额外含：

- reason。
- currency/item。
- delta/from/to。
- balanceAfter。
- settlementId/listingId/productId。

### 19.2 指标

- 登录成功/失败、token 过期。
- WS 在线、重连、消息大小、命令拒绝。
- 排队时长、房间数、人数分布。
- RoomActor 队列长度、tick 延迟、快照耗时。
- PVE/PVP 时长和异常结束。
- 结算成功/重试/幂等命中/失败。
- 货币 source/sink、市场成交/冲突、商店购买。
- 数据库池、慢查询、迁移状态。

### 19.3 告警

至少为以下建立告警：

- readiness 失败。
- 结算失败或积压。
- 经济余额出现负数/账实不符。
- 同 match/player 多结算约束冲突。
- RoomActor 延迟持续升高。
- PostgreSQL 连接/磁盘/备份异常。

## 20. 测试

### 20.1 Domain 单测

必须覆盖：

- 玩家生命、护盾、L'。
- 编组规则。
- 装备品质/强化/词缀门槛和帽。
- 抽牌、满手轮空、弃牌洗回、PVP 快照。
- 全部 GDD 战斗黄金向量。
- 地图生成分布和确定性。
- 怪物意图、Boss 阶段。
- PVP 配对、豁免、停战、逃脱百分点。
- 背包堆叠、安全格、两种替换。
- 撤离/死亡资产分类。

### 20.2 Integration

使用真实 PostgreSQL 容器：

- 登录并发初始化。
- profile version 409。
- 购买幂等、余额不足。
- 强化材料事务。
- 同市场 listing 并发购买。
- preparation 资产锁。
- settlement 重试/进程中断。
- 遗物转移。
- 迁移从空库和上一版本升级。

### 20.3 Protocol

- REST JSON 字段 camelCase、字符串枚举、未知字段兼容。
- WebSocket Protobuf v1 的命令/事件往返、未知字段兼容、错误版本拒绝和文本帧拒绝。
- 所有命令/事件序列化快照测试。
- 消息上限。
- sequence 去重/跳号。
- 旧客户端忽略新可选字段。

### 20.4 Room 模拟

用虚拟 TimeProvider，不真正 sleep：

- 1/2/4 玩家完整局。
- A 打 Boss、B 入侵、C 豁免的 GDD 时序。
- 同格两场并行 1v1。
- PVP 切入和恢复 PVE。
- 逃脱读条被生命伤打断/被盾挡不打断。
- 撤离读条被合法玩家打断。
- 断线、进程恢复、过期计时推进。

### 20.5 Load

原型发布前至少验证：

- 目标并发 WS 数。
- 多房间 RoomActor tick 延迟。
- 高频 battle.play_cards 和事件广播。
- 市场分页与购买热点。
- 快照写入对 PostgreSQL 的影响。

具体容量目标由发行预估确定，测量后扩容；不要先拆微服务。

## 21. 部署与运维

### 21.1 本地

保留当前：

- `server/start-server.bat`。
- `server/stop-server.bat`。
- `docker compose up -d --build`。

补充：

- 一键应用迁移。
- 创建测试玩家/清理仅本地数据的显式脚本。
- 不把本地清库逻辑编进生产。

### 21.2 Staging/Production

- Linux 容器、非 root 用户。
- HTTPS/WSS 在反向代理或应用终止。
- 密钥从 Secret Store/环境注入。
- PostgreSQL 自动备份和恢复演练。
- 发布前迁移检查。
- 房间 drain：新版本停止接新房，旧房完成/迁移后下线。
- configVersion 与客户端构建建立兼容矩阵。
- 回滚应用不能回滚已经不兼容的数据库迁移；迁移优先向前兼容。

首版不需要 Kubernetes。单实例/少量实例 + PostgreSQL 足以验证，扩容后再引入房间 ownership 和 Redis 协调。

## 22. 实施阶段

| 阶段 | 交付 | 完成门 |
| --- | --- | --- |
| S0 基础 | SQL 迁移、幂等、协议外壳、集成测试、生产禁 local auth | 骨架可演进 |
| S1 玩家聚合 | provisioning、bootstrap、钱包/卡牌/装备/编组 | 登录后完整大厅数据 |
| S2 大厅业务 | 穿戴、强化、商店、市场 | 持久资产闭环 |
| S3 准备/匹配 | preparation 锁、队列、match、RoomActor、**5.14 补位机器人** | Hall→Room |
| S4 地图 | 权威生成、隐藏投影、移动、格状态 | 进入 PVE |
| S5 PVE | deck、combat、monster、奖励 | 打怪→行动栏 |
| S6 PVP | 配对、冻结恢复、离开、逃脱、停战 | 同格规则通过 |
| S7 背包/遗物/结算 | 安全格、替换、撤离、死亡、幂等结算 | 完整一局 |
| S8 经济完善 | 日轮换、限购、市场到期、审计对账 | 原型经济闭环 |
| S9 可靠性 | resume、快照恢复、限流、负载、部署 runbook | 发布候选 |

推荐每阶段都交一个客户端可用的纵向片，不在服务端一次性写完所有表后才联调。

当前代码已交付 S0/S1 主体和 preparation 纵向切片；下一执行顺序为 P0 数据库集成验收 → S2 大厅资产事务 → S3 匹配/RoomActor。具体任务拆分以 [服务端现状审计与开发计划](./SERVER_IMPLEMENTATION_STATUS_AND_PLAN.md) 为准。

## 23. 服务端最终验收

- [ ] 当前登录/档案协议保持兼容。
- [ ] 新玩家初始化只发生一次。
- [ ] bootstrap 可恢复未完成房间/结算。
- [ ] 卡组、穿戴、强化、商店、市场全部服务端校验。
- [ ] preparation 锁定资产，取消/失败释放。
- [ ] 1–4 人标准难度可成房；未满 4 时 30 秒后补机器人。
- [ ] 地图隐藏信息按玩家过滤。
- [ ] PVE 实例完全独立。
- [ ] 手牌/抽牌/战斗/怪意图服务端权威。
- [ ] PVP 配对、豁免、后手、停战、逃脱通过 GDD 时序。
- [ ] 三选一刷新、包满回收、遗物回堆严格区分。
- [ ] 撤离/PVE 死/PVP 死结算原子且幂等。
- [ ] 专属武器永不进入遗物/市场/材料。
- [ ] 经济有流水，余额不为负，市场并发只有一个买家成功。
- [ ] WS 可 resume；缺事件时可发 snapshot。
- [ ] 服务进程重启能恢复 Running room 或安全完成补偿流程。
- [ ] 本地、Staging、Production 配置隔离，生产没有 local auth。
- [ ] 迁移、备份、恢复、日志、指标、告警和发布 runbook 可用。
