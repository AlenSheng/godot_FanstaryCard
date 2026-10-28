# A04.1／A04.2 当前验收通过

MAIN接受A04.1与A04.2，94 Accepted／29 Partial／9 Ready，仍38项未整体验收；缺失case/profile134→132。A04.3保存失败、MarkRunning已提交后丢结果两例仍缺LIVE，A04.4等待该依赖，全部全局gate不变。

A04.1-T02使用当前原始完整入口，前两次ticket GET只在wire URL替换UUID，真实Program返回404原字节，本地原ticket/context保持。随后同鉴权公开DELETE原所属ticket204，第三次原始查询实际Cancelled200，命中ready_ticket_terminal，0READY/0完成。原收尾逻辑还需一次权威ticket GET200Cancelled，再执行幂等取消；所以是三次匹配查询加一次收尾查询，不能把必要清理读取误报为无界重试。

A04.1-T03等待真实匹配和原15秒READY到期。私有Gateway只在实际Matched200 HTTP传输完成后暂停消费者，所有原始JSON值SHA保持；真实ready_removed已通过原Gateway/Store/driver，ticket/prompt为空后才交回原Matched值。driver保留的最早权威deadline使其命中ready_deadline_expired，0READY/0完成、cleanupPassed。没有缩短botfill30秒、延长HTTP10/30秒或修改服务器时钟。消费者gate与传输计时严格区分。

两例原始报告ok=false、原失败守卫及真实OS退出1全部保留，case断言另行全部通过。这是预先声明的拒绝和回收路径，不能改写成正常对局完成或自然胜利。只新增1个匹配世界、2个真实账号、0个Native完成周期和0次ACK。PG第一阶段0world/1UID、最终1world/2UID；没有收据、ACK、Pending hold、装备或流水，所有准备Cancelled，唯一真人match成员Removed。历史Matched ticket和机器人Running世界保留属合法事实，不等于账号占用。

A04.1-T01复用当前8eb的全丢required及重放原件：原Native没有收到任何required，完整原始READY循环完成一局。当前Gateway相对该原件仅新增“同一verified且已accepted的required忽略”分支，其条件在此输入流不可达；移除该新增分支后其余字节与原Gateway17416完全相同，driver READY整函数及其他核心文件保持。没有用旧SHA冒充整文件当前SHA。三例全部profile证据及LOAD-04.4／LOAD-09.2依赖齐全，因此接受A04.1。

A04.2前轮三个当前4609场景的全部profile已齐，R1确认界面1/1→0/1的MAIN失败及R2修复后1/1保持、两次false第三次真实成功、第二局旧started隔离原件保持。本轮核心源码未变，A04.1依赖现已Accepted，因此MAIN接受A04.2，无需重跑其四个历史物理世界。

**执行前纠正和上传中断不隐藏。** 首个夹具把所有ticket读数当匹配查询；查阅原_cancel_waiting_preparation后，在任何SDK/SUT启动前冻结v2，记录三次匹配读与一次清理权威读。两份私有GD和计划以COW更新，原v1安装包及G原件保留，最终108包文件/2151实际输入与G盘v2冻结包逐一相符。SFTP曾10054/EOF中断在3047424字节；复查同目录同前缀SHA、无测试unit/evidence/写入进程后，从该偏移续传同v1包，完整SHA验证后安装一次。没有盲重发任务或增加测试场数。派发摘要中继承的expected_dedicatedNative_actor0=true为未使用旧标签；预注册计划、真实Native启动记录及service断言均明确要求原退出1，摘要原值不改写。

客户端完整遥测连续、原HTTP/WS字节SHA、真实15秒期限、清理Bootstrap、分阶段PG全表及dump、实际启动/退出、源码重建和生产指纹均独立核对。所有原件和生产器完整G封存后，确认unit PID0/inactive、自有容器消失、精确owner/绝对根目录与108/2151 SHA，再只清理自有临时云输入；本地代码、共享缓存、云raw及G保留，生产health200及指纹不变。

完整GDD v0.70主卷覆盖v0.69基础卷，Mage70/Priest80/Guardian100及用户确认80/70合法边界保持，不钳制或误报。本地始终headless/Dummy/60FPS/无窗口/低优先级，无全屏、焦点、输入、真实登录或PG。未改变UI资源或布局、未新增像素渲染，不扩张视觉验收；无需ImageGen。只使用现有云主机，资源不足容量继续未通过，真人体验排除。没有新Git提交、推送或生产部署，全项目尚未完成。
