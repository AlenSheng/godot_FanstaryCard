# FantasyCard 开发文档索引

| 项目 | 内容 |
| --- | --- |
| 基准 GDD | `GDD.md` Draft v0.64，2026-09-02 |
| 客户端 | 团结引擎，Unity 2022.3 LTS 基线，C#，UGUI |
| 服务端 | ASP.NET Core / .NET 10 LTS，SDK 10.0.400，PostgreSQL，REST + WebSocket |
| 首发目标 | Steam Windows，标准难度原型 |
| 文档用途 | 从现有原型代码继续开发，完成登录 → 大厅 → 探索准备 → 匹配 → 地图 → PVE/PVP → 撤离/死亡结算全链路 |

服务端任务由技能 [server_create](../.agents/skills/server_create/SKILL.md) 约束：先读 GDD / 服务器规范 / 0→1 指南；规则冲突先停手；无冲突全权开发；改完跑相关模块测试。Cursor 每次会话通过 `.cursor/rules/server_create.mdc` 自动引用该技能。

## 1. 阅读顺序

1. [策划配置与导表流程](./CONFIG_PIPELINE.md)：Excel 源表、字段约定、校验、Protobuf 配置包与双端发布。
2. [端到端流程与协议](./END_TO_END_FLOW_AND_PROTOCOL.md)：端服共同状态机、时序、命令/事件和异常恢复。
3. [客户端技术规范](./CLIENT_SPEC.md)：预表现与权威、界面状态、输入、情报、手牌与掉线表现（GDD v0.63 口径）。
4. [服务器设计规范](./SERVER_SPEC.md)：权威、10 Hz tick、冻结快照、匹配 30s 补机器人、掉线 15s、房间指令表。
5. [客户端 0→1 开发指南](./CLIENT_0_TO_1_GUIDE.md)：工程结构、页面、状态仓库、网络层、逐阶段开发和客户端验收。
6. [服务端 0→1 开发指南](./SERVER_0_TO_1_GUIDE.md)：模块、数据模型、权威房间、事务、幂等、测试和部署。
7. [服务端现状审计与开发计划](./SERVER_IMPLEMENTATION_STATUS_AND_PLAN.md)：当前完成度、真实缺口、阶段优先级和验收门。
8. [当前服务器客户端对接指南](../server/docs/CLIENT_INTEGRATION.md)：只描述当前真实可调用的登录、Bootstrap、图鉴/编组、准备和 WebSocket 协议。

## 2. 规则优先级

发生冲突时按以下顺序处理：

1. `GDD.md` 的 v0.64 锁定规则，尤其 `0.2` 冻结模块与 **5.14 补位机器人**。
2. [CLIENT_SPEC.md](./CLIENT_SPEC.md) / [SERVER_SPEC.md](./SERVER_SPEC.md) 的口径裁决。
3. 本目录中的端到端协议和开发流程。
4. `server/docs/CLIENT_INTEGRATION.md` 中已上线接口的具体字段。
5. 当前原型代码。

本目录不修改 GDD 玩法。若实现中必须改变地图情报、生命/护盾/回血、职业本命、独立 PVE + 同格 1v1、背包/遗物等冻结规则，先按 GDD `0.2 发起二次确认，不能由程序自行“合理化”。

## 3. 当前仓库基线

服务端开发机与 CI 统一使用 `.NET SDK 10.0.400`；`server/global.json` 是唯一版本锁定来源。升级 SDK 时必须同时更新该文件、Docker 构建镜像和本索引所列开发文档。

| 能力 | 当前状态 | 主要位置 |
| --- | --- | --- |
| 客户端纯 C# 分层 | 已有 `Game.Contracts / Game.Domain / Game.Client` 三层程序集 | `FantasyCard_Unity/New Tuanjie Project/Assets/Scripts` |
| 6×6 地图、Boss/泉水/撤离/宝箱、出生和怪组生成 | 已有本地领域实现 | `MapGenerator.cs`、`MapService.cs` |
| 200 图鉴、三职业默认编组、编组校验 | 已有本地领域与原型 UI | `CardDatabase.cs`、`DeckService.cs`、`CodexScene.unity` |
| 战斗数值、三职业本命、装备词缀 | 已有本地领域实现 | `CombatService.cs`、`BattleState.cs`、`EquipmentData.cs` |
| 手牌 5、弃牌洗回、1v1 三堆快照 | 已有本地领域实现 | `DeckState.cs` |
| PVE 怪意图和同格 1v1 规则骨架 | 已有本地领域实现 | `MonsterInstance.cs`、`GridCombatManager.cs` |
| 地图/战斗/图鉴原型场景 | 已有 | `MapScene.unity`、`BattleScene.unity`、`CodexScene.unity` |
| 迁移、登录、玩家初始化、Bootstrap、档案、图鉴/编组、准备快照 | 已有 `0.2.0-s1-preparation` 纵向切片 | `server/src`、`server/docs/CLIENT_INTEGRATION.md` |
| Unity 登录/大厅/准备/匹配/在线房间 | 未实现 | 本文档的首要工作 |
| 服务端换装/强化/商店/市场/匹配/战斗/结算 | 未实现 | `SERVER_IMPLEMENTATION_STATUS_AND_PLAN.md` 的 P1–P5 |
| 会话 sequence/replay/resume | 已有内存实现 | `server/src/FantasyCard.Server/Realtime` |
| 房间快照与进程恢复 | 未实现 | S3/S9 必须补齐 |
| Unity 自动化业务测试 | 未建立 | 需建立 EditMode + PlayMode 测试程序集 |

当前 `BattleController`、`MapSceneController` 等是本地演示控制器，不是线上权威客户端。后续保留其表现和纯领域算法价值，但线上战局必须由服务端事件驱动，客户端不得自行决定伤害、抽牌、掉落、移动或结算。

## 4. 原型范围边界

### 必须完成

- 本地开发身份登录；正式 Steam 身份通过平台适配层预留。
- 大厅三职业切换、图鉴、恰好 20 张编组、五部位穿戴、锁定专属武器、强化。
- 金币商店、金币装备市场、探索背包、生命药剂。
- 标准难度混沌领域，1–4 人，6×6，独立 PVE + 同格 1v1。
- 手牌上限 5、弃牌循环、怪物卡、三选一、泉水、遗物、撤离与死亡结算。
- 服务端权威、可重连、可审计、结算幂等。

### 明确不做

- 厄运选档 UI 和倍率实装。
- 红装掉落实装、红卡。
- 钻石购买、钻石市场、钻石兑金币。
- 本场临时牌池内容、完整双抽/临时抽骰表。
- 自建社交、微服务、Kubernetes、事件溯源、CQRS、单独 Web 前端。

## 5. 共同完成标准

一个模块只有同时满足以下条件才算完成：

- 规则：与 GDD 对应章节一致，冻结规则没有被隐式改写。
- 协议：请求、成功、业务拒绝、超时、重试和重连都有定义。
- 权威：涉及资产、战斗、随机、计时和胜负时，以服务端为准。
- UI：有加载、空、成功、失败、冲突、断线恢复状态。
- 数据：有数据库迁移、版本字段、幂等键和经济流水。
- 测试：领域单测、接口集成测试、客户端状态测试和至少一条端到端用例。
- 可观测：日志含 traceId / playerId / matchId / roomId / commandId，且不记录令牌。
- 验收：产品可从登录连续操作到回到大厅，不靠编辑器手工改状态。
