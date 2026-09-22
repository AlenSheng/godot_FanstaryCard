# 云端 2 核服务器压力点优化记录

## 服务器基线

本次依据云端实例信息调整：AMD EPYC 9754 宿主机，但容器实际只绑定 2 个逻辑 CPU；物理内存约 3.58 GiB；服务进程 RSS 约 229 MiB；启用 Server GC，GC 线程数为 2；容器没有内存上限，当前没有使用 swap。

CPU 1.7% 和系统负载 0.23 属于空闲采样，不能作为压测容量。2 核实例的主要风险是数据库连接竞争、房间命令积压、重复快照/结算工作和日志/观测开销叠加。

## 已完成的优化

- Npgsql 连接池默认调整为最大 16、最小 1；连接超时 5 秒、命令超时 10 秒、KeepAlive 30 秒。Compose 云端配置可以通过 `FANTASYCARD_DB_*` 环境变量覆盖。
- 增加 `/api/v1/economy/context`，一次返回商店、市场和库存；商店与市场读取在服务端并行发起，客户端只保留一次 HTTP 读取入口，减少重复的 HTTP 请求和库存查询。
- SettlementCoordinator 对同一比赛/玩家的成功结算做内存去重；并发中的重复观察会合并，失败仍可在下一次观察中重试，避免终局后每个 tick 重复访问数据库。
- RoomActor 使用容量 256 的有界命令队列。队列达到上限后快速返回过载错误，避免无限积压造成更大的延时和内存压力；房间权威状态仍保持单读者顺序执行。
- RoomActor 对已经返回完整快照的命令复用命令结果，减少一次深拷贝式快照生成。
- 客户端商店/市场页面优先请求聚合经济上下文，并保留旧接口 404 回退；云端旧版本升级前仍能兼容原接口。
- 商店读取改为按玩家/日重置键批量聚合购买数量，并一次性读取已拥有卡牌；移除市场读取路径中的过期写入。
- 日商店轮换和刷新状态初始化在进程内按重置键只执行一次；新增购买记录、活动卖家和活动过期索引（V027）。
- 只读 RoomActor 命令不再触发持久化观察快照；实时写操作与客户端房间快照合并到同一次 Actor 排队，减少一次房内往返。
- 新增 `fantasycard.room_actor.command.wait`，记录命令进入 Actor 队列到开始执行的等待时延，用于区分排队瓶颈和执行瓶颈。

## 监控接入

- 应用继续使用 OpenTelemetry，新增 .NET Runtime 指标，并支持将 metrics 与 traces 分别配置出口；云端只将 metrics 发往内网 `otel-collector:4317`。
- OTel Collector 将应用指标转换为 Prometheus 可抓取端点；Prometheus 同时采集 Collector 和 node-exporter，保存 7 天或最多 384 MB 数据。
- Grafana 预置“FantasyCard 云端总览”仪表盘，覆盖应用采集状态、主机 CPU/内存、HTTP 请求速率与 p95、实时连接数、房间 Actor 排队等待 p95。
- Collector、node-exporter、Prometheus、Grafana 均不映射公网端口；只在服务器回环地址提供 Prometheus `9090`、Grafana `3000`，通过 SSH 隧道访问。
- Prometheus 已配置应用采集中断、主机指标中断、CPU 超过 85%、可用内存低于 15%、Actor 等待 p95 超过 100ms 的规则。当前规则只在 Prometheus/Grafana 内显示，不配置外部通知渠道。
- 监控组件设置了合计约 768 MB 的容器内存上限和 0.75 CPU 配额，适配当前 2 核/3.6 GiB 实例；若后续压测发现内存回收或查询争用，再提高实例规格或下调 Prometheus 保留周期。

## 预期效果

这些调整主要降低数据库连接峰值、重复查询和房间队列尾延时。它们不会凭空提高 2 核服务器的 CPU 算力，也不会把同一 RoomActor 拆成并发写队列：同一房间仍由单写者保证 Revision、随机数和 tick 顺序；不同房间的 Actor 已可并行执行。若要进一步提高 tick 吞吐，应优先做跨房间调度分片或基于不可变快照的只读通道，而不是让同一房间并发写状态。

## 发布后的验证

1. 发布后检查 `/health/ready`，确认新版本已生效。
2. 采集 `fantasycard.room_actor.queue.length`、`fantasycard.room_actor.tick.delay`、`fantasycard.room.snapshot.duration`、Npgsql pool 状态、数据库查询耗时、CPU、RSS 和 GC pause。
3. 使用 5 分钟阶梯重新压测，分别记录 10、20、30、40 客户端阶段的稳定 HTTP p95、WebSocket RTT p95、429/5xx、队列长度和 tick 延迟。
4. 如果仍在 20 客户端附近出现 429，先判断是否为单一出口 IP 的读限流，再判断服务器资源；不要把 429 直接当作 CPU 达到上限。

本次改动已部署到云端 `release`：

- 版本：`7095170fb7b88de5b6f5b884d6f423f44c700580`；本地/公网健康检查均为 `Healthy`。
- V027 已由云端启动迁移实际应用；部署脚本在两次更新前均保留 PostgreSQL 备份。
- 北京时间午夜自动恢复任务已将临时压测限流恢复为 Auth=10、MarketRead=120、EconomyWrite=30。
- 部署后小规模公网回归（5 客户端、约 90 秒）：稳定 HTTP p95 813ms，WebSocket RTT p95 287ms，实时命令 p95 272ms，错误率 0%。健康检查 p95 在容器冷启动后约 1.28s，不能直接等同于玩家操作延时。
- 监控已实际接通：Prometheus 的 `fantasycard`、`node`、`prometheus` 三个目标均为 UP，5 条规则已加载，Grafana 仪表盘“FantasyCard 云端总览”可通过 API 查询到。
- 部署后最近一次采样组件实测占用约 214 MiB：Collector 约 35 MiB、node-exporter 约 9 MiB、Prometheus 约 32 MiB、Grafana 约 138 MiB；监控端口仍只绑定 `127.0.0.1`。
