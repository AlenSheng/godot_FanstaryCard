# FantasyCard 客户端对接指南

| 项目 | 当前值 |
| --- | --- |
| 服务版本 | `0.2.0-s1-preparation` |
| 协议前缀 | REST `/api/v1`；WebSocket `/ws/v1` |
| 配置版本 | `gdd-0.64-config-1` |
| 更新时间 | 2026-09-05 |
| 当前完整链路 | 登录 → Bootstrap → 大厅资产 → 探索准备 → 匹配/房间 → 战斗/奖励/撤离 → 结算恢复 |

本文只描述当前代码中真实可调用的协议。匹配、Ready、房间、地图、战斗、奖励、遗物和结算已有纵向切片；客户端仍不得把文档中的待验收能力当成生产已上线接口。

## 1. 环境与地址

| 类型 | 本地地址 |
| --- | --- |
| HTTP | `http://127.0.0.1:5080` |
| WebSocket | `ws://127.0.0.1:5080` |
| 服务信息 | `GET /` |
| 存活检查 | `GET /health/live` |
| 数据库就绪 | `GET /health/ready` |

启动：

```powershell
cd server
.\start-server.bat --no-pause
```

客户端和服务器不在同一台电脑时，把 `127.0.0.1` 改成服务器局域网 IP，并放行 TCP 5080。当前 HTTP/WS 明文只用于本地开发，正式环境必须使用 HTTPS/WSS。

`POST /auth/local` 默认关闭，只有 `Development` 环境且 `Identity:EnableLocalAuth=true` 时才能开启。Production 即使误配该开关也返回 404，不能把 Local Auth 当正式登录。

## 2. 客户端启动顺序

1. 读取环境配置、`deviceId`、token、token 过期时间和 `lastSequence`。
2. 请求 `/health/ready`；失败时指数退避，不要每帧请求。
3. 有 token 时先请求 `/api/v1/bootstrap`；只有 401 才清除 token。
4. 无 token 或收到 401 时执行本地登录。
5. 登录成功后请求 Bootstrap，建立大厅 Store 的完整快照。
6. 连接 WebSocket，收到 `session.connected` 后标记实时通道可用。
7. 若本地保存过 `lastSequence`，发送 `session.resume`。
8. 进入大厅。`unfinishedMatch` 非空时必须优先连接 WebSocket 并恢复对应房间；否则若 `unfinishedSettlement` 非空，展示结算并在 UI 成功接收后调用确认接口。

## 3. 通用约定

### 3.1 HTTP 请求头

登录外的业务接口：

```http
Authorization: Bearer {accessToken}
Content-Type: application/json
X-Trace-Id: unity-42-a1b2c3d4
```

`X-Trace-Id` 可省略。若客户端提供，只允许字母、数字、点、下划线和连字符，最长 64；服务端会在响应头返回最终 trace ID。

创建准备、商店/市场写入、防具强化与专属武器强化还必须提供：

```http
Idempotency-Key: prep-018f90dc19a37a3d
```

同一次业务重试复用同一个键；新业务必须生成新键。同键不同请求体返回 409。

### 3.2 REST JSON

- UTF-8、字段 `camelCase`。
- 枚举使用字符串：`Priest`、`Mage`、`Guardian`。
- GUID 使用带连字符格式。
- 时间是 UTC ISO 8601。
- 客户端必须忽略未知字段，不能因服务端增加字段崩溃。
- token、设备身份票据不得写入普通日志。

### 3.3 ProblemDetails

REST 错误使用 `application/problem+json`：

```json
{
  "type": "about:blank",
  "title": "Deck changed",
  "status": 409,
  "detail": "Reload the deck and retry with its latest version.",
  "traceId": "unity-42-a1b2c3d4"
}
```

| 状态 | 客户端动作 |
| --- | --- |
| 400 | 修正输入；开发模式可显示 detail |
| 401 | 清 token，回登录 |
| 404 | 资源不存在或 Production 禁止 Local Auth |
| 409 | 刷新服务端状态后由用户重新确认；不要无限自动重试 |
| 429 | 按响应节奏退避并合并重复操作；不要立即并发重放 |
| 426 | 把 WebSocket 地址误当普通 HTTP 请求 |
| 500 | 记录 traceId，显示服务暂不可用 |

