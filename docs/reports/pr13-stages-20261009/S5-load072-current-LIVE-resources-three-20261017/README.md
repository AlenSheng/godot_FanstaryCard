# 当前真实LIVE：发压端资源、退出与FPS身份

三个LIVE规范案例通过，4个当前完整Godot客户端实际使用新合成账号连接项目服务，真实HTTPS/WS与严格known-host SSH只读Prometheus；原容量运行仍均未通过，不写成100人/600秒成功。云端容器ID/镜像/环境/started前后一致，无部署、限流、配置或源码上传。

**补齐的真实实现缺口：** 旧8客户端数据只有汇总CPU/RSS，缺逐PID与实际帧钟，原件仍按未测保留。当前psutil逐PID记录协调器/原生CPU、RSS、线程、可得句柄与磁盘I/O；首个/新进程CPU无前计数写null及原因，不能拿已知部分冒充总CPU。退出PID列入明确exclusion，当前FPS也排除退出PID。没有每进程网络包计数钩子，因此packet_rate=null且有原因；I/O写字节、请求完成率均不称物理发包率。云端指标与本机生成器分列，实际启动时刻和单调观察窗启动率保留。

T01先用真实物理RAM记录，再在12秒后监控读数接缝注入2GiB-1；真实RAM一直高于2GiB，未分配内存制造压力。原安全门在第二组已计划但其客户端尚未启动时停止，实际只启动1人，停止明确为generator_memory_low_before_launch，不能归因服务容量。原生正常清理。

T02真实客户端完成登录/排队后，仅给这个确切PID/epoch的客户端写独立STOP，协调器继续运行。生产workload_snapshot实际观察online/alive1→0；之后两次实际协调器采样为0，exitedPID明列，FPS集合为空。使用原生正常业务退出/exit0，无强杀、更无其他PID操作；不是伪造process对象。

T03各一人，24秒观察：原无覆盖声明Engine.max_fps0，实测3799过程帧/26204ms≈144.978；显式--max-fps60，Engine.max_fps60，实测1540/25638ms≈60.067。来自[Godot实际过程帧计数](https://docs.godotengine.org/en/stable/classes/class_engine.html#class-engine-method-get-process-frames)及本进程Time.get_ticks_msec，headless不是渲染FPS。启动参数本身不当实测。两次源字节/其他contract一致，只有client_max_fps和fps_scope不同；CLI现生成完整contract/sourcehash的独立合格workload_profile_id，原family标签保留，60候选与原输入ID不同，当前性能比较DiagnosticOnly。观察到的CPU不同不作性能收益推断，正式默认帧配置不改。

128项本地回归通过，覆盖实际main终局、时钟修复及8项新资源/身份规则。首轮新测试sys.path遗漏导致加载错误、8项尚未运行，保留工具观测记录，修正测试路径后再通过；不是游戏错误。采样只加元数据/真实计量，不改出牌策略、抽牌、控制或任何游戏规则。

4个账号SQL只读确认0活动归属/0holds/0锁装备、4准备/4票据，无成员或结算，新客户端都在入房前受控收尾，0正常周期。所有客户端/协调器/bridge终止，无引擎错误或强退。云盘约14.26%，goal5%运行余量满足，旧15%容量红线仍保留、不宣称通过。真实物理内存与故障注入读数分开，FPS只代表过程帧，暂无物理网络包实测、容量、自然周期、渲染或真人结论。

原始运行/审计/SQL/参数/完整profile定义/逐PID计数/控制源与回归备份G盘。执行的2124源项用已验证原客户端ZIP加1个实际load-driver源差分重建，2123不变项和差分逐SHA/ZIP CRC验证；不重写旧缺失测量，也不复制用户session目录到公开报告。Git仅摘要/派生证据，全局门禁不变。
