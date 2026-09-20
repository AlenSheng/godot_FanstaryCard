# Relicbound（遗境行者）端到端流程与协议

| 项目 | 内容 |
| --- | --- |
| 文档版本 | 1.3 |
| 基准 | GDD v0.64 |
| 目标链路 | 登录 → 大厅 → 探索准备 → 匹配 → 地图 → 战斗 → 战利品/行动 → 撤离或死亡 → 结算 → 大厅 |
| 协议原则 | REST 管持久业务，WebSocket 管匹配、房间和战斗；服务端权威 |

> 标有“当前”的接口已存在于仓库；标有“目标”的接口/事件是后续实现约定。实现目标协议时应保持当前 `/api/v1`、`/ws/v1` 前缀和向后兼容规则。

## 1. 全流程总览

| 阶段 | 客户端页面/状态 | 客户端动作 | 服务端权威动作 | 成功出口 |
| --- | --- | --- | --- | --- |
| 0 启动 | Boot | 读环境配置、设备 ID、令牌、资源/配置版本 | 健康检查、配置版本响应 | 进入自动登录或登录页 |
| 1 登录 | Login | 本地开发登录；正式版走平台票据 | 验证身份，映射内部 UserId，签发会话 | 获得 token 和玩家档案 |
| 2 引导/大厅装载 | HallLoading | 拉取 bootstrap，连接 WebSocket | 返回档案、钱包、卡牌、装备、编组、商店摘要 | HallReady |
| 3 大厅 | Hall | 换职业、编组、穿戴、强化、商店、市场 | 校验版本、资产所有权、橙红唯一、消耗事务 | 可进入探索准备 |
| 4 探索准备 | Preparation | 选择 20 张卡组、五防具、包档、0–2 药剂 | 生成不可变准备快照并锁定/预留资产 | 可加入匹配 |
| 5 匹配 | Queue | 加入/取消标准难度队列 | 满 4 名真人立刻开；否则等 30 秒用机器人补到 4；生成 roomId、seed、configVersion | MatchFound |
| 6 房间加载 | MatchLoading | 预加载 Run 场景和资源，发送 ready | 等待玩家 ready，超时剔除/补为少人局 | RoomStarted |
| 7 地图/进格 | InRun.Map | 查看允许情报，点四邻移动 | 校验不能向外；进格后才揭示本格；尝试配对 PVP | PVE、PVP 或行动栏 |
| 8 PVE | InRun.PVE | 选目标、选 1–5 张手牌、释放 | 抽牌、意图、伤害、本命、怪物卡全部权威结算 | PVEVictory 或 Death |
| 9 PVP | InRun.PVP | 出牌、双方离开、强制逃脱 | 冻结 PVE 和三堆；重置抽 3；后进后手；权威结算 | 胜负、停战或恢复 PVE |
| 10 三选一 | InRun.Choice | 装备/碎片/即时回血；可刷新；包满替换 | 生成三项、扣刷新金、确认替换回收 | 行动栏 |
| 11 行动栏 | InRun.Action | 泉水、药剂、遗物、撤离、移动 | 校验非战斗、次数、包容量、撤离条件；药剂点击即结算、无读条 | 下一格、撤离或被拉 PVP |
| 12 撤离 | InRun.Extracting | 确认并等待 3 秒 | 可配对玩家出现则取消；成功后原子结算 | Settlement.Success |
| 13 死亡 | InRun.Dead | 只看结果，不自行生成掉落 | 五防具+非安全物资入遗物堆；专属武器保留；付费包消耗 | Settlement.Death |
| 14 结算 | Settlement | 展示带出/损失/成长，确认返回 | 结算幂等落库，释放房间资产锁 | 回大厅并重新 bootstrap 增量 |

## 2. 共同状态机

### 2.1 客户端应用状态

```text
ColdStart
  → Bootstrapping
  → Authenticating
  → LoadingProfile
  → ConnectingRealtime
  → HallReady
  → Preparing
  → Queued
  → MatchLoading
  → InRun(Map | PVE | PVP | Choice | Relic | Action | Extracting)
  → Settling
  → HallReady
```

任何状态都可能进入 `ConnectionRecovering`。恢复成功后，以服务端 `session.snapshot` / `room.snapshot` 为准回到正确状态；恢复失败且令牌无效则回 `Authenticating`；房间已结算则进入 `Settling`，不能直接丢回大厅。