## 4. 服务信息与健康检查

### `GET /`

```json
{
  "service": "FantasyCard.Server",
  "version": "0.2.0-s1-preparation",
  "configVersion": "gdd-0.61-proto-1",
  "milestone": "S0/S1 complete; preparation vertical slice available",
  "capabilities": [
    "identity.local",
    "players.profile",
    "bootstrap",
    "cards.read",
    "decks.read_write",
    "preparations.create_read_cancel",
    "realtime.ping_resume"
  ]
}
```

客户端可在开发诊断页展示 version/configVersion，但不要依据 `milestone` 文本裁决业务。需要能力探测时使用 `capabilities`。

## 5. 本地登录

### `POST /api/v1/auth/local`

```json
{
  "deviceId": "local-development-device-001",
  "displayName": "山海客"
}
```

约束：

- `deviceId` 去首尾空格后 8–128 个可打印字符；首次登录后映射到内部 UserId。
- `displayName` 2–20 个 Unicode 字符，首次创建玩家时使用。
- 同一 `deviceId` 并发首次登录由数据库事务和 advisory lock 串行化。

响应：

```json
{
  "accessToken": "只保存，不记录日志",
  "expiresAt": "2026-09-28T08:00:00+00:00",
  "player": {
    "userId": "018f90dc-19a3-7a3d-989c-6f49a1093e21",
    "displayName": "山海客",
    "selectedClass": null,
    "version": 1,
    "createdAt": "2026-08-29T08:00:00+00:00",
    "updatedAt": "2026-08-29T08:00:00+00:00"
  }
}
```

首次登录会幂等初始化：0 余额钱包、0 材料、30 张通用白卡、每职业 7 张职业白卡、三套默认 20 张编组、三把 +0 专属武器、三双绑定白鞋。起始金币、药剂、付费包未获策划确认，保持为 0。

### `POST /api/v1/auth/steam`

Steam 登录默认关闭。服务端配置 `Identity:Steam:Enabled=true`、AppId、PublisherKey 与票据 identity 后可用：

```json
{
  "ticket": "GetAuthTicketForWebApi 返回票据的十六进制字符串",
  "displayName": "山海客"
}
```

客户端不得提交或决定 SteamID；服务端向 Steamworks 验票后使用返回的 64 位 SteamID 建立外部身份映射。成功响应与本地登录相同；无效票据返回 401，Steam 验票服务不可用返回 503，功能未配置返回 404。PublisherKey 只存在于服务端 Secret Store。

## 6. Bootstrap

### `GET /api/v1/bootstrap`

这是登录后大厅首屏的唯一推荐入口。不要并行拼接多个请求代替它。

精简响应示例：

```json
{
  "serverTime": "2026-08-29T08:00:01+00:00",
  "configVersion": "gdd-0.61-proto-1",
  "player": {
    "userId": "018f90dc-19a3-7a3d-989c-6f49a1093e21",
    "displayName": "山海客",
    "selectedClass": null,
    "version": 1,
    "createdAt": "2026-08-29T08:00:00+00:00",
    "updatedAt": "2026-08-29T08:00:00+00:00"
  },
  "wallet": { "gold": 0, "diamond": 0 },
  "materials": {
    "warriorSoul": 0,
    "priestSoul": 0,
    "mageSoul": 0,
    "guardianSoul": 0,
    "equipmentFragments": 0
  },
  "classWeapons": [
    { "heroClass": "Priest", "level": 0, "version": 1 },
    { "heroClass": "Mage", "level": 0, "version": 1 },
    { "heroClass": "Guardian", "level": 0, "version": 1 }
  ],
  "equippedLoadouts": [
    {
      "heroClass": "Mage",
      "equipmentIds": [null, null, null, null, "018f..."],
      "version": 1
    }
  ],
  "decks": [
    {
      "deckId": "018f...",
      "heroClass": "Mage",
      "cardIds": ["common-01", "...", "mage-07"],
      "version": 1,
      "updatedAt": "2026-08-29T08:00:00+00:00"
    }
  ],
  "inventorySummary": { "capacity": 50, "equipmentCount": 0, "freeSlots": 50 },
  "unfinishedMatch": null,
  "unfinishedSettlement": null
}
```

