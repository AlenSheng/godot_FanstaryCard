# FantasyCard 客户端对接指南

| 项目 | 当前值 |
| --- | --- |
| 服务版本 | `0.3.0-room-combat`（运行时以 `GET /` 为准） |
| 协议前缀 | REST `/api/v1`；WebSocket `/ws/v1` |
| 配置版本 | `gdd-0.67-gameplay-completion-1` |
| 更新时间 | 2026-09-10 |
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

`POST /api/v1/auth/local` 默认关闭，只有 `Development` 环境且 `Identity:EnableLocalAuth=true` 时才能开启。Production 即使误配该开关也返回 404，不能把 Local Auth 当正式登录。

配置源为仓库根目录 `config/FantasyCard_Config.xlsx`。`tools/export-config.ps1` 将同一份 bytes/version/hash 发布到 `server/config/generated/` 与 `client/data/generated/`，并生成 Godot 使用的 `client/data/catalog.json`。当前版本包含 220 张图鉴卡、12 张怪物卡和 1320 行成长数据；湮核 `M-VOIDCORE` 为火 8、金 8、盾 8，`GO10.is_class_reveal=true`。服务端和客户端版本不一致时先更新配置，不用客户端猜测数值。

## 2. 客户端启动顺序

1. 读取环境配置、`deviceId`、token、token 过期时间和 `lastSequence`。
2. 请求 `/health/ready`；失败时指数退避，不要每帧请求。
3. 有 token 时先请求 `/api/v1/bootstrap`；只有 401 才清除 token。
4. 无 token 或收到 401 时执行环境对应的登录：开发环境可本地登录，发行客户端走 Steam 票据登录。
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
X-Trace-Id: godot-42-a1b2c3d4
```

`X-Trace-Id` 可省略。若客户端提供，只允许字母、数字、点、下划线和连字符，最长 64；服务端会在响应头返回最终 trace ID。

卡牌合成/分解/升级、创建准备、商店/市场写入、防具强化与专属武器强化还必须提供：

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
  "traceId": "godot-42-a1b2c3d4"
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
  "version": "0.3.0-room-combat",
  "configVersion": "gdd-0.67-gameplay-completion-1",
  "milestone": "S0/S1 complete; S2-S9 vertical slices available; room recovery, player snapshots, bot runtime, rate limits, and economy reconciliation",
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

上例省略其余 capabilities。客户端可在开发诊断页展示 version/configVersion，但不要依据 `milestone` 文本裁决业务。`capabilities` 是已有的粗粒度提示，目前未逐一登记本轮所有新增命令；具体字段和调用方式以本文及 Protobuf schema 为准。

## 5. 本地登录

### `POST /api/v1/auth/local`

```json
{
  "deviceId": "local-development-device-001",
  "displayName": "山海客",
  "configVersion": "gdd-0.68-element-tuning-1",
  "includeBootstrap": true
}
```

约束：

- `deviceId` 保留为兼容字段，去首尾空格后 8–128 个可打印字符，不再决定账号。
- `displayName` 是本地账号名，2–20 个 Unicode 字符；去首尾空格、NFKC 规范化后，按数据库小写规则全局唯一（例如 `Alice`、`alice` 和 `Ａｌｉｃｅ` 对应同名）。
- 同名登录返回原 UID 和资产；输入未注册的新名称创建新 UID，即使 deviceId 相同。跨设备同名也登录同一本地账号。
- 同名并发首次登录由数据库事务、advisory lock 和唯一索引保证只注册一次。已被 Steam 等非本地账号占用的名称返回 409，不会将该账号作为本地账号登录。
- V019 为原有本地账号补充名称绑定，保留原 UID、资产、会话。历史重名必须先人工处理，迁移不会自动合并或删除账号。
- 本地账号名与 UID 固定绑定；`PUT /players/me` 可选职业，可调整同名的大小写展示，不能将本地账号改为另一个名称，改名请求返回 409。创建另一个账号应回登录页输入新名称。
- 切换登录前清除 token、界面缓存和旧请求；UID 改变后清除房间重放游标，再从 Bootstrap 获取新账号状态。

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

客户端可在登录请求中带 `configVersion`。不匹配时服务端返回 409，避免创建不兼容的登录会话。设置 `includeBootstrap: true` 后，成功响应还包含 `bootstrap`（与 `GET /api/v1/bootstrap` 相同的完整账号快照）和 `clientInfo`（配置版本、能力与公告）。新客户端直接使用这两个字段进入大厅；旧客户端仍可继续单独请求 Bootstrap。

首次登录会幂等初始化：0 余额钱包、0 材料、30 张通用白卡、每职业 7 张职业白卡、三套默认 20 张编组、三把 +0 专属武器、三职业五部位配装全空。**不发放绑定白鞋或任何起始防具。** 起始金币、药剂、付费包未获策划确认，保持为 0。

### `POST /api/v1/auth/steam`

Steam 登录默认关闭。服务端配置 `Identity:Steam:Enabled=true`、AppId、PublisherKey 与票据 identity 后可用：

```json
{
  "ticket": "GetAuthTicketForWebApi 返回票据的十六进制字符串",
  "displayName": "山海客"
}
```

客户端不得提交或决定 SteamID；服务端向 Steamworks 验票后使用返回的 64 位 SteamID 建立外部身份映射。成功响应与本地登录相同；无效票据返回 401，玩家名等输入非法返回 400，Steam 验票服务不可用返回 503，功能关闭返回 404。启用却缺 AppId/PublisherKey/Identity 时配置校验拒绝服务启动。PublisherKey 只存在于服务端 Secret Store。

### `POST /api/v1/auth/google`

Android 客户端可提交 Google Sign-In 返回的 `idToken` 和展示名。服务端验证签名、受众、发行者和邮箱验证状态后，使用稳定的 Google subject 关联内部账号；客户端不能自行提交 Google 用户 ID。请求也支持 `configVersion` 和 `includeBootstrap`，行为与本地、Steam 登录一致。

Godot 的 `client/platform/platform_service.gd` 已封装 GodotSteam 单例初始化、Web API 票据回调、15 秒超时、十六进制转换及取消票据。发行环境需要安装兼容的原生组件，并配置 `platform/steam/app_id` 与 `platform/steam/web_api_identity`，后者必须和服务器票据 Identity 对应。当前项目默认 AppID 为 0、identity 为空，未完成真实 Steamworks 凭据及发行环境登录验收；本地登录和模拟验票测试不代表 Steam 生产登录通过。发行构建不开放开发本地登录入口。

## 6. Bootstrap

### `GET /api/v1/bootstrap`

登录响应已内嵌相同的完整快照，可直接用于大厅首屏；`GET /api/v1/bootstrap` 用于断线恢复、主动刷新和兼容旧客户端。不要并行拼接多个模块请求代替它。

精简响应示例：

```json
{
  "serverTime": "2026-08-29T08:00:01+00:00",
  "configVersion": "gdd-0.67-gameplay-completion-1",
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
      "equipmentIds": [null, null, null, null, null],
      "version": 1
    }
  ],
  "decks": [
    {
      "deckId": "018f...",
      "heroClass": "Mage",
      "cardIds": ["C01", "...", "MAG-07"],
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
  "configVersion": "gdd-0.67-gameplay-completion-1"
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

死亡结算提交后身上五件防具进遗物堆，对应配装栏保持空。开局与死亡都 **不发放绑定白鞋**。专属武器始终保留，不进遗物堆。

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
    "cardId": "C01",
    "heroClass": null,
    "rarity": "White",
    "unlocked": true,
    "copyCount": 1,
    "level": 0,
    "version": 1,
    "craftCost": 10,
    "upgradeSoulSpent": 0,
    "dismantleRefund": 2,
    "currencyKind": "WarriorSoul",
    "canDismantle": false,
    "blockedReason": "Card is required by a saved deck.",
    "upgradeCost": 5,
    "upgradeCopyCost": 0,
    "canUpgrade": true,
    "upgradeBlockedReason": null
  }
]
```

返回当前配置包中全部 220 张图鉴卡（不含 12 张战局怪物卡），含尚未拥有的条目。未拥有条目 `unlocked=false`、`copyCount=0`；正常初始化行的 `version=1`，缺失的历史行则为 0。卡面使用相同 `configVersion` 的静态配置，交易价格与材料类型使用这里的服务端报价。

`currencyKind` 为 `WarriorSoul`、`PriestSoul`、`MageSoul`、`GuardianSoul`，三职业材料互不通用。`canDismantle=false` 时 `blockedReason` 给出未拥有或已编组原因。品质字符串为 `White/Green/Blue/Purple/Orange`。

上例省略 `currentEffect` 与 `nextEffect`：它们分别返回当前等级和下一等级的完整效果；+5 时 `nextEffect=null`。效果字段包括元素/直接伤害、治疗、护盾、抽牌、加速/控制持续时间、生命代价、组合系数、`isClassReveal`，以及 `secondaryElementalDamage`/`secondaryElement`。`canUpgrade` 只判断拥有、等级上限和同名副本保护；客户端还须结合 `materials` 与 `upgradeCost` 判断余额，最终扣款由服务端事务裁决。

### `POST /api/v1/cards/{cardId}/craft` / `POST /api/v1/cards/{cardId}/dismantle`

必须携带 Bearer 身份与 `Idempotency-Key`，请求体 `{"expectedVersion":1}`，版本使用最近读取的条目。合成获得一张 +0 卡牌（已有时增加复制），扣除该牌对应魂；开局赠送卡重新合成按复制价收取，不可免费反复分解。

分解每次移除一张，返还 `floor((卡牌魂价 + 累计升级魂消耗) / 4)` 到同一种魂。现有库存按卡号聚合一张已养成卡与其 +0 复制，优先分解多余的 +0 复制，其 `upgradeSoulSpent=0`；最后一张才返还该牌累计升级魂，耗尽后等级归零。任一已保存职业编组所需的份数必须保留；多个编组可共用同一收藏，不累加三套的份数。

成功响应 HTTP 200：

```json
{
  "card": { "cardId": "C01", "unlocked": true, "copyCount": 1, "level": 0, "version": 2 },
  "materials": { "warriorSoul": 90, "priestSoul": 0, "mageSoul": 0, "guardianSoul": 0, "equipmentFragments": 0 },
  "currencyKind": "WarriorSoul",
  "soulAmount": 10
}
```

`card` 实际包含完整上述报价字段；`soulAmount` 是本次扣除或返还的正整数。相同键和请求体返回首次完整响应，不重复扣款或返还；同键不同体、余额不足、未拥有分解、编组保护、未知卡牌或版本过期返回 409 ProblemDetails。操作后刷新卡牌与 bootstrap，材料余额不可由客户端自行累加。

### `POST /api/v1/cards/{cardId}/upgrade`

请求体仍为 `{"expectedVersion":1}`，必须带 Bearer 和 `Idempotency-Key`。成功返回完整 `CardMutationResponse`：`card`、`materials`、`currencyKind`、正数 `soulAmount`，以及实际消耗的同名副本数 `consumedCopies`。每次只升一级，最大 +5；+4/+5 除对应魂外各消耗一张多余同名卡，且必须保留养成卡和所有已保存编组所需的最大份数。怪物卡不能升级。缺键/请求格式非法为 400，余额、版本或规则冲突为 409；同键同请求回放首次响应。

库存模型是一张养成卡加若干 +0 副本，同名卡重复编入时只有第一个编组槽携带养成等级，其余为 +0。升级仅增长已有伤害/回复/护盾和配置指定的持续时间，不改变品质、元素、抽牌张数、生命代价或复合结构。展示优先读取 `currentEffect`/`nextEffect`，不要给所有同名副本复制养成收益。

### `GET /api/v1/decks`

返回三职业编组。客户端以 `heroClass` 建索引，不依赖数组顺序。

### `PUT /api/v1/decks/{heroClass}`

路径示例：`/api/v1/decks/Mage`
请求头必须带 `Idempotency-Key`；成功响应丢失后的重试复用原键。

```json
{
  "cardIds": [
    "C01", "C02", "C03", "C04", "C05",
    "C06", "C07", "C08", "C09", "C10",
    "C11", "C12", "C13",
    "MAG-01", "MAG-02", "MAG-03", "MAG-04", "MAG-05", "MAG-06", "MAG-07"
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

`GET /api/v1/market/` 返回挂单数组，每项包含 `listingId`、`sellerId`、`equipmentId`、`priceGold`、`status`、`version`、`createdAt`、`expiresAt` 和可选 `equipment`。列表中的 `equipment` 由真实装备记录投影，结构与大厅 `EquipmentResponse` 一致，包含部位、品质、等级、绑定状态、位置、版本、元素和两类词缀；不能只按挂单 UUID 猜测卡面。上架/购买的旧幂等响应允许 `equipment=null`，保持首次响应不随装备变化；需要详情时重新读取市场列表或库存。

市场上架和成交会写库存移动审计；成交时装备只有仍由卖家持有且处于 `MarketListed` 才能转给买家。买卖双方金币流水与获胜购买请求的 `Idempotency-Key` 关联。同一挂单并发购买只有一个请求成功，其他请求返回 409 且不扣金币。

### 强化前报价

读取 `GET /api/v1/equipment/{equipmentId}/enhancement-quote` 或 `GET /api/v1/class-weapons/{heroClass}/enhancement-quote`。需要 Bearer，无需 `Idempotency-Key`。报价示例：

```json
{
  "targetKind": "Equipment",
  "currentLevel": 3,
  "nextLevel": 4,
  "expectedVersion": 1,
  "fragmentCost": 256,
  "materialCount": 1,
  "materialQuality": "Purple",
  "availableFragments": 256,
  "availableMaterialCount": 1,
  "canEnhance": true,
  "blockedReason": null
}
```

`targetKind` 为 `Equipment` 或 `ClassWeapon`。满 +5 时 `nextLevel=null`、`fragmentCost=0`、`canEnhance=false`；报价同时校验余额、材料数量及装备位置。防具只允许 `Inventory/Equipped`，+4/+5 才需一件同品质仓库材料，目标装备自身不计入材料数量。专武费用按 +1 至 +5 为 8/16/32/64/128 碎片，`materialCount=0`、`materialQuality=null`。

提交 `POST /api/v1/equipment/{equipmentId}/enhance`，请求 `{"expectedVersion":1,"materialEquipmentId":"材料 UUID"}`；不需要材料时省略 `materialEquipmentId`，低级防具附带多余材料会被拒绝。专武提交 `POST /api/v1/class-weapons/{heroClass}/enhance`，仅传 `expectedVersion`。写入必须带 `Idempotency-Key`，报价不是预留，服务端会在事务内重新核验；成功返回 `equipment`、剩余 `equipmentFragments` 和可空 `consumedMaterialEquipmentId`。

### 商店与强化事务审计

商店购买必须复用一次 UI 操作的 `Idempotency-Key`；同键同请求回放首次结果，同键改商品或数量返回 409。日限、金币不足，以及高级/顶级探索包购买后仓库合计将超过 3 个时，服务端不会扣金币或发放物品。防具 +4/+5 材料可使用仓库中同品质、任意部位/元素/强化等级的防具；绑定材料允许，红装只接受红装材料，专属武器永远不可作材料。红装强化 UI 随红装掉落/周配额一同开放，当前原型不展示入口。失败不会扣碎片或消费材料，成功重放不会重复消费。

`GET /api/v1/shop/` 每日 UTC+8 04:00 更换 `resetKey`。货架按 GDD 6.2 固定包含：

| productId | kind | 价格 | 日限 | 发放 |
| --- | --- | --- | --- | --- |
| `card_pack` | Cards | 250 | 5 | 3 张白～紫随机卡，权重 50/30/15/5，不含橙和职业紫/橙 |
| `daily_card_1..3` | Cards | 白 80 / 绿 150 / 蓝 280 / 紫 500 | 各 1 | 当日轮换指定图鉴卡 1 张 |
| `warrior_soul` | WarriorSoul | 180 | 3 | 20 勇士之魂 |
| `equipment_fragments` | EquipmentFragments | 120 | 3 | 20 装备碎片 |
| `priest_soul` / `mage_soul` / `guardian_soul` | ClassSoul | 400 | 各 1 | 12 该职业之魂 |
| `health_potion` | HealthPotion | 100 | 4 | 1 瓶生命药剂 |
| `advanced_bag` | AdvancedBag | 800 | 99 | 1 个高级探索包；仓库高级+顶级合计不得超过 3 |
| `top_bag` | TopBag | 2200 | 99 | 1 个顶级探索包；同上合计上限 |

`daily_card_*` 的 `payload` 是 JSON 字符串，含 `cardId`、`quality`、`count=1`。三张卡互不重复，仅从图鉴 White～Purple 中产生，不含 Orange；同一 resetKey 在所有服务实例上一致。

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

请求头必须带 `Idempotency-Key`。免费包、五部位全空的示例：

```json
{
  "heroClass": "Mage",
  "deckVersion": 1,
  "equipmentIds": [null, null, null, null, null],
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
    "cardLevels": [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
    "equipmentIds": [null, null, null, null, null],
    "equipmentSnapshots": [],
    "classWeaponLevel": 0,
    "backpackTier": "Free",
    "backpackCapacity": 20,
    "safeSlotIndexes": [],
    "potionCount": 0,
    "difficulty": "Standard",
    "configVersion": "gdd-0.67-gameplay-completion-1"
  },
  "createdAt": "2026-08-29T08:10:00+00:00",
  "expiresAt": "2026-08-29T08:40:00+00:00"
}
```

`equipmentSnapshots` 是进入匹配时使用的不可变权威装备属性；只包含实际穿戴的非空槽，旧响应可能没有该可选字段。客户端展示可以读取它，但不得提交或覆盖其中的战斗数值。服务端按该快照计算元素增伤/抗性、强化成长、效果套、抽牌间隔和鞋子逃脱加成。

`cardLevels` 是与 `cardIds` 等长、按槽对应的冻结等级数组；创建准备时校验持有份数并固定养成等级，后续大厅升级不改变已有准备。等级随卡牌实例洗牌、弃牌循环、PVP 冻结还原及房间快照恢复保留。旧快照缺少等级时按 +0 兼容。

### 9.2 查询当前准备

`GET /api/v1/preparations`

- 有 Active/Queued/Matched：200。
- 没有：404；客户端显示未准备状态，不视为服务器故障。

### 9.3 取消

`DELETE /api/v1/preparations/{preparationId}`

请求头必须带 `Idempotency-Key`；重复取消复用原键。同一个键改为取消其他 preparation 返回 409。

- Active：204，装备从 `PreparationLocked` 恢复 `Equipped`，同时释放其他逻辑预留。
- 不属于玩家/不存在：404。
- 已进入其他状态：409；后续 Queued 必须走 `DELETE /api/v1/matches/tickets/{ticketId}`。

### 9.4 匹配入队

`POST /api/v1/matches/enqueue` 必须带 Bearer 与 `Idempotency-Key`：

```json
{ "preparationId": "018f..." }
```

- 只接受当前玩家的 Active preparation。
- 首次成功返回 202 与 ticket：`ticketId`、`preparationId`、`status`、`queuedAt`、可选 `matchId`。
- 同键同准备回放原 ticket；同键改 preparationId 返回 409。
- 重复入队（不同键）仍返回原 ticket，不生成第二张。
- 满 4 名真人立刻开房；未满则从队内第一人入队起等 30 秒，用补位机器人补到 4。

`GET /api/v1/matches/tickets/{ticketId}` 查询本人 ticket；不存在返回 404。

`DELETE /api/v1/matches/tickets/{ticketId}` 必须带 `Idempotency-Key`。Queued 取消后 preparation 回到 Active，锁定装备恢复 `Equipped`。同键改 ticket 返回 409。已开房返回 409，不能用取消准备接口代替。

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
| `combat.preview` | C→S | 同一个 `BattlePlayCardsCommand`；带 request_id 与 expected_revision |
| `combat.previewed` / `battle.combo_resolved` | S→C | `BattleComboResolvedEvent`；分别为权威预览与实际出牌结果 |
| `combat.hit` | S→C | `BattleComboResolvedEvent`；怪物、机器人或 PVP 对手造成的权威受击反馈 |
| `battle.select_target` | C→S | `BattleSelectTargetCommand`；仅活动 PVE，可选择当前战斗内未死亡目标 |
| `battle.target_selected` | S→C | `BattleTargetSelectedEvent`；返回 battleId、targetId 和新 roomRevision |
| `action.extract` | C→S | `ActionExtractCommand` |
| `action.extract_started` | S→C | `ActionExtractEvent` |
| `action.spring` / `action.use_spring` | C→S | `ActionSpringCommand` |
| `action.spring_started` | S→C | `ActionSpringEvent`，固定返回 1.2 秒权威读条 |
| `action.potion` | C→S | `ActionPotionCommand`；仅在 `allowed_actions` 包含该值时发送，点击即结算、无读条 |
| `action.potion_used` | S→C | `ActionPotionEvent`；返回被消耗的 itemId 与实际恢复量 healed |
| `inventory.move` | C→S | `InventoryMoveCommand`；item_id、target_slot_index |
| `inventory.equip` | C→S | `InventoryEquipCommand`；item_id |
| `inventory.unequip` | C→S | `InventoryUnequipCommand`；slot，固定五防具部位之一 |
| `inventory.changed` | S→C | `InventoryChangedEvent`；action、item_id，随后返回最新 room.snapshot |
| `relic.read` | C→S | `RelicReadCommand`；pile_id，只读，无需 expected_revision |
| `relic.contents` | S→C | `RoomRelicPile`；pile_id、owner_name、version 和完整 items |
| `relic.take` | C→S | `RelicTakeCommand`；旧客户端仍可通过可选 replaceItemId 做满包替换 |
| `relic.replace` | C→S | `RelicReplaceCommand`；显式指定当前堆、目标物和退回当前堆的背包物品 |
| `relic.taken` / `relic.replaced` | S→C | 返回 pileId、取得物、最新 pileVersion；替换事件另含 returnedItemId |
| `duel.started` | S→C | `DuelStartedEvent`；duel_id、双方 ID、后入场解锁与离开窗口截止时间 |
| `duel.leave` / `duel.escape` | C→S | `DuelLeaveCommand` / `DuelEscapeCommand`，都只传 duel_id |
| `duel.leave_ack` / `duel.escape_started` | S→C | 离开完成状态或当前逃脱概率/状态 |
| `duel.ended` | S→C | `DuelEndedEvent`；reason、可选 winnerId，snapshotRequired=true 时读取/等待最新 `room.snapshot` |
| `duel.escape_interrupted` / `duel.escape_failed` | S→C | `DuelEscapeEvent`；实际扣到生命时中断，掷骰失败时进入 12 秒冷却 |
| `player.died` | S→C | `PlayerDiedEvent`；cause 为 PveDeath/PvpDeath，随后等待结算事件 |
| `action.extract_cancelled/completed` | S→C | `ActionExtractEvent`；合法 PVP 打断或 3 秒读条完成 |
| `action.spring_cancelled/completed` | S→C | `ActionSpringEvent`；合法 PVP 打断或 1.2 秒读条完成 |

所有改变房间状态的命令必须带 `request_id` 与最近快照的 `expected_revision`；超时重试复用相同键和相同请求内容。`combat.preview` 虽然不修改状态，当前协议也要求这两个字段。`room_revision` 仅房间事件使用。绝对时间字段为 Unix 毫秒，持续时间按字段后缀使用毫秒或十进制秒字符串。

客户端必须按 `sequence` 去重并持久化最后成功值；跳号时用 `SessionResumeCommand.last_sequence/room_id/room_revision` 请求恢复；未知字段忽略，未知 type 记录开发日志后忽略。缓存有缺口时服务端返回 `session.snapshot`，若玩家仍在房间会紧接玩家隔离的 `room.snapshot`；房间 revision 落后时也会补发。建立 WebSocket 连接时，若玩家处于确认阶段，服务端在 `session.connected` 后发送最新 `room.ready_required`；若已有活动房间，则主动发送 `room.snapshot`。

`room.snapshot` 的全图只包含 6×6 形状、Boss 和泉水；不会下发其他玩家位置、人数、交战、已清格、随机撤离、宝箱怪或非当前格遗物。当前格上下文、自己的战斗/三堆摘要、临时包、PVE/PVP、奖励、读条与 `allowed_actions` 会一并返回。

未知或未开放命令返回 `error.command_rejected`。常见 code：`INVALID_COMMAND`、`INVALID_REQUEST_ID`、`REQUEST_ID_REQUIRED`、`REQUEST_ID_REUSED`、`EXPECTED_REVISION_REQUIRED`、`INVALID_PAYLOAD`、`UNSUPPORTED_COMMAND`、`COMMAND_REJECTED`、`STALE_RELIC`、`NOT_IN_ROOM`、`READY_NOT_FOUND`、`READY_TIMEOUT`。单连接命令超过服务端窗口时返回 `error.rate_limited`；客户端应停止当帧发送、合并可覆盖命令并指数退避。版本冲突后读新快照，再为新操作生成新 request_id；同键改内容不会成为新请求。

### 10.3 局内背包、换装与遗物

`RoomPlayer` 新增 `inventory_capacity`、`safe_slot_indexes`、`equipped_items`、`weapon_level` 和 `battle_status`。`RoomInventoryItem` 的 `slot_index` 是零基背包格位，旧消息缺失时按未分配处理；`is_safe` 与房间安全格映射由服务端决定。其可选 `equipment` 包含 `slot/quality/element/effect_affix/secondary_trait/level/is_bound`。大厅 REST 的 `EquipmentResponse` 与这个局内 Protobuf 类型不同，不能互换字段大小写或直接混用对象。

只在 `allowed_actions` 允许时发送背包命令。玩家必须已清战斗并处于可用行动栏；PVP、奖励选择、泉水/撤离读条、死亡或断线时不可整理/换装。`inventory.move` 对应显式格位移动；`inventory.equip` 从临时包穿上防具，原部位装备回到该物品原格；`inventory.unequip` 将指定部位放回空格，满包失败。实际属性重算、换装前后物品和最终结算均由服务器处理，成功后按新快照更新。

`current_cell.relic_piles` 只给当前格可操作遗物的堆 ID、主人名和版本，摘要中的 `items` 故意为空。打开堆时先发 `relic.read`，用 `relic.contents.version` 和目标 item_id 发 `relic.take`；满包交换使用 `relic.replace`，并明确指定 `replace_item_id`。被换出的物品回到同一个遗物堆。读取和拾取都校验当前格与行动阶段，旧 pile_version 会被拒绝，空堆被移除后应关闭面板。涉及装备归属和死亡结算托管时，以后续权威状态为准，不可在客户端直接创建永久装备。

### 10.4 连放预览、分类伤害与速度效果

选中 1–5 个不同手牌实例后，使用 `combat.preview`，payload 为当前 `battle_id`、`target_id`、`card_instance_ids`。PVE 目标为活动怪物 ID；PVP 目标为当前对手玩家 UUID。预览采用当前等级、装备、被动、目标抗性和控制递减计算，克隆房间后结算，不消耗牌、生命、随机状态、原房间 revision，也不产生真实受击事件。改变手牌、目标或收到新快照后重新请求；旧 revision 的预览不能继续作为实际出牌结果。

`combat.previewed` 与 `battle.combo_resolved` 共用 `BattleComboResolvedEvent`，保留 `damage/shield_damage/hp_damage/heal/shield_gain/target_defeated/battle_ended`，并追加：

- `damage_segments`：每段 `kind/amount`；kind 为 `Fire/Wood/Earth/Metal/Water/Direct`。按类型着色分行显示，不只保留白色总伤；护盾与生命实际分摊读取各自字段。
- `core_element/core_count`、`stun_seconds/draw_block_seconds`、`health_cost/draw_charge/immediate_draw`：此次连放的核、控制、生命消耗与抽牌结果。比例与秒数字段使用文化无关的十进制字符串。
- `card_instance_ids/source_id`：实际出牌响应携带选中实例；`combat.hit` 可携带怪物或攻击来源 ID。受击通知只发给受击真人，缺少可选效果字段时按零/未知处理。
- `draw_speed_seconds/draw_speed_modifier/draw_block_speed_seconds`：Protobuf 字段 21/22/23，分别为加速持续秒数、抽牌间隔修正系数、PVE 封抽转为双倍抽牌速度的持续秒数。负的 interval modifier 表示缩短抽牌间隔；不要把持续时间当作百分比。

`combat.hit` 用于怪物意图、机器人出牌及 PVP 受击的表现，不作为客户端自行扣血的第二条账本；生命/护盾状态以快照为准。该表现推送对慢连接有 250ms 超时并终止旧连接，避免卡住房间处理；事件可能需要通过 resume/快照恢复，不能让缺少飘字阻塞操作。

### 10.5 被动、PVP 与怪物卡实例

自身 `player.battle_status` 和对手 `duel.opponent_status` 使用 `RoomBattleStatus`：`passive_kind` 为 `LinYuan/FenXian/ZaiYue`，并带 `combo/core_element`、`bonuses`、`sets`、`draw_interval_seconds`。`bonuses` 是 key/value 列表，仅下发非零项；包括被动治疗/控制/护盾、专武、元素伤害与抗性、效果套和抽牌/逃脱修正。`sets` 返回 kind/count/required/active，客户端直接呈现服务器激活状态，不按图片件数自行计算。

`RoomDuel` 还提供 `opponent_class/opponent_name/escape_probability`、后入场解锁时间、离开窗口截止、自身是否已申请离开和逃脱剩余时间。对手手牌、背包与地图位置不在此公开投影中。离开、逃脱和出牌是否可用以 `allowed_actions` 为准；双方未连接时不能出牌。`duel.ended` 后重新读取快照，胜者或双方存活者会恢复冻结的 PVE/行动状态；不要把 PVP 手牌直接当回到 PVE 后的牌堆。

`RoomCard` 新增 `level`（字段 3，旧包默认 0）与可选 `element_override`（字段 4）。后者只用于 `M-BOXSPIRIT`：缺失表示使用基础配置，`None` 表示该次匣灵为无属性、造成直伤 7，五行值表示对应元素伤害 7；这不是修改图鉴卡。客户端先复制基础卡定义，再应用实例覆写和等级。匣灵保持 +0，不进入图鉴升级接口；覆写随弃牌循环、PVP 冻结还原和房间恢复保留。湮核的 `secondary_elemental_damage/secondary_element` 属于静态配置的独立第二段伤害，不复用匣灵的实例覆写字段。

### 10.6 恢复与可靠性范围

永久资产写入与结算具备数据库幂等和事务回滚；房间状态依靠关键状态检查点及周期快照恢复。当前命令完成通知可能先于房间快照落盘，因此任意操作 ACK 不能解释为“立即强杀也零丢失”。本轮真实进程验证在撤离关键快照已经保存后强杀，确认读条恢复、资产提交和再次重启均不重复入账。发生重连时必须读取服务端快照，不能只重放本地 UI 状态；详细证据和未覆盖项见 [POSTGRES_TESTS.md](POSTGRES_TESTS.md)。

## 11. Godot 客户端落地建议

### Store 分层

- `SessionStore`：token、expiresAt、lastSequence、连接状态。
- `PlayerStore`：player、wallet、materials、cards、decks、weapons、loadouts。
- `PreparationStore`：草稿、创建中、Active snapshot、取消中、错误。
- 局内状态与大厅永久资产分离，按 `room.snapshot` 和局内命令更新；不能让客户端战斗展示直接写永久资产。

### 请求规则

- 所有 HTTP 从统一 Gateway 注入 Authorization、X-Trace-Id、超时和 ProblemDetails 解析。
- PUT 使用 Store 当前 version，并为一次 UI 提交生成固定 `Idempotency-Key`；网络重试复用，409 后刷新且不自动覆盖玩家新状态。
- POST preparation 在 UI 一次提交期间固定 Idempotency-Key；网络重试复用。
- DELETE preparation、match ticket、market listing 同样为一次用户操作固定 `Idempotency-Key`；同键不得改目标 ID。
- 服务端成功响应到达前，不乐观增加资产或改变权威 preparation 状态。

### DTO 兼容

- 网络 DTO 与 Godot `Node/Control/Resource` 分离；HTTP 保持 camelCase，Protobuf/Godot schema 使用 snake_case。
- UUID、可选枚举、字符串小数与 64 位时间戳按协议解码；新增 Protobuf 字段后同步生成 `client/data/realtime_schema.json`，避免只改界面脚本。
- REST 响应字段允许增加，JSON 反序列化器忽略未知字段；WebSocket Protobuf 同样忽略未知字段。

## 12. 当前联调验收清单

以下保留客户端逐项交互验收清单；自动化服务测试通过不等于所有 Godot 界面已逐屏人工验收。

- [ ] 首次登录只生成一个内部玩家，重复登录资产不重复。
- [ ] Bootstrap 得到三职业武器、编组，五部位配装全空；初始余额为 0。不发放绑定白鞋。
- [ ] 档案更新 version +1；同幂等键重试回放成功响应，旧 version 的新请求返回 409。
- [ ] 图鉴返回全部 220 张，其中 51 张初始解锁，三套编组各 20 张。
- [ ] 非 20 张、跨职业卡、超持有数量的编组返回 400。
- [ ] 合法编组/穿戴保存 version +1；同幂等键重试回放成功响应，旧版本的新请求返回 409。
- [ ] 免费包准备成功；重复同幂等键返回同 preparationId。
- [ ] 同幂等键改请求体返回 409。
- [ ] Active 准备可查询、可取消；取消后 GET 返回 404。
- [ ] WebSocket 收到 session.connected，ping 得到 pong。
- [ ] 断线后 resume 可重放缺失 sequence；重复事件不重复应用。
- [ ] 匹配成功收到 `match.found` 与 `room.ready_required`；全员 Ready 可提前收到 `room.started`。
- [ ] 15 秒超时后未 Ready 真人收到 `room.ready_removed`，保留真人进入固定 4 席房间且首快照只含本人可见信息。
- [ ] 卡升级与强化面板读取真实报价，+4/+5 材料及编组副本保护正确，失败不修改本地余额。
- [ ] 局内格位移动、换装、遗物详情和交换使用权威版本；分类预览、速度字段、被动/PVP 信息与实例元素正确显示。
- [ ] 死亡回大厅后身上防具进遗物堆，配装栏保持空；开局与死亡都不发放绑定白鞋。
- [ ] 商店货架含礼包/魂/碎片/药剂/探索包与每日三张单卡；匹配 enqueue/cancel 使用同一 Idempotency-Key 回放。

2026-09-10 最终回归：领域 202/202、服务 157/157，通过且无跳过；服务 Release 构建 0 警告、0 错误。服务全套启用独立 Docker/PostgreSQL 测试数据库，含真实 HTTP 16 路同键升级只扣一次，以及真实 WS 的 PVP 击杀、遗物读取/拾取、重复请求、已落盘撤离状态后强杀恢复及二次重启不重复结算。服务测试报告为仓库根目录 `artifacts/gameplay-validation/gameplay-final.trx`，范围见 [POSTGRES_TESTS.md](POSTGRES_TESTS.md)。该结果包含最终地图分组与匣灵实例覆写，不代表真实 Steam 平台验票、任意 ACK 后零丢失或持续生产负载验收完成。