### 2.2 服务端玩家会话状态

| 状态 | 允许的主要操作 | 禁止 |
| --- | --- | --- |
| Offline | 登录 | 业务写入 |
| OnlineInHall | 大厅 REST、准备、加入匹配 | 战局命令 |
| Queued | 取消匹配、心跳 | 修改被准备快照锁定的资产 |
| LoadingRoom | ready、断线恢复 | 大厅资产写入 |
| InRoom | 房间/战斗命令 | 商店、市场、强化、改职业/编组 |
| Settling | 查询结算 | 重复发起结算 |
| OnlineInHallAfterSettlement | 大厅业务 | 使用旧 roomRevision |

### 2.3 格内玩家状态

沿用 GDD `5.5：

| 状态 | 可被拉入 1v1 | 可操作 |
| --- | --- | --- |
| InPVE | 是 | 出牌；不能背包/药剂/换装/移动/逃怪 |
| InChoice | 是 | 选择、刷新、包满替换 |
| InRelic | 是 | 检索一份遗物堆 |
| InAction | 是 | 泉水、药剂、撤离、移动 |
| Extracting | 是 | 等待读条；可被合法配对者打断 |
| InPVP | 否 | 出牌；8 秒双方离开；强制逃脱 |
| Dead / Extracted | 否 | 等待结算 |

## 3. 协议外壳

REST `/api/v1` 保持 JSON；本章仅描述 WebSocket。实时通道 `/ws/v1/session` 使用 `protocol/realtime/v1/realtime.proto`，每条 WebSocket **Binary** 消息承载一个 `ClientEnvelope` 或 `ServerEnvelope`，禁止 Text 帧及任何 JSON payload。

### 3.1 当前 Protobuf v1 信封

客户端信封保留 `type / request_id / expected_revision / payload`，服务端信封保留 `type / trace_id / payload / event_id / sequence / occurred_at_unix_ms / request_id / room_revision`，并统一带 `protocol_version=1`。具体字段号以 `.proto` 为唯一权威，不在文档复制另一份结构。

### 3.2 兼容扩展

- `payload` 必须按消息类型对应具名 Protobuf message；新增命令/事件同时补 schema、前后端编解码与快照测试。
- 未知字段忽略；未知 type 记录开发日志并安全忽略。
- 已发布字段号不得复用或改变语义；删除字段保留编号；破坏性变更新建 `v2`。
- 每条完整消息上限 16 KiB，支持 WebSocket 分片后再解码。

字段语义保持：`request_id` 用于幂等重试，`event_id` 唯一，`sequence` 单调递增，`room_revision` 标记权威房间版本，`occurred_at_unix_ms` 只用于展示/诊断，`trace_id` 不得含 token。

客户端必须按 sequence 去重；发现跳号发送 `session.resume`；命令超时重发必须复用 request_id。

### 3.3 房间命令同步与低延迟策略（当前实现）

- 客户端发送房间命令时直接使用最近一次已确认的 `room_revision`，不再采用“先读完整快照、再发送命令”的固定两次往返流程。
- `RoomActor` 是唯一权威串行队列。命令的 `expected_revision` 只拒绝**未来版本**；略旧版本仍会排队执行，并由玩法状态、目标和幂等 `request_id` 做最终校验。这样可以吸收服务端 100 ms tick 或同一房间前序命令造成的正常小幅滞后。
- 只有服务端返回 `error.command_rejected(code=REVISION_CONFLICT)` 时，客户端才请求一次 `room.snapshot.read`，按新快照重新校验原意图并换用新的 `request_id` 重发一次。重发再次失败、超时、断线、换房或目标/手牌失效时立即停止，不做无限重试。
- `room.snapshot` 是事件触发和恢复兜底消息，不再以 500 ms 周期轮询。移动、战斗结算、目标/奖励/遗物/行动状态变化等事件会合并触发一次节流快照；同一时间只保留一个待发读取请求。
- 普通命令的发送成功即表示已进入 WebSocket；客户端 UI 可立即进入等待态并继续渲染本地动画，不需要额外等待快照 ACK。最终状态仍以事件/快照为准，客户端预检仅用于减少无效往返，不能替代服务端校验。
- 服务器持久化和战斗表现观察者在权威命令完成后异步执行，并通过串行观察者尾保证顺序；快照观察者只保留最新待处理快照，避免慢数据库或慢连接拖住房间 actor、造成无界积压。
## 4. 启动、登录与大厅装载

### 4.1 启动顺序

1. 读取构建环境：Local / Dev / Staging / Production。
2. 初始化日志、异常捕获、平台适配、HTTP、WebSocket、时间同步。
3. 读取本地 `deviceId`、token、expiresAt、最后 sequence；token 不写日志。
4. 可选调用 `GET /health/ready`。失败时显示“服务器不可用”，退避重试，不每帧请求。
5. token 可用时尝试 `GET /api/v1/players/me`；收到 401 才清 token。
6. 无 token 时显示登录页并调用登录接口。
7. 获取 bootstrap 后建立 WebSocket；收到 `session.connected` 才标记实时会话可用。
8. 进入大厅。

### 4.2 登录

当前本地开发：

- `POST /api/v1/auth/local`
- 请求：`deviceId`、`displayName`
- 响应：`accessToken`、`expiresAt`、`player`

目标正式身份：

- Steam：客户端从 Steamworks 获取一次性票据，发送 `POST /api/v1/auth/steam`。
- 微信：平台适配层获取 code，发送 `POST /api/v1/auth/wechat`。
- 服务端都映射到内部 `UserId`，业务表绝不使用 SteamID/OpenID 作主键。

登录失败处理：

| 情况 | 客户端 |
| --- | --- |
| 400 | 显示本地化输入错误；开发详情可展开 |
| 401 | 清 token，回登录 |
| 网络超时 | 保留输入，指数退避，可手动重试 |
| 5xx | 记录 traceId，显示服务暂不可用 |
| 重复点击 | UI 防连点；服务端登录保持幂等身份映射 |

### 4.3 Bootstrap

当前 `GET /api/v1/bootstrap` 已返回玩家、钱包、材料、专属武器、穿戴、编组和背包摘要；后续阶段继续加入商店/市场摘要与未完成房间/结算。目标完整结构为：

```json
{
  "serverTime": "2026-08-29T06:40:00Z",
  "configVersion": "gdd-0.61-proto-1",
  "player": {},
  "wallet": {},
  "materials": {},
  "classWeapons": [],
  "equippedLoadouts": [],
  "decks": [],
  "inventorySummary": {},
  "shopRotation": {},
  "activeMarketListings": [],
  "unfinishedMatch": null
}
```

若 `unfinishedMatch` 非空，客户端优先恢复房间或展示已有结算，不能让玩家先改大厅资产。

## 5. 大厅业务

### 5.1 职业切换

- 当前：`PUT /api/v1/players/me`，带 `expectedVersion`。
- 409：重新 GET；刷新本地版本；询问业务层是否重放，禁止无限自动重试。
- 切换职业后，客户端立即显示对应生命 80/70/100、默认/已保存卡组和锁定专属武器。
- 战局状态下服务端拒绝切换。

### 5.2 编组

目标 REST：

| 方法 | 路径 | 用途 |
| --- | --- | --- |
| GET | `/api/v1/decks` | 三职业卡组 |
| PUT | `/api/v1/decks/{class}` | 保存某职业恰好 20 张 |

服务端校验：

- 恰好 20 张。
- 玩家拥有/已解锁且复制数量足够。
- 职业卡只能本职业。
- 通用橙最多 1，职业橙最多 1，可同时存在。
- 怪物卡不能编组。
- 当前战局/准备快照已锁定时不能修改该快照。

### 5.3 穿戴与强化

目标 REST：

| 方法 | 路径 | 用途 |
| --- | --- | --- |
| GET/PUT | `/api/v1/loadouts/{class}` | 五防具穿戴 |
| POST | `/api/v1/equipment/{id}/enhance` | 防具强化 |
| POST | `/api/v1/class-weapons/{class}/enhance` | 专属武器只碎强化 |

必须校验五部位、身上最多 1 橙/红、所有权、锁定/上架/战局占用状态。防具 +4/+5 各耗 1 件同品质仓库装备，绑定材料允许；红装只耗红装，随红装掉落/周配额开放，当前原型不可达。专属武器自动穿、不可卸、不交易、不进材料槽。

客户端穿戴草稿同步执行可确定的前置校验：同一件已选装备再次点击即卸下；未选装备为正向穿戴操作；橙/红在五件草稿中合计最多一件（替换同一部位允许）。命中该限制时客户端立即提示并不发保存请求。服务端保留全部权威校验，用于并发、资产状态和绕过客户端的请求。

### 5.4 商店与市场

所有购买/上架/购买市场项使用 `Idempotency-Key`。服务端事务同时写资产变化和经济流水。

客户端不乐观增加金币或物品；可以先播放等待态，成功响应后再更新。

## 6. 探索准备与匹配

### 6.1 创建准备快照

目标 `POST /api/v1/preparations`：

```json
{
  "class": "Mage",
  "deckVersion": 7,
  "equipmentIds": ["...5 ids..."],
  "backpackTier": "Advanced",
  "safeSlotIndexes": [27],
  "potionCount": 2,
  "difficulty": "Standard"
}
```

服务端返回 `preparationId`、完整快照、校验摘要和版本。准备快照包含：

- 出战职业与职业生命。
- 20 张卡及等级。
- 五件防具的完整不可变属性。
- 当前职业专属武器等级。
- 背包 20/0、28/1 或 36/3。
- 最多 2 瓶生命药剂。
- 只允许 Standard。
- `configVersion`。

高级/顶级包和药剂此时进入“预留”状态，不立即消耗；撤离释放预留，死亡才按结算事务消耗。

### 6.2 加入匹配

WebSocket 目标命令：

```json
{
  "type": "match.enqueue",
  "requestId": "01K...",
  "payload": {
    "preparationId": "...",
    "mode": "chaos_realm",
    "difficulty": "Standard"
  }
}
```

事件：

- `match.queued`：ticketId、queuedAt。
- `match.cancelled`。
- `match.found`：roomId、matchId、加载截止时间。原型不要求公开其他玩家身份或位置。补位机器人在服务端占席，**不下发** `isBot`。
- `room.ready_required`：matchId、roomId、15 秒绝对截止时间、当前/所需确认人数。
- 客户端发 `room.ready`，服务端先回 `room.ready_accepted`；全部真人确认后可提前开局。
- 截止时未确认真人被剔除并收到 `room.ready_removed`，服务端用机器人补齐到 4 席后向保留真人下发 `room.started`。
- `room.started` 携带该玩家的首份私有房间快照；即使全部真人都未确认，服务端仍按 4 个机器人完成该局的权威生命周期。

匹配期禁止修改准备快照中的卡组、装备、包和药剂。取消匹配释放预留。

## 7. 房间开始与地图

`room.started` 至少下发：

- roomId、matchId、roomRevision、configVersion。
- 当前玩家出生坐标。
- 6×6 基础形状。
- Boss 格。
- 全部泉水格。
- 当前坐标和允许移动的四邻。
- 自己的生命、有效上限、护盾、卡组三堆摘要、临时背包。
- 不下发他人位置、人数变化、交战、已清、随机撤离、宝箱怪、遗物等隐藏情报。

移动命令：

```json
{
  "type": "room.move",
  "requestId": "01K...",
  "expectedRevision": 12,
  "payload": {
    "to": { "row": 0, "col": 3 }
  }
}
```

服务端校验相邻、同层或向内、非战斗、玩家存活、无正在确认的 UI 操作。成功后发送 `room.player_moved`（仅本人需要的位置结果）和 `grid.entered`（只向本人揭示本格可见内容）。

首次可进入中层时，服务端可带 `requiresMiddleWarning=true`。客户端本地只展示一次；真正的移动限制仍由服务端校验。

## 8. 战斗开始

### 8.1 PVE 开始

`battle.started`：

```json
{
  "battleId": "...",
  "battleType": "PVE",
  "grid": { "row": 0, "col": 3 },
  "player": {
    "hp": 70,
    "maxHp": 70,
    "effectiveMaxHp": 70,
    "shield": 0
  },
  "hand": [],
  "libraryCount": 17,
  "discardCount": 0,
  "draw": {
    "intervalMs": 4000,
    "progress": 0,
    "serverDeadline": "..."
  },
  "monsters": [],
  "currentTargetId": "...",
  "battleRevision": 1
}
```

客户端用 `serverDeadline` 平滑显示蓄能，但抽到哪张、满手轮空、焚弦立刻抽均由服务端事件确认。

### 8.2 PVP 开始

触发条件由服务端按 GDD `5.5 配对。服务端必须先：

