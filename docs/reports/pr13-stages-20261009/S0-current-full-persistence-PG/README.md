# PR13 当前 Persistence 命名空间全量 PostgreSQL 原生回归

冻结全部 Category=PostgresIntegration 且 FullyQualifiedName 属于 FantasyCard.Server.Tests.Persistence 的原生测试，使用实际现有146文件程序集，不修改生产、测试源码或运行时。原编译源9555aa...与当前328源逐文件Git等价，程序集SHA固定。预先由真实dotnet适配器发现完整筛选清单，保存每个参数化行的名称，再执行同一固定筛选器；实际TRX必须与发现清单一一对应且全部通过、无跳过、无额外或缺失行。发现清单不是执行后缩小目标。

程序集包括当前数据库迁移、bootstrap批读取与取消、卡组／经济／市场／强化／装备、房间／结算／恢复、数值和连接池等Persistence测试；不称全部解决方案、Program／Godot／公网或强度实验。本次是明确子系统全回归，不直接映射并关闭未验收案例格，也不替代其他实际入口条件。

云端独立PG max_connections100、512MiB，SDK1400MiB，xunit原程序集原配置maxParallelThreads1。每个测试自身并发、原超时和断言保持。内存500MB、云盘15%安全线不变，共享锁等待B04当前包结束，单工作者不与B04重叠。真实清单、nativeTRX、日志、资源及终态原件转存G；任何真实失败保留，不能删除测试变绿。仅实际全部通过且G完整SHA／CRC、无占用后清理该副本。当前尚未执行，全部门禁和验收状态保持。
