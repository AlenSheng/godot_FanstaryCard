# A04.3-T01 当前真实保存失败与进程重启恢复通过

关闭一个LIVE缺口，132→131。A04.3保持Partial，仅剩T03 MarkRunning已提交丢结果的LIVE；A04.4仍等待该依赖。累计94 Accepted／29 Partial／9 Ready，38项未整体验收，其他131任务和全部全局gate不变。

实际Program8eb、Godot4.7.2、config49ce及PG18.6，新增一个真实账号、一个匹配世界和一件声明初始装备。初始绑定White／0级／Fire／DrawInterval脚装备只在认证后、准备前种入一次，Native通过原Bootstrap和Mage配装/准备/匹配/READY流程进入，不修改玩法默认发放、生命或服务器规则。

自有PG的room_snapshots BEFORE INSERT OR UPDATE触发器实际抛P0001／QA_A043_SAVE_FAILURE。原Program两次真实Save异常后，PG始终同一个M/room/seed、Launching、snapshot0；只读StartupHook取得实际Program DI RoomRegistry和RoomReadyCoordinator，记录pendingM、房间、玩家路由和ticker，全部房间/路由为0，未提前Running。观察器只读字段和真实锁内快照，没有ghost房、构造替代Registry或人工填业务状态。

核对原Program的完整命令SHA、/runtime工作目录、PID/startticks两次后，仅对该自有子进程SIGKILL，保留真实退出-9。新OS进程同DB/同二进制恢复Launching，再次触发真实保存异常；同M/room/seed、snapshot0和实际Registry/route0保持。重启前后equipment、movement、hold、wallet、material、ledger完全相同：一件装备处于InMatchEquipped，只有Equipped→PreparationLocked→InMatchEquipped两条流水，没有第二次预留或扣资源。

再次核实自有触发器定义后，只DROP精确触发器及其函数，不写业务行。原协调器重试保存唯一快照、注册唯一actor并启动ticker，pendingM清空，实际UID路由指向原room。原Godot Gateway自动重连，同UID/session generation接收新peer的真实权威房间；只有一次actualstarted。公开battle.abandon的实际发送和completed回包同request_id，之后原始完整_run／READY／ACK／cleanup全部通过，Native退出0。

最终PG只有1world／1真实UID／1收据／1唯一ACK。一件装备只新增第三条InMatchEquipped→RelicPile死亡流水，没有恢复装备、重复死亡提交或Pending残留。Native8项、原始检查7项及83项独立核对通过，原始errors为空、完整遥测连续，引擎无脚本/解析错误或资源泄漏。这是声明的退出/结算功能周期，不称自然胜利或容量正常周期。

**上传异常保留。** 首次原stdin上传10054／EOF，云端只有0字节冻结包和遗留接收进程，测试0局。按精确root/owner/命令SHA/startticks/UID两次验证后只停止该接收者。随后每512KiB重建传输并核对完整前缀SHA，8个整块及尾块全部通过；同冻结包完整SHA验证后接续原文件并安装一次，没有重建包或重放actor。staging和原失败记录一起保留到完整G封存后清理。所有实际源码以111包文件、2151输入SHA为准，不用HEAD冒充干净源码。

完整源码/编译器生产器、原HTTP/WS、两个真实Program日志、DI时序、分阶段PG全表及dump、上传断链和分块校验已G94封存；2151输入按父G2100+本轮delta50+原场景补充1逐字节重建。确认unit PID0/inactive、自有容器消失、111/2151 SHA、精确owner/绝对根目录及生产指纹/health200后，仅清理自有临时云输入；云raw、G、本地代码及共享缓存保留。

仅用当前云主机，功能500MB/5percent余量不代替容量SLO，资源不足容量项继续未通过。本地只做无窗口、低优先级、Dummy音频、60FPS解析/工具校验和单worker观察器编译，无GUI/全屏/焦点/输入/真实PG或登录。完整GDD v0.70主卷覆盖v0.69，合法Mage70/Priest80/Guardian100及80/70边界不钳制、不误报；无UI/资源变动或新像素验收，无需ImageGen。没有新Git提交、推送或生产部署。

T03仍需真实Godot LIVE，不能用本次保存失败或已有registry故障替代。下一步参考项目ProcessLifecycleRegistrationFaultTests.cs中已验证的RegistrationCommitProxy，并对照[PostgreSQL18消息格式](https://www.postgresql.org/docs/18/protocol-message-formats.html)和[消息流程](https://www.postgresql.org/docs/18/protocol-flow.html)，获取真实提交后响应丢失及持久状态恢复的原件。本轮不宣称该项通过。