1. 冻结双方各自 PVE 怪物的生命、护盾、意图与计时。
2. 写入玩家冻结快照：生命、护盾、手牌/库/弃牌及抽牌 RNG 状态、蓄能、焚弦 C、PVE 抽牌加速剩余、对该怪的眩晕窗口（GDD 2.2）。
3. 1v1 工作副本：生命/护盾从快照拷贝；本局池新洗各抽 3；蓄能 0；焚弦 C=0。
4. 已在格内者先手；后进入者 0.8 秒不能出牌且蓄能不跳。
5. 发送 `duel.started`，包含双方公开战斗状态、leaveWindowEndsAt、lateJoinerUnlockAt。
6. 存活结束丢掉 1v1 副本并恢复快照；死亡不恢复。

PVP 不发送本场临时牌，不做职业元素相克。

## 9. 出牌与实时结算

客户端只提交意图：

```json
{
  "type": "battle.play_cards",
  "requestId": "01K...",
  "expectedRevision": 42,
  "payload": {
    "battleId": "...",
    "targetId": "monster-or-player-id",
    "cardInstanceIds": ["hand-1", "hand-3", "hand-4"]
  }
}
```

服务端按唯一流水计算：

1. 验证这些实例确实在当前手牌、未重复、玩家未眩晕、后手锁已结束。
2. 牌面 + 养成。
3. 紫燃料：1–3 同元素伤不加，4 张 +2，5 张 +4。
4. 职业显 floor。
5. 共振/向反、装备增伤、目标抗性，元素段整体 floor。
6. 直伤 + 破击逐张 floor，再做最终 floor。
7. 若防守者是盾且载壁激活，再乘减伤 floor。
8. 先扣盾再扣生命。
9. 处理治疗、上盾、控制、本命、抽牌。
10. 打出的牌入弃牌；击杀怪物时怪物卡入弃牌。
11. 增加 battleRevision / roomRevision，记录事件。