穿戴数组的固定顺序是：`Head, Chest, Hands, Legs, Feet`。空槽为 `null`，专属武器不在此数组内。

活动战局存在时，`unfinishedMatch` 为：

```json
{
  "matchId": "018f...",
  "roomId": "018f...",
  "status": "Running",
  "roomRevision": 42,
  "configVersion": "gdd-0.61-proto-1"
}
```

`roomRevision` 在首个持久快照前允许为 `null`。客户端随后建立 WebSocket；服务端会主动下发玩家隔离的 `room.snapshot`。

资产 hold 全部提交且玩家尚未确认时，`unfinishedSettlement` 返回最新一条待展示结算：

```json
{
  "settlementId": "018f...",
  "matchId": "018f...",
  "playerId": "018f...",
  "result": "Extracted",
  "details": { "source": "extract" },
  "createdAt": "2026-08-29T08:15:00+00:00"
}
```

客户端完成结算弹窗数据绑定后调用：

```http
POST /api/v1/settlements/{settlementId}/acknowledge
Authorization: Bearer {accessToken}
Idempotency-Key: settlement-ack-018f90dc
```

成功返回 `settlementId` 和首次 `acknowledgedAt`。同一次 UI 操作及其网络重试必须复用 `Idempotency-Key`；同键同结算回放首次响应，同键改为其他结算返回 409。使用新键重复确认仍返回首次确认时间；他人结算返回 404；资产仍处于 Pending 时返回 409。确认只结束待展示状态，不触发或重复提交资产。结算详情也可通过 `GET /api/v1/settlements/{id}` 或 `GET /api/v1/matches/{id}/settlement` 查询。

## 7. 玩家档案

### `GET /api/v1/players/me`

返回 `player` 对象。

### `PUT /api/v1/players/me`

请求头必须带 `Idempotency-Key`；同一次 UI 提交和网络重试复用同一个键。

```json
{
  "displayName": null,
  "selectedClass": "Mage",
  "expectedVersion": 1
}
```

- `displayName` 与 `selectedClass` 至少提供一个。
- 成功后 version +1。
- 同键同请求会返回首次成功响应；同键改请求体返回 409。
- 非幂等冲突的 version 409 时重新获取 Bootstrap 或 `/players/me`，不要换新键后用旧 version 覆盖。

## 8. 图鉴与编组

### `GET /api/v1/cards`

```json
[
  {
    "cardId": "common-01",
    "heroClass": null,
    "rarity": "White",
    "unlocked": true,
    "copyCount": 1,
    "level": 0,
    "version": 1
  }
]
```

当前是起始 ID 占位目录，不是最终 200 卡配置包。客户端卡面展示仍需与后续静态配置版本对齐。

### `GET /api/v1/decks`

返回三职业编组。客户端以 `heroClass` 建索引，不依赖数组顺序。

### `PUT /api/v1/decks/{heroClass}`

路径示例：`/api/v1/decks/Mage`
请求头必须带 `Idempotency-Key`；成功响应丢失后的重试复用原键。

```json
{
  "cardIds": [
    "common-01", "common-02", "common-03", "common-04", "common-05",
    "common-06", "common-07", "common-08", "common-09", "common-10",
    "common-11", "common-12", "common-13",
    "mage-01", "mage-02", "mage-03", "mage-04", "mage-05", "mage-06", "mage-07"
  ],
  "expectedVersion": 1
}
```

服务端校验：

- 恰好 20 张。
- 已拥有且复制数量足够。
- 职业卡只进本职业。
- 怪物卡不能编组。
- 通用橙最多 1，职业橙最多 1。
- expectedVersion 必须等于当前版本。

成功返回新 Deck，version +1；400 是规则不合法，409 是版本冲突。

### `GET /api/v1/inventory`

返回养成背包与当前三职业穿戴涉及的装备详情，以及仓库消耗品：

