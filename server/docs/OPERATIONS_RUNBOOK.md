# FantasyCard 服务端发布与恢复 Runbook

本文用于 Staging/Production 发布、回滚、备份恢复和房间故障处置。玩法与数据边界以 `GDD.md`、`docs/SERVER_SPEC.md`、`docs/SERVER_0_TO_1_GUIDE.md` 为准。

## 1. 环境基线

- Linux 容器运行 `FantasyCard.Server`，镜像内使用 .NET 运行时的非 root `APP_UID`。
- HTTPS/WSS 在可信反向代理终止；只向应用转发受信代理地址。
- PostgreSQL 凭据、平台票据密钥和 OTLP 地址从 Secret Store 或环境变量注入，不写入镜像和仓库。
- Steam 登录使用 `Identity__Steam__Enabled`、`Identity__Steam__AppId`、`Identity__Steam__PublisherKey`、`Identity__Steam__Identity` 注入；PublisherKey 不得出现在客户端、日志或发布单明文中。
- Production 必须设置 `ASPNETCORE_ENVIRONMENT=Production`，并确认 `Identity__EnableLocalAuth=false`。
- 每个环境使用独立数据库、密钥、配置发布目录和备份桶。禁止把本地 `fantasycard_dev` 密码用于 Staging/Production。
- 发布前记录应用镜像 digest、数据库迁移最高版本、`configVersion`、配置 SHA-256 和兼容客户端构建范围。

## 2. 发布前检查

1. 在干净工作区运行 `dotnet test FantasyCard.Server.slnx`。
2. 使用与目标环境同主版本的 PostgreSQL 执行迁移集成测试；必须设置 `FANTASYCARD_TEST_POSTGRES`，不得接受跳过结果作为发布通过。
3. 运行配置导出，确认服务端与客户端 `fantasycard.config.bytes` 字节一致，版本和 SHA-256 与发布单一致。
4. 构建镜像并记录不可变 digest；扫描基础镜像和 NuGet 依赖。
5. 对目标数据库创建并校验发布前备份；执行 `pg_restore --list` 确认转储可读。
6. 确认 `/health/live` 与 `/health/ready` 的探针、日志收集、OTLP traces/metrics、告警和磁盘容量可用；`room-recovery` 或 `room-persistence` 不健康时不得接流量。
7. 确认 `fantasycard.settlement.failures`、`fantasycard.room.snapshot.failures`、`fantasycard.economy.reconciliation.violations` 无持续增长，并观察 Pending holds、实时连接数及各类 expired cleanup 计数是否符合流量预期。
8. 检查登录失败/过期令牌、WS resume/命令拒绝/消息大小、匹配排队时长、活动房间数/人数分布、RoomActor 队列/tick 延迟、快照耗时、PVE/PVP 时长与异常关闭、结算创建/幂等命中；异常增长时按 provider、reason、code、outcome 标签定位。
9. 检查 `fantasycard.database.migration.*` 与 `fantasycard.database.schema.version`；同时观察 Npgsql 10 的 `db.client.connection.count`、`db.client.connection.max` 和 `db.client.operation.duration`。数据源指标名固定为 `FantasyCard.Postgres`，不得暴露连接字符串。
10. 确认当前 Running 房间数量、结算 Pending hold 数量、RoomActor tick 延迟和市场写入流量。

任一检查失败即停止发布，不执行跳步迁移。

## 3. 向前兼容发布

1. 将实例置为 drain：停止接受新匹配和新房间；已存在房间继续运行并保持其锁定的 `configVersion`。
2. 等待 Running 房间自然结束。超过维护窗口的房间不得直接删除；保留快照和资产托管，转入人工处置。
3. 确认结算 Pending hold 已降为 0，或记录每个未完成 settlementId 供新版本继续幂等处理。
4. 应用只增不破坏的数据库迁移。迁移器会使用 advisory lock、事务和 checksum；checksum 不一致必须中止。
5. 部署新镜像，先启动单个 canary。等待 `/health/ready` 成功，再验证登录、Bootstrap、WebSocket、市场读取和一次不产生真实消费的测试流程。
6. 逐步替换剩余实例。观察至少一个完整监控窗口后解除 drain。
7. 记录发布时间、操作者、镜像 digest、迁移版本、配置 hash、健康结果和异常。

当前代码尚未提供跨实例房间 ownership，因此发布期间同一 Running 房间只能由一个实例恢复和持有；在实现租约前不得水平扩展 RoomActor 所有权。

## 4. 应用回滚

- 只回滚应用镜像，不回滚已经提交的数据库迁移。
- 回滚镜像必须在发布单兼容矩阵中声明可读取当前 schema 和当前房间快照。
- 若新版本已写入旧版本不认识的快照字段，保持新版本 drain 并修复向前兼容，不强启旧镜像。
- 回滚后重新检查 readiness、Running 房间恢复、Pending holds、市场 listing 状态和经济流水。

## 5. PostgreSQL 备份

- 使用 `pg_dump --format=custom --no-owner --no-privileges` 创建一致转储。
- 为转储生成 SHA-256，并把转储、校验文件、应用镜像 digest、迁移版本和 configVersion 一起写入备份清单。
- 备份加密后存入受控存储，限制读取权限并设置保留周期；数据库包含身份映射和令牌 hash，不得进入源码仓库。
- 每月至少在隔离数据库执行一次恢复演练。只有 `pg_restore --list` 和实际恢复后的业务校验都通过，备份才算可恢复。

## 6. 恢复演练

1. 创建与生产隔离、网络受限的空 PostgreSQL 实例，主版本不得低于源实例。
2. 校验转储 SHA-256；不一致立即停止。
3. 用 `pg_restore --clean --if-exists --no-owner --no-privileges` 恢复到隔离数据库。
4. 以恢复数据库启动同版本服务；确认迁移 checksum、readiness 和配置版本一致。
5. 抽查玩家聚合、活动 preparation、Running room 快照、match/player 状态、settlement holds、市场 listing 和经济流水。
6. 执行一次 `session.resume` 和房间 `room.snapshot` 恢复；不得产生重复结算或重复资产。
7. 销毁演练环境并记录恢复耗时、数据时间点、验证结果和发现的问题。

Production 恢复必须先保留故障库快照，禁止直接对唯一副本执行 `--clean`。

## 7. 告警与处置

| 告警 | 首要检查 | 处置 |
| --- | --- | --- |
| readiness 失败 | PostgreSQL 连通、迁移 checksum、连接池 | 停止接流量；修复连接或迁移，不绕过 readiness |
| Pending holds 积压 | settlement worker 日志、资产状态冲突 | 保持幂等重试；按 settlementId 排查，禁止手工重复发奖 |
| 经济余额为负/账实不符 | economy ledger、请求幂等键、listing 事务 | 关闭经济写端点，保留读取；导出审计记录后修复 |
| RoomActor tick 延迟 | CPU、GC、房间数、快照写耗时 | 停止新匹配；保留现有房间，按 roomId 定位热点 |
| Running 房间恢复失败 | snapshot JSON、configVersion、RNG 状态 | 隔离该房间并保留托管资产；不得删除快照或直接判失败 |
| PostgreSQL 磁盘告警 | WAL、备份、表增长、长事务 | 停止非必要写入，扩容或清理已确认可删除的数据 |

## 8. 事故证据

事故记录至少包含 `traceId`、`requestId`、`playerId`、`matchId`、`roomId`、`battleId`、`roomRevision`、`eventSequence`、`settlementId`、应用 digest、configVersion 和 UTC 时间。日志不得记录 access token、平台票据、数据库密码或完整 WS query。