`battle.combo_resolved` 返回“表现结果”，不要求客户端重算：

- 每种元素段数字。
- 直伤段。
- 实伤及盾/血变化。
- 治疗、上盾。
- 眩晕/阻断/加速。
- 手牌移除、新抽牌、库/弃牌数量。
- 本命状态：焚弦 C/E、临渊倍率、载岳倍率。
- 击杀和怪物卡获得。

客户端表现规则：同系合并、异系分开；贴图闪一下 + 缩放一下；不等待长特效队列。

## 10. PVP 特殊命令

| 命令 | 校验 | 事件 |
| --- | --- | --- |
| `duel.request_leave` | 开打 8 秒内 | 单方已申请；双方都申请则 `duel.ended: mutual_leave` |
| `duel.start_escape` | PVP、未冷却、未读条 | `duel.escape_started`，2 秒截止 |
| 服务端伤害结算 | 读条时实际扣到生命 | `duel.escape_interrupted`；盾完全挡住不打断 |
| 服务端读条到期 | 按公式掷骰 | 成功 `duel.ended: escaped`；失败 `duel.escape_failed` + 12 秒冷却 |

结束后写入 45 秒或曼哈顿距离 ≥3 解除的成对停战缓存。非死亡结束时丢弃 1v1 工作副本，恢复进入 PVP 前的完整冻结快照：玩家生命、护盾、手牌/库/弃牌及抽牌 RNG 状态、蓄能、焚弦 C、抽牌加速、眩晕/阻断等状态，以及该玩家独立 PVE 实例内所有怪物的生命、护盾、意图索引、间隔/前摇、蓄力、强化、眩晕与其他计时状态。若一方死亡，死亡方不恢复；胜者恢复自己的完整快照后继续原 PVE 或行动栏。