```json
{
  "summary": { "capacity": 50, "equipmentCount": 1, "freeSlots": 49 },
  "equipments": [
    {
      "instanceId": "装备 UUID",
      "slot": "Head",
      "quality": "Purple",
      "level": 2,
      "isBound": false,
      "location": "Inventory",
      "version": 1,
      "element": "Water",
      "effectAffix": "Vitality",
      "secondaryTrait": "DrawInterval"
    }
  ],
  "consumables": {
    "healthPotionCount": 3,
    "advancedBagCount": 2,
    "topBagCount": 1
  }
}
```

`summary.equipmentCount/freeSlots` 只按 50 格养成背包内 `Inventory` 装备计算；`equipments` 同时返回 `Inventory` 与 `Equipped`，使配装 ID 始终能解析到完整装备属性。市场上架、准备锁定、局内和已消耗装备由各自流程展示，不混入大厅可操作库存。

### `GET /api/v1/loadouts/{heroClass}`

返回指定职业的五防具配装，`equipmentIds` 固定按 `Head, Chest, Hands, Legs, Feet` 排列，空槽为 `null`，专属武器不在数组内。未知职业返回 400，玩家或配装不存在返回 404。

### `PUT /api/v1/loadouts/{heroClass}`

请求头必须带 `Idempotency-Key`。请求包含固定五槽 `equipmentIds` 和 `expectedVersion`；同键同请求回放首次成功响应，同键改请求体返回 409。服务端只迁移实际变化的装备位置并写库存移动审计。

### 市场事务审计

市场上架和成交会写库存移动审计；成交时装备只有仍由卖家持有且处于 `MarketListed` 才能转给买家。买卖双方金币流水与获胜购买请求的 `Idempotency-Key` 关联。同一挂单并发购买只有一个请求成功，其他请求返回 409 且不扣金币。

### 商店与强化事务审计

商店购买必须复用一次 UI 操作的 `Idempotency-Key`；同键同请求回放首次结果，同键改商品或数量返回 409。日限、金币不足，以及高级/顶级探索包购买后仓库合计将超过 3 个时，服务端不会扣金币或发放物品。防具 +4/+5 材料可使用仓库中同品质、任意部位/元素/强化等级的防具；绑定材料允许，红装只接受红装材料，专属武器永远不可作材料。红装强化 UI 随红装掉落/周配额一同开放，当前原型不展示入口。失败不会扣碎片或消费材料，成功重放不会重复消费。

`GET /api/v1/shop/` 每日 UTC+8 04:00 更换 `resetKey`。响应固定包含三条 `productId=daily_card_1..3` 的单卡报价；`payload` 是 JSON 字符串，含 `cardId`、`quality`、`count=1`。三张卡互不重复，仅从图鉴 White～Purple 中产生，不含 Orange；同一 resetKey 在所有服务实例上一致。价格为白 80、绿 150、蓝 280、紫 500，每张每名玩家当日限购 1。

```json
{
  "productId": "daily_card_1",
  "kind": "Cards",
  "priceGold": 150,
  "limit": 1,
  "purchased": 0,
  "payload": "{\"cardId\":\"G17\",\"quality\":\"Green\",\"count\":1}"
}
```

购买调用 `POST /api/v1/shop/purchases`，请求体为 `{"productId":"daily_card_1","quantity":1}`。成功后指定卡解锁并增加一张同名复制；随机卡牌礼包按白/绿/蓝/紫 50/30/15/5 独立抽取三次，不含 Orange 和职业 Purple/Orange。服务端要求每张卡实际写入玩家卡表，否则整笔扣金和发货回滚。

## 9. 探索准备

### 9.1 创建

`POST /api/v1/preparations`

请求头必须带 `Idempotency-Key`。免费包、只穿起始鞋的示例：

```json
{
  "heroClass": "Mage",
  "deckVersion": 1,
  "equipmentIds": [null, null, null, null, "从 bootstrap 取得的白鞋 ID"],
  "backpackTier": "Free",
  "safeSlotIndexes": [],
  "potionCount": 0,
  "difficulty": "Standard"
}
```

规则：

