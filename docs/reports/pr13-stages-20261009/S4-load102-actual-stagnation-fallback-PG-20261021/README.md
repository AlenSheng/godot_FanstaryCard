# 实际停滞兜底的 PG 边界通过；退出资源告警继续阻止 LIVE

仅补LOAD-10.2-T03的POSTGRES支持，整项仍Partial。云端1个真实世界、4名真实法师，原生Godot执行当前完整_run／expedition／准备／排队／READY／命令／ACK，当前真实协调器main监督并生成最终判定。私有场景仅继承原脚本，在实际stagnation分支前把last_effective_ms年龄设为61001ms，随后调用原parent方法；不是等了61秒，也没有伪造房间、收据或替换业务回复。

四名客户端均明确记录一次fixture注入、一次原battle.abandon.fallback、一次同match/cycle的ACK和cycle.completed，240条完整审计序号连续、无丢失。Native均退出0、业务状态清理完成。协调器实际退出1，outcome=incomplete_acceptance，gameplay维度Failed：generic完成4、ACK4、fallback完成4、normal0，正常局要求未通过。这正是负例的预期行为，不能把控制器ok或ACK成功解读为四局自然完成。

实际PG只有1match／4player／4prepare／4非机器人成员，4个独立Dead收据及4个唯一持久ACK均能与Native用户／周期绑定；全部已确认，holds0、无未确认收据，准备／成员均Settled。每份结算items0，未塞金币材料或把空资产方案冒作实物发奖正例。真实PG custom dump在移除自有PG容器前保存。

**完整LIVE仍不通过。** 独立审查发现其中1／4 Native退出时记录“2 ObjectDB instances were leaked”和“1 resources still in use”；OS退出0不等于引擎资源干净。它不否定已完成的PG事务与计数，但本轮只接受数据库业务边界，LIVE仍缺并增加必须解决的退出资源问题。现有证据没有证明这是持续服务端内存泄漏，原因待verbose、零登录／零局退出探针定位。原日志完整保留，不能删除或降级成整轮通过。

2209项独立来源／事件／PG核对通过，其中多数是2143个实际执行客户端文件的SHA核对，不是2209场。完整2147原始客户端输入加私有fixture／scene覆盖共2148份源码资源另有全量manifest；核心父脚本与当前根目录相同。被测当前Python normal guard确实在原协调器执行，未用合成main替代。当前Server为8eb、Contracts256、Domainc825，正式配置包与GDD规则保持，合法80/70及基础L盾未检查成异常。

来源元数据明示局限：直接从当前本地仓库导出现有commit／tree／index，真实Git命令在安装阶段核对HEAD6f与2143 tracked文件，未创建新commit；只复制执行目录，其他未执行路径在Git状态中表现为Deleted，因此不声称干净HEAD。原协调器报告git_commit／git_dirty为null，其捕获器未记具体异常；未改写原字段或猜测原因。随后对相同不可变导出、相同UID1000运行只读Git诊断，HEAD6f和dirty状态实际返回0，完整代码内容SHA另行绑定。没有因此重跑已经完成的匹配。

本地预检第一轮退出0但metadata分支未初始化parent Game变量，parent_process产生SCRIPT_ERROR，按日志拒绝预检并保存原件。修正仅在私有“validate only”分支停用本节点处理，第二次真实headless预检干净后才上传；实际云端分支的parent_ready／运行流程未改。所有本地Godot均headless／Dummy／60fps、CREATE_NO_WINDOW／BelowNormal，不弹窗、不抢焦点。

云端PG256m／CPU.4、Program＋4Godot＋协调器共1024m／CPU1.5，PG network-none，app只共享私有namespace，没有host端口或生产volume。认证10／写30／读120／实时30上限保持，无bypass；仅私有Development的补位延迟从0覆盖为标准30秒，等待四个真实客户端，READY15秒不变。1world／4player的私有SQL预算保护在真实迁移后建立。5%磁盘／500MB内存是功能测试底线，不代表原15%容量门通过。未做渲染、真人或容量验收。

所有原始结果、PG dump、真实完整客户端源码资源、Git导出、二进制及控制器共3042成员、约1.50GB在G全SHA／CRC保管。随后逐owner、102包内文件／2148客户端SHA、unit PID0/inactive、容器不存在及生产身份／镜像／启动时刻／环境摘要与health200校验，精确删除本轮临时输入根。云端raw、本地完整副本与G原件保留，共享基础缓存保留，生产未改。实际新增1／20专项世界、4／80玩家周期，不重置旧自然9局、原30局失败与删失或其他任务配额。

登记仍88 Accepted、36 Partial、8 Ready、44未验收，缺失case/profile从173降为172，仅T03 POSTGRES闭合。T03 LIVE／CAPACITY与T02真实ACK deadline超时仍待；旧连接断开丢回复不冒作deadline耗尽。所有全局门与其他131项保持，整体未通过。

原件：G:\PR13Evidence\load102-current-actual-fallback-PG-20261021-originals。
