# 当前结算读取配对测量与限定所有权验收

本轮仅关闭 `PR13-B11.3-T03/LIVE`，B11.3 仍为 Partial，T02 的 LIVE/POSTGRES/RENDER 尚未验收。全局仍 58 Accepted、74 项未验收，案例/层级缺口 274→273。成本数据没有自动变成 NoChange、完整每局优化收益或全项目通过。

恢复一份真实测试库备份，其中有 1 份资产已完成但未 ACK 的原始收据。来源整轮此前失败/中断，仍保留为失败；没有改写 acknowledged_at、hold、结算或装备来制造试验状态。私有库保留原 16 玩家、8 局、32 收据、31 ACK，在启动完整当前 Program 前增加仅限本库的“禁止新增 matches”保护。实际新增账号/对局均为 0，三轮重复测量的是同一真实收据，不能当成三个独立对局样本。

使用当前 Godot Gateway、Protobuf 和完整 21 文件 Program（Server `245265ff`），单个读取客户端每轮执行 10 组配对，Bootstrap/按ID两种顺序各5组，共60次测量、30组结算核心数据完全一致的配对。另查询三个不同真实他人收据，均实际404；当前所有权断言与同 DLL 的真实 Pending/ACK409/Bootstrapnull及45张等待/恢复原图分别关联，闭合 T03 LIVE。本人 Pending 详情可以200，同局参与者的按match查询可以返回本人收据200；没有重犯把合法200当作越权/就绪缺陷的误判。

响应体固定为 Bootstrap 36315B、按ID 213B。三个配对轮的服务端 HTTP 中位数分别约45.34/5.28ms、47.79/3.37ms、38.16/4.01ms；客户端中位数另记录为95.5/25ms、108/25ms、91/25ms，包含客户端帧调度与网络，不混作 SQL 时间。两条路由每次都只有一个逻辑请求，**没有声称请求次数下降或上线了新优化**。这里只比较已经存在的两种路由，不能把本轮前后数据伪装成新候选 A/B。

每次 Bootstrap 有14个 Npgsql 查询操作、19条显式 SQL，按ID为2个操作、2条 SQL。SQL条数来自实际操作 query.text 的顶层语句解析，保留引号、dollar body和嵌套注释，解析不完整记未知；不是把操作数直接充当 SQL 数。数据库30个配对窗口共1423条调用，包含背景服务 SQL，不能全部归给前台测量，也不能把窗口耗时当成某条请求的 SQL 执行时间。规划统计本次实际开启；原先关闭规划统计、池等待未采得的旧报告保持原结论。

增加只用于隔离测量的外部 StartupHook，不修改或重建游戏 Server/Domain。它通过标准 Activity/Meter 监听关联客户端 logicalID、服务端 HTTP 和实际数据库操作；池名只写hash，SQL文本只写hash，不写token、密码或参数值。指标依据为 [Npgsql 10.0.3 MetricsReporter](https://raw.githubusercontent.com/npgsql/npgsql/v10.0.3/src/Npgsql/MetricsReporter.cs)、[连接池排队实现](https://raw.githubusercontent.com/npgsql/npgsql/v10.0.3/src/Npgsql/PoolingDataSource.cs) 和 [Npgsql Activity 源](https://raw.githubusercontent.com/npgsql/npgsql/v10.0.3/src/Npgsql/NpgsqlActivitySource.cs)。HTTP起止按 [.NET 10 Hosting 源码](https://raw.githubusercontent.com/dotnet/aspnetcore/v10.0.0/src/Hosting/Hosting/src/Internal/HostingApplicationDiagnostics.cs) 关联。

本地先用相同 Npgsql DLL 的真实1连接池制造第二次 Open 等待，确认 pending 的+1/-1和至少50ms持续时间能够被捕获；不是用自造计数器冒充正对照。当前观察器的本地真实 API、关闭控制及20项控制器负例通过，再复制云端。云端60个测量请求都关联到完整 HTTP 起止和查询活动，观察器正常结束、错误计数0。所有测量窗口的池排队积分及池超时均为实测0；这是该池“等待可用连接的排队请求”时间，不是所有 Open 延迟或全局无等待。该指标的解释受相同版本的真实正对照和完整监听记录约束。

**原失败与限制不能省略。** 首次本地60次查询/30配对、三次他人404和资产检查成功，但 Windows TerminateProcess 没有触发观察器尾记录，原整轮仍失败。冻结原观察器 DLL和源码，不改判；修复仅为测量器增加本地关闭信号，另以两条读取和一条404完成实际HTTP/正常收尾控制，没有重跑本地60次。随后当前观察器真实池正对照重新通过。三轮云端60次则属于另行冻结的 Linux 同档位测量，不与 Windows 合并估计性能。

云端全程为当前代码和声明的私有100/200/500请求余量，旧默认10/30/120失败保留，READY15、HTTP10/30秒和资产就绪规则未改。所有60个测量请求成功且核心数据相等；Native349项检查、独立45项来源/数据核对通过。完整16人空间和八类资产表在测量前后逐表摘要相同。这个单用户暖态数据集不证明并发容量、完整每局节省、故障恢复流量下无热点或现有 Bootstrap 可被任意精简。

201份原件在PG移除前回存G盘并逐文件SHA验证，最终206份原件再次核验。清理准备文件上传及代码归档下载分别发生SSH10054；先验证准确远端前缀/文件状态，再续传同一文件和已生成的同一归档，没有重跑测量。最后下载使用有上界的并发预取，完整hash及每个成员通过后才清理。333个代码/程序成员回存校验后，精确删除2个输入/上传目录、3428个文件名、1个空工作目录与临时清理启动器。本地代码、旧失败、云端raw保留，共享缓存2104个输入及生产指纹/健康200不变。

本机只有隐藏 headless/Dummy 和私有本地PG/.NET校验，没有取图或焦点操作；本轮没有新增渲染图、产品代码或资源。GDD主卷覆盖基础卷，两卷全文按原字节固定到G盘，合法80/70不钳制、不误报。真人体验排除，原15%容量磁盘门槛仍未通过。后续继续 T02/LOAD08.4 的完整工作负载与候选/NoChange裁决，不能把本轮逐请求对比当成较宽目标完成。