- equipmentIds 固定 5 个位置，可为 null，不能重复。
- 装备必须属于玩家、处于 `Equipped`，并与位置一致。
- Free：容量 20、安全格 0；Advanced：28/1；Top：36/3。
- 安全格索引必须互异且在容量范围内。
- 药剂 0–2，且仓库数量足够。
- 创建时所选装备立即进入 `PreparationLocked`，不能换装、强化或交易；付费包和药剂只登记预留，尚不扣除。
- 正式开房时装备转 `InMatchEquipped` 并原子扣除带入药剂；付费包继续保持逻辑预留。开房事务失败则全部回滚；撤离返还未用药剂并释放付费包，死亡结算才消耗付费包。
- 原型只允许 Standard。
- 同一玩家只能有一个 Active/Queued/Matched preparation。

首次成功返回 201；完全相同的幂等重放返回 200 和同一 preparationId：

```json
{
  "preparationId": "018f...",
  "status": "Active",
  "snapshot": {
    "heroClass": "Mage",
    "maximumHp": 70,
    "cardIds": ["...20 cards..."],
    "equipmentIds": [null, null, null, null, "018f..."],
    "equipmentSnapshots": [
      {
        "instanceId": "018f...",
        "slot": "Feet",
        "quality": "White",
        "level": 0,
        "element": "Fire",
        "effectAffix": null,
        "secondaryTrait": "DrawInterval"
      }
    ],
    "classWeaponLevel": 0,
    "backpackTier": "Free",
    "backpackCapacity": 20,
    "safeSlotIndexes": [],
    "potionCount": 0,
    "difficulty": "Standard",
    "configVersion": "gdd-0.61-proto-1"
  },
  "createdAt": "2026-08-29T08:10:00+00:00",
  "expiresAt": "2026-08-29T08:40:00+00:00"
}
```

`equipmentSnapshots` 是进入匹配时使用的不可变权威装备属性；只包含实际穿戴的非空槽，旧响应可能没有该可选字段。客户端展示可以读取它，但不得提交或覆盖其中的战斗数值。服务端按该快照计算元素增伤/抗性、强化成长、效果套、抽牌间隔和鞋子逃脱加成。

### 9.2 查询当前准备

`GET /api/v1/preparations`

- 有 Active/Queued/Matched：200。
- 没有：404；客户端显示未准备状态，不视为服务器故障。

### 9.3 取消

`DELETE /api/v1/preparations/{preparationId}`

请求头必须带 `Idempotency-Key`；重复取消复用原键。同一个键改为取消其他 preparation 返回 409。

- Active：204，装备从 `PreparationLocked` 恢复 `Equipped`，同时释放其他逻辑预留。
- 不属于玩家/不存在：404。
- 已进入其他状态：409；后续 Queued 必须走 `match.cancel`。

## 10. WebSocket

### 10.1 连接与编码

```text
ws://127.0.0.1:5080/ws/v1/session?access_token={URL 编码 token}
```

- 单条完整消息上限 16 KiB，支持 WebSocket 分片。
- 只接受 Protobuf v1 **Binary** 帧；Text 帧以 `InvalidMessageType` 关闭。
- schema：`protocol/realtime/v1/realtime.proto`。每条消息是一个 `ClientEnvelope` 或 `ServerEnvelope`，`protocol_version=1`。
- `payload` 是该 type 对应的具名 Protobuf message，禁止传 JSON 字符串/字节。
- 同账号新连接接管实时会话，旧连接先收到 `session.replaced` 后关闭。

### 10.2 当前消息

