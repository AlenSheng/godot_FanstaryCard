# FantasyCard 本地服务器

服务遵循 `GDD.md` 第 8 章：ASP.NET Core / .NET 10 模块化单体、PostgreSQL 权威存储、REST + WebSocket、内部 `UserId` 与平台身份隔离。开发与构建基线为 **.NET SDK 10.0.400**。当前代码已包含 S2–S9 纵向切片、RoomActor、房间恢复和补位机器人运行时；具体完成门以现状审计为准。

## 已实现

- 本地设备身份登录：`POST /api/v1/auth/local`（仅 Development）
- Steam 票据登录：`POST /api/v1/auth/steam`（默认关闭，服务端向 Steamworks 验票）
- 当前玩家档案：`GET/PUT /api/v1/players/me`（PUT 要求 `Idempotency-Key`）
- 乐观并发版本，避免档案静默覆盖
- V001–V003 PostgreSQL 版本化迁移、checksum、迁移锁与就绪检查
- 首次玩家幂等初始化：钱包、材料、起始卡/编组、专属武器和绑定白鞋
- 大厅 Bootstrap：`GET /api/v1/bootstrap`
- 图鉴与编组：`GET /api/v1/cards`、`GET/PUT /api/v1/decks`（PUT 要求 `Idempotency-Key`）
- 探索准备：`GET/POST/DELETE /api/v1/preparations`，支持资产校验和幂等重试
- WebSocket 会话入口：`/ws/v1/session?access_token=...`
- `ping` / `pong`、sequence、最近事件重放、`session.resume`、同账号连接接管与 16 KiB 消息上限
- 实时事件流按 `Realtime:EventStreamIdleRetentionMinutes` 回收；缓存失效后客户端通过 session/room snapshot 恢复
- JSON 结构化日志、请求追踪 ID、OpenTelemetry traces/metrics OTLP 接口
- 登录、市场读取、经济写入与 WebSocket 命令分层限流
- 市场、装备、成交单与经济账本链的周期性只读一致性审计
- Running 房间恢复与快照持久化纳入 readiness
- 领域与实时协议自动化测试

本地登录只用于开发。Steam 登录启用后映射到相同的内部 `UserId`；微信登录仍等待平台参数与联调环境。

代理开发流程见 [server_create 技能](../.agents/skills/server_create/SKILL.md)：先读 GDD / `docs/SERVER_SPEC.md` / `docs/SERVER_0_TO_1_GUIDE.md`，规则冲突先停手，无冲突全权开发，改完跑相关测试。

客户端 REST/WebSocket 联调协议、示例和验收用例见 [`docs/CLIENT_INTEGRATION.md`](./docs/CLIENT_INTEGRATION.md)。当前完成度、剩余缺口与开发顺序见 [`../docs/SERVER_IMPLEMENTATION_STATUS_AND_PLAN.md`](../docs/SERVER_IMPLEMENTATION_STATUS_AND_PLAN.md)。
Staging/Production 发布、drain、回滚、备份恢复和事故处置见 [`docs/OPERATIONS_RUNBOOK.md`](./docs/OPERATIONS_RUNBOOK.md)。

## 启动

需要先安装并启动 Docker Desktop。Windows 下可直接双击：

- `start-server.bat`：构建、后台启动并等待健康检查通过
- `stop-server.bat`：停止服务器与 PostgreSQL，但保留数据库内容
- `clear-local-database.bat`：确认后删除**仅本地** PostgreSQL 数据卷，重建数据库、应用全部迁移并重新启动服务
- `backup-all-local-data.bat`：将完整本地 PostgreSQL 数据库复制到 `local-backups/`，并生成 SHA-256 校验文件

在命令行中也可以运行；加 `--no-pause` 可在结束时不等待按键：

```powershell
cd server
.\start-server.bat --no-pause
.\stop-server.bat --no-pause
.\clear-local-database.bat --no-pause
.\backup-all-local-data.bat --no-pause
```

清库不可恢复，脚本默认要求按 `Y` 确认。自动化环境可额外传入 `--yes` 跳过确认；它只操作固定的 Compose 项目 `fantasycard-local`，不会用于 Staging 或 Production。

完整备份使用 PostgreSQL 原生 `pg_dump` 自定义格式，包含全部用户和业务表、迁移表与数据库结构。备份文件含身份和会话等敏感数据，位于 `server/local-backups/` 且已被 Git 忽略；跨设备迁移时请同时复制 `.dump` 与 `.sha256` 文件，不要提交到仓库。

对应的 Docker 命令为：

```powershell
cd server
docker compose up -d --build
```

服务地址为 `http://localhost:5080`。可用 `http/FantasyCard.Server.http` 依次调用服务信息、健康检查、登录、Bootstrap、图鉴/编组和准备接口。

只在本机运行应用时，需要安装 **.NET SDK 10.0.400**（版本由 `global.json` 锁定），并先启动 PostgreSQL：

```powershell
docker compose up -d postgres
dotnet run --project src/FantasyCard.Server
```

运行测试：

```powershell
dotnet test FantasyCard.Server.slnx
```

可用 `dotnet --version` 检查当前目录解析到的 SDK，预期输出 `10.0.400`。

## WebSocket 消息

连接成功后服务端发送带事件序号的消息：

```json
{"type":"session.connected","traceId":"...","payload":{"playerId":"..."},"eventId":"...","sequence":1,"occurredAt":"..."}
```

客户端可发送：

```json
{"type":"ping","requestId":"ping-00000001","payload":null}
```

当前 WebSocket 已支持会话恢复、玩家隔离房间快照、移动、PVE/PVP 出牌、三选一、遗物、撤离、泉水与决斗操作；完整类型清单见客户端联调文档。
