# Relicbound（遗境行者）本地服务器

服务遵循 `GDD.md` 第 8 章：ASP.NET Core / .NET 10 模块化单体、PostgreSQL 权威存储、REST + WebSocket、内部 `UserId` 与平台身份隔离。开发与构建基线为 **.NET SDK 10.0.400**。当前代码已包含 S2–S9 纵向切片、RoomActor、房间恢复和补位机器人运行时；具体完成门以现状审计为准。

## 已实现

- 本地名称账号登录：`POST /api/v1/auth/local`（仅 Development）；同名重登原 UID，新名称创建独立 UID
- Steam 票据登录：`POST /api/v1/auth/steam`（默认关闭，服务端向 Steamworks 验票）
- 当前玩家档案：`GET/PUT /api/v1/players/me`（PUT 要求 `Idempotency-Key`）
- 乐观并发版本，避免档案静默覆盖
- V001–V003 PostgreSQL 版本化迁移、checksum、迁移锁与就绪检查
- 首次玩家幂等初始化：钱包、材料、起始卡/编组、专属武器；五部位配装全空，不发放绑定白鞋
- 大厅 Bootstrap：`GET /api/v1/bootstrap`
- 图鉴与编组：`GET /api/v1/cards`、`GET/PUT /api/v1/decks`（PUT 要求 `Idempotency-Key`）
- 探索准备：`GET/POST/DELETE /api/v1/preparations`，支持资产校验和幂等重试
- WebSocket 会话入口：先用 Bearer 调用 `POST /api/v1/realtime/ticket`，再连接 `/ws/v1/session?ticket=...`（短时单次票据）
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

Windows 下可直接双击 `start-server.bat`。脚本优先使用 Docker Desktop，并自动识别系统安装和当前用户安装目录，不要求手工添加 PATH。Docker 不存在时改用本机 .NET；已安装但未启动 Docker 时会提示先启动 Docker Desktop，也可传 `--native` 明确使用本机模式。

- `start-server.bat`：构建、后台启动并等待健康检查通过
- `run-local-server.bat`：使用本机 .NET 构建、后台启动，连接已配置的 PostgreSQL
- `stop-server.bat`：Docker 模式停止服务器与 PostgreSQL；本机模式只停止本脚本启动的应用，保留数据库内容
- `update_server.bat`：重新构建当前模式的服务器；本机模式可显式传 `--native`；传 `--cloud` 则更新腾讯云
- `cloud-update.bat`：调用腾讯云的安全更新脚本；加 `--push` 时先把已提交的当前分支推送至 GitHub
- `cloud-status.bat`：显示腾讯云当前已部署的 Git 提交并检查服务健康状态
- `clear-local-database.bat`：确认后删除**仅本地** PostgreSQL 数据卷，重建数据库、应用全部迁移并重新启动服务
- `backup-all-local-data.bat`：将完整本地 PostgreSQL 数据库复制到 `local-backups/`，并生成 SHA-256 校验文件

在命令行中也可以运行；加 `--no-pause` 可在结束时不等待按键：

```powershell
cd server
.\start-server.bat --no-pause
.\start-server.bat --native --no-pause
.\update_server.bat --cloud --push --no-pause
.\cloud-status.bat --no-pause
.\stop-server.bat --no-pause
.\clear-local-database.bat --no-pause
.\backup-all-local-data.bat --no-pause
```

## 腾讯云更新

云端只跟踪 GitHub 的 `release` 分支。先在 `release` 分支完成本地 `git commit`，随后运行：

```powershell
cd server
.\update_server.bat --cloud --push
```

`--push` 只推送已经提交的 `release` 变更，不会自动提交工作区内容；不传它时，脚本仅部署已存在于 GitHub `release` 的最新提交。为避免误发布，云端批处理会拒绝非 `release` 分支。首次使用时，把 `cloud-env.example.bat` 复制为 `cloud-env.local.bat`，并填写 SSH 私钥路径。该本地配置已被 Git 忽略。