| type | 方向 | payload |
| --- | --- | --- |
| `ping` | C→S | 空 |
| `session.resume` | C→S | `SessionResumeCommand` |
| `session.connected` | S→C | `SessionConnectedEvent` |
| `session.replaced` | S→C | `SessionReplacedEvent` |
| `pong` | S→C | `PongEvent` |
| `session.snapshot` | S→C | `SessionSnapshotEvent` |
| `match.found` | S→C | matchId、roomId、15 秒确认截止时间 |
| `room.ready_required` | S→C | matchId、roomId、截止时间、当前/所需确认人数 |
| `room.ready` | C→S | 空；必须带 request_id |
| `room.ready_accepted` | S→C | Ready 进度；全部真人确认可提前开局 |
| `room.ready_removed` | S→C | 超时未确认，席位已由机器人接替 |
| `room.started` | S→C | matchId、roomId、固定 4 席及当前玩家私有首快照 |
| `settlement.ready` / `match.settled` | S→C | `SettlementReadyEvent`；settlementId、matchId、result；资产托管全部提交后由持久 outbox 兼容发布两种名称，离线行在重连时投递，客户端按 settlementId/eventId 去重 |
| `room.snapshot.read` | C→S | `RoomSnapshotCommand` |
| `room.snapshot` | S→C | `RoomSnapshotEvent`；仅含当前玩家可见房间状态 |
| `error.command_rejected` | S→C | `CommandRejectedEvent` |
| `error.invalid_message` | S→C | 空 |
| `error.rate_limited` | S→C | 空 |
| `room.move` / `map.move` | C→S | `RoomMoveCommand`；前者为现有客户端名，后者为服务器规范兼容名 |
| `battle.play_cards` | C→S | `BattlePlayCardsCommand` |
| `battle.select_target` | C→S | `BattleSelectTargetCommand`；仅活动 PVE，可选择当前战斗内未死亡目标 |
| `battle.target_selected` | S→C | `BattleTargetSelectedEvent`；返回 battleId、targetId 和新 roomRevision |
| `action.extract` | C→S | `ActionExtractCommand` |
| `action.extract_started` | S→C | `ActionExtractEvent` |
| `action.spring` / `action.use_spring` | C→S | `ActionSpringCommand` |
| `action.spring_started` | S→C | `ActionSpringEvent`，固定返回 1.2 秒权威读条 |
| `action.potion` | C→S | `ActionPotionCommand`；仅在 `allowed_actions` 包含该值时发送，点击即结算、无读条 |
| `action.potion_used` | S→C | `ActionPotionEvent`；返回被消耗的 itemId 与实际恢复量 healed |
| `relic.take` | C→S | `RelicTakeCommand`；旧客户端仍可通过可选 replaceItemId 做满包替换 |
| `relic.replace` | C→S | `RelicReplaceCommand`；显式指定当前堆、目标物和退回当前堆的背包物品 |
| `relic.taken` / `relic.replaced` | S→C | 返回 pileId、取得物、最新 pileVersion；替换事件另含 returnedItemId |
| `duel.ended` | S→C | `DuelEndedEvent`；reason、可选 winnerId，snapshotRequired=true 时读取/等待最新 `room.snapshot` |
| `duel.escape_interrupted` / `duel.escape_failed` | S→C | `DuelEscapeEvent`；实际扣到生命时中断，掷骰失败时进入 12 秒冷却 |
| `player.died` | S→C | `PlayerDiedEvent`；cause 为 PveDeath/PvpDeath，随后等待结算事件 |
| `action.extract_cancelled/completed` | S→C | `ActionExtractEvent`；合法 PVP 打断或 3 秒读条完成 |
| `action.spring_cancelled/completed` | S→C | `ActionSpringEvent`；合法 PVP 打断或 1.2 秒读条完成 |

所有改变状态的命令必须带 `request_id`；超时重试复用同一值。`room_revision` 仅房间事件使用。时间字段为 Unix 毫秒。

客户端必须按 `sequence` 去重并持久化最后成功值；跳号时用 `SessionResumeCommand.last_sequence/room_id/room_revision` 请求恢复；未知字段忽略，未知 type 记录开发日志后忽略。缓存有缺口时服务端返回 `session.snapshot`，若玩家仍在房间会紧接玩家隔离的 `room.snapshot`；房间 revision 落后时也会补发。建立 WebSocket 连接时，若玩家处于确认阶段，服务端在 `session.connected` 后发送最新 `room.ready_required`；若已有活动房间，则主动发送 `room.snapshot`。

`room.snapshot` 的全图只包含 6×6 形状、Boss 和泉水；不会下发其他玩家位置、人数、交战、已清格、随机撤离、宝箱怪或非当前格遗物。当前格上下文、自己的战斗/三堆摘要、临时包、PVE/PVP、奖励、读条与 `allowed_actions` 会一并返回。

