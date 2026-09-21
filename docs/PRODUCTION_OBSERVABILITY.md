# 生产监控与故障证据

仓库侧已经保留结构化控制台日志、ASP.NET/Npgsql/OpenTelemetry traces 和 metrics 接口，并提供 `POST /api/v1/telemetry/events` 接收受限的客户端启动、网络、ANR、崩溃事件。这个接口只接受事件类型、版本、平台和短错误码，不接受令牌、堆栈中的完整个人信息或付款凭证。

## 生产配置

服务端通过 `OTEL_EXPORTER_OTLP_ENDPOINT` 将 traces 和 metrics 发往运营方配置的 OTLP 后端。生产部署必须通过安全的运行时环境变量注入 endpoint，不得把 API key、collector token 或云账号写入仓库。当前仓库没有绑定具体云厂商，因此不能声称告警已生效。

## 必须创建的告警

- `/health/ready` 连续失败、数据库连接池耗尽、迁移失败。
- 登录失败率、401/429/5xx、Google provider unavailable。
- WebSocket 活跃连接、断线率、命令拒绝/限流、消息延迟。
- PVE/PVP 异常结束、结算失败、经济账目校验失败。
- Android crash-free users、ANR、启动失败、登录失败和网络恢复失败。

正式发布前必须用真实后端接收一条 trace、一条 metric、一条日志和一条客户端事件，验证脱敏、保留期、通知联系人和告警恢复；这些属于部署环境阻塞项。