## 11. PVE 胜利、三选一和行动栏

### 11.1 PVE 胜利

服务端在组内全部怪死亡后：

- 结算本层金币、勇士之魂、当前职业之魂、基础碎片。
- 无已有堆且临时包无空格时，额外资源按 GDD 系统回收。
- 为已击杀的怪物卡完成入弃牌记录。
- 生成固定三类奖励。
- 玩家进入 InChoice，仍可被合法玩家拉 PVP。

### 11.2 三选一

`reward.choice_offered` 必含：

- rewardSetId。
- 装备候选完整公开属性。
- 碎片数量。
- 按层计算的即时回血绝对值和预计写入值。
- 本局剩余刷新次数、下一次刷新价格。
- 是否需要包满替换。

命令：

- `reward.refresh`：同一 rewardSetId，扣 60/180/450；幂等。
- `reward.choose`：选择 Equipment / Fragments / Heal。
- `reward.confirm_replacement`：指定临时包格，或新装直接穿戴后指定卸下件。

确认后才改资产。已确认的三选一替换件在离开界面或被入侵时系统回收；未确认被入侵则整个选择取消，不扣、不回收。

### 11.3 行动栏

清怪并完成三选一后，服务端下发当前允许动作：

- `action.use_spring`：每人每泉一次，1.2 秒；可被 PVP 打断。
- `action.potion`：仅非战斗且背包有药剂；点击立即消耗 1 瓶并恢复，无读条；返回 `action.potion_used`。
- `action.open_relic`：一份遗物堆一个按钮。
- `action.start_extract`：本格有撤离点且自己的怪已清。
- `room.move`：服务端返回的合法四邻。