未知或未开放命令返回 `error.command_rejected`。当前 code：`INVALID_COMMAND`、`INVALID_REQUEST_ID`、`REQUEST_ID_REQUIRED`、`INVALID_PAYLOAD`、`UNSUPPORTED_COMMAND`、`COMMAND_REJECTED`、`READY_NOT_FOUND`、`READY_TIMEOUT`。单连接命令超过服务端窗口时返回 `error.rate_limited`；客户端应停止当帧发送、合并可覆盖命令并指数退避。
## 11. Unity 客户端落地建议

### Store 分层

- `SessionStore`：token、expiresAt、lastSequence、连接状态。
- `PlayerStore`：player、wallet、materials、cards、decks、weapons、loadouts。
- `PreparationStore`：草稿、创建中、Active snapshot、取消中、错误。
- 后续 `RoomStore` 与大厅 Store 分离，不能让本地战斗原型直接写永久资产。

### 请求规则

- 所有 HTTP 从统一 Gateway 注入 Authorization、X-Trace-Id、超时和 ProblemDetails 解析。
- PUT 使用 Store 当前 version，并为一次 UI 提交生成固定 `Idempotency-Key`；网络重试复用，409 后刷新且不自动覆盖玩家新状态。
- POST preparation 在 UI 一次提交期间固定 Idempotency-Key；网络重试复用。
- DELETE preparation、match ticket、market listing 同样为一次用户操作固定 `Idempotency-Key`；同键不得改目标 ID。
- 服务端成功响应到达前，不乐观增加资产或改变权威 preparation 状态。

### DTO 兼容

- 网络 DTO 独立于 `Game.Domain`，不要直接序列化 MonoBehaviour 或 Unity 类型。
- `Guid`、`DateTimeOffset`、nullable enum 在 IL2CPP/Wasm 构建前做 AOT 冒烟。
- REST 响应字段允许增加，JSON 反序列化器忽略未知字段；WebSocket Protobuf 同样忽略未知字段。

## 12. 当前联调验收清单

- [ ] 首次登录只生成一个内部玩家，重复登录资产不重复。
- [ ] Bootstrap 得到三职业武器、编组和白鞋；初始余额为 0。
- [ ] 档案更新 version +1；同幂等键重试回放成功响应，旧 version 的新请求返回 409。
- [ ] 图鉴返回 51 张起始卡，三套编组各 20 张。
- [ ] 非 20 张、跨职业卡、超持有数量的编组返回 400。
- [ ] 合法编组/穿戴保存 version +1；同幂等键重试回放成功响应，旧版本的新请求返回 409。
- [ ] 免费包准备成功；重复同幂等键返回同 preparationId。
- [ ] 同幂等键改请求体返回 409。
- [ ] Active 准备可查询、可取消；取消后 GET 返回 404。
- [ ] WebSocket 收到 session.connected，ping 得到 pong。
- [ ] 断线后 resume 可重放缺失 sequence；重复事件不重复应用。
- [ ] 匹配成功收到 `match.found` 与 `room.ready_required`；全员 Ready 可提前收到 `room.started`。
- [ ] 15 秒超时后未 Ready 真人收到 `room.ready_removed`，保留真人进入固定 4 席房间且首快照只含本人可见信息。

2026-09-09 已使用真实 Docker/PostgreSQL 环境执行完整回归：领域测试 129/129、服务测试 120/120，合计 249 项通过、0 跳过；其中 PostgreSQL 集成测试 21/21，覆盖装备/掉落统一配置、迁移、旧库升级、并发初始化、大厅资产事务、统一 REST `Idempotency-Key` 校验、红装同品质强化材料、准备/开房资产托管、遗物装备再撤离、结算九个 hold 幂等提交、失败整批回滚与死亡装备/付费包处理、Pending hold 冷启动恢复及结算确认持久回放、四真人立即开房和 30 秒成组/15 秒 Ready 超时剔除/机器人补位的 Hall→Room 纵向链路、Running 房间停机 tick 恢复，以及 RoomActor 撤离/死亡后自动结算资产并清理终局 Registry。