云端以 Git 提交号作为版本号，并在 `/opt/fantasycard-app/version-manifests/` 保存已部署版本的运行文件 MD5 清单（服务端源码、生成配置、构建与代理配置、部署脚本）。更新时，Git 仅传输仓库差异；脚本比较 MD5 清单并打印新增、修改、删除的文件。服务端运行文件变化时才备份 PostgreSQL、重建应用容器；只有 `Caddyfile` 变化时只重载代理；客户端或文档变化时无需重建服务器。MD5 只用于判断文件是否变化，版本来源仍以 Git 提交号为准。清单和版本标记在健康检查成功后一起更新；失败时下次会重新尝试。云端 `.env` 和数据库不会被覆盖或清空。可执行 `cloud-status.bat` 查看已部署提交、清单版本及健康状态。

清库不可恢复，脚本默认要求按 `Y` 确认。自动化环境可额外传入 `--yes` 跳过确认；它只操作固定的 Compose 项目 `fantasycard-local`，不会用于 Staging 或 Production。

完整备份使用 PostgreSQL 原生 `pg_dump` 自定义格式，包含全部用户和业务表、迁移表与数据库结构。备份文件含身份和会话等敏感数据，位于 `server/local-backups/` 且已被 Git 忽略；跨设备迁移时请同时复制 `.dump` 与 `.sha256` 文件，不要提交到仓库。

对应的 Docker 命令为：

```powershell
cd server
docker compose up -d --build
```

服务地址为 `http://localhost:5080`。可用 `http/FantasyCard.Server.http` 依次调用服务信息、健康检查、登录、Bootstrap、图鉴/编组和准备接口。

只在本机运行应用时，需要安装 **.NET SDK 10.0.400**（版本由 `global.json` 锁定），并先启动 PostgreSQL。本机启动器连接现有数据库，不创建或清空数据库；默认使用 `localhost:5432/fantasycard`，也可以通过 `ConnectionStrings__Postgres` 环境变量指定连接。本机停止脚本不会停止由外部管理的 PostgreSQL。

```powershell
docker compose up -d postgres
.\run-local-server.bat --no-pause
```

本机启动每次在 `.artifacts/local-build/` 重新还原和构建，避免使用从旧电脑复制来的 `bin/obj` 和绝对路径缓存。后台进程身份与日志保存在 `.artifacts/local-server/`；启动失败会打印日志，重复启动会检查现有进程是否健康。自定义本机监听地址可设置 `ASPNETCORE_URLS`。更新本机程序前先运行 `stop-server.bat`，更新后再启动。

迁移 SQL 的校验统一使用 LF 换行，并兼容旧版本写入的 LF/CRLF 校验值，因此 Windows/Linux 或 Git 换行转换不会误报迁移内容变化。实际 SQL 改动仍会阻止启动，不会自动改写历史校验值；遇到此类错误不要用清库脚本绕过，应恢复原迁移并新增版本。

Docker 模式复用已有基础镜像，只在缺失时下载；本地登录通过 Compose 的 Development 配置显式开启。数据库备份/清理脚本只操作固定 Docker 项目；使用外部 PostgreSQL 时应使用对应数据库的备份工具。

运行测试：

```powershell
dotnet test FantasyCard.Server.slnx
```

可用 `dotnet --version` 检查当前目录解析到的 SDK，预期输出 `10.0.400`。

## HTTP 与 WebSocket 消息

第一方登录/玩法 HTTP 使用 `application/protobuf`。契约、生成和字段适配见 [网络契约](../docs/network-protobuf-migration/protocol-compatibility.md)。公告、管理和登录前信息仍使用 JSON。原有 `.http` JSON 示例仅适用于显式设置 `ProtobufHttp:AllowLegacyJson=true` 的旧客户端兼容测试。旧 WebSocket 查询令牌也必须显式设置 `Realtime:AllowLegacyAccessTokenQuery=true`，默认关闭。

构建容器时 Compose 的 context 为仓库根目录，以包含 `protocol/`；Dockerfile 的保护流程保持原样。此迁移没有执行生产部署。

WebSocket 只收发 Protobuf v1 二进制帧。以下为解码后的字段示意，不能作为 JSON 文本帧发送。连接成功后服务端发送带事件序号的消息：

```json
{"type":"session.connected","traceId":"...","payload":{"playerId":"..."},"eventId":"...","sequence":1,"occurredAt":"..."}
```

客户端应按 `ClientEnvelope` 编码发送以下语义：

```json
{"type":"ping","requestId":"ping-00000001","payload":null}
```

当前 WebSocket 已支持会话恢复、玩家隔离房间快照、移动、PVE/PVP 出牌、三选一、遗物、撤离、泉水与决斗操作；完整类型清单见客户端联调文档。