客户端只渲染服务端返回的动作集合，不能靠本地猜测显示可用按钮。

## 12. 遗物检索

打开某一堆时服务端创建短期操作会话 `relicSessionId`，返回该堆当前版本和物品。

拾取命令必须包含 pileId、pileVersion、itemId、目标包格或叠加目标。包满替换时，自己的旧物放回正在检索的同一堆，必须在一个事务/房间原子操作中完成。

多人同时检索同一堆时，房间串行处理；后到者收到版本冲突并刷新。专属武器和卡牌永远不能出现在遗物堆。

## 13. 撤离、死亡与结算

### 13.1 撤离

`action.start_extract` 后 3 秒：

- 合法可配对玩家出现：服务端取消读条并立即开 1v1。
- 只有豁免/停战对象出现：不打断。
- 读条成功：玩家离开房间互动，进入 Settling。

成功结算事务：

1. 锁定 player + match_player。
2. 检查该 matchId 尚未结算。
3. 身上五件防具保留。
4. 临时包全部合法物资转入养成资产；金币/魂/碎片入账；药剂回仓库。
5. 付费探索背包不消耗，只释放预留。
6. 清空本局怪物卡、临时战斗状态。
7. 写 settlement、经济流水和 inventory movement。
8. 提交后发布 `match.settled`。

### 13.2 死亡

死亡事务：

1. 安全格物资转回养成资产。
2. 身上五件防具 + 非安全格物资生成当前格的一份遗物堆，带死者名。
3. 职业专属武器保留且强化等级不变。
4. 编成、图鉴、普通卡、本局怪物卡不进入遗物堆。
5. 已装备付费探索背包消耗；免费包无本体可扣。
6. 不补鞋、不补防具；配装栏保持空。
7. 写 settlement 与审计流水。

### 13.3 结算事件

`match.settled` 至少返回：

- settlementId、matchId、result（Extracted / PveDeath / PvpDeath）。
- 入局前、结算后关键余额。
- 获得和损失的金币/魂/碎片。
- 带出、保留、掉入遗物、安全带回、系统回收的物品分组。
- 探索背包是否消耗。
- 卡牌解锁/等级和装备变化。
- 新玩家档案/资产版本。

客户端必须用这一份结果渲染结算页，不能根据本地临时包自行推导。

## 14. 断线恢复

### 14.1 重连顺序

1. 暂停可改变状态的按钮，但本地表现动画可结束。
2. 使用现有 token 重建 WebSocket。
3. 发送 `session.resume`，携带 lastSequence、roomId、lastRoomRevision。
4. 服务端能重放时，发送缺失事件。
5. 事件缓存不足或版本不一致时，发送 `room.snapshot`。
6. 客户端清除未确认的乐观 UI，按快照重建。

### 14.2 战斗断线策略

- 服务端计时继续，怪意图、抽牌、读条不依赖客户端在线（1v1 断线等待期间双方停手，见下）。
- 断线保留席位 **15 秒**，可 resume；满 15 秒按死亡结算（GDD 2.5.2）。不发明掉线无敌。
- 1v1 中一方断线：15 秒内双方不能出牌。超时断开方死亡，在线方按 PVP 胜并恢复己方快照。
- 结算事件即使断线也必须落库；重登 bootstrap 返回 unfinishedSettlement。

## 15. 标准错误码

目标 `error.command_rejected`：

| code | 含义 | 客户端动作 |
| --- | --- | --- |
| AUTH_EXPIRED | 会话失效 | 重新登录 |
| STATE_NOT_ALLOWED | 当前状态不允许 | 关闭错误操作并刷新动作集合 |
| REVISION_CONFLICT | 版本落后 | 请求 snapshot |
| REQUEST_DUPLICATE | requestId 已处理 | 使用服务端原结果，不重复动画 |
| ASSET_LOCKED | 资产在市场/准备/战局中 | 刷新资产 |
| DECK_INVALID | 编组不合法 | 回编组页定位问题 |
| INVENTORY_FULL | 养成包/临时包无法接收 | 打开替换或停止操作 |
| INSUFFICIENT_CURRENCY | 余额不足 | 刷新余额 |
| TARGET_INVALID | 目标已死或不可选 | 刷新战斗快照 |
| CARD_NOT_IN_HAND | 手牌版本过期 | 刷新战斗快照 |
| MATCH_ALREADY_SETTLED | 已结算 | 拉取结算 |
| RATE_LIMITED | 频率过高 | 按 retryAfterMs 重试 |

## 16. 权威边界

| 内容 | 客户端可预览 | 服务端最终裁决 |
| --- | --- | --- |
| UI 排版、动画、音效 | 是 | 否 |
| 连放预览 | 是，必须标为预览 | 是 |
| 移动合法性 | 可提前灰置 | 是 |
| 地图随机和隐藏情报 | 否 | 是 |
| 抽牌顺序、满手轮空 | 只显示进度 | 是 |
| 怪意图时钟 | 可插值显示 | 是 |
| 伤害、治疗、盾、控制、本命 | 可本地快速预演 | 是 |
| PVP 配对、先后手、停战、逃脱骰 | 否 | 是 |
| 三选一、刷新、掉落 | 否 | 是 |
| 包容量、替换、遗物并发 | 可提示 | 是 |
| 商店/市场/强化/货币 | 否 | 是 |
| 撤离和死亡结算 | 否 | 是 |

## 17. 端到端验收场景

### E2E-01 首次玩家完整撤离

首次本地登录 → 选择法 → 默认 20 → 免费包 → 单人匹配（等 30 秒，服务端补 3 名机器人）→ 外层出生 → 打赢 O1 → 选装备 → 发现随机撤离 → 3 秒撤离 → 结算显示装备/金币/魂/碎片 → 回大厅资产一致。小地图始终看不见机器人。

### E2E-01b 同格遭遇补位机器人

单人开房后进到有机器人的格 → 立刻完整 1v1（重置抽 3，机器人中等出牌）→ 小地图仍不显示该单位 → HUD 无「机器人」标记。

### E2E-02 两人 PVE 被入侵

A 打 PVE，B 进格 → A/B 的 PVE 和三堆冻结 → 双方重置抽 3 → B 后手锁 0.8 秒 → 双方离开成功 → 停战缓存 → 恢复各自 PVE 原状态。

### E2E-03 PVP 死亡与遗物

A 击杀 B → B 的五防具+非安全物资形成一份遗物堆，专属武器不掉，付费包消耗 → A 清完自己的怪后检索 → 包满替换物放回该堆 → C 后来仍可捡剩余物。

### E2E-04 满手轮空和弃牌循环

手牌 5 时到点不抽且蓄能清零 → 打出牌进入弃牌 → 等下一次到点才抽 → 库空时弃牌洗回 → 无“牌用完”状态。

### E2E-05 断线恢复

PVE 出牌后断线，服务端继续意图 → 客户端重连并 resume → 若事件缺失则重放，否则 snapshot → UI 的血、盾、手牌、意图、revision 与服务端一致，不重复发奖励。

### E2E-06 结算幂等

撤离完成后客户端未收到响应并重连 → 服务端不重复发金币/物品 → bootstrap 返回同一个 settlementId → 客户端进入结算页。
