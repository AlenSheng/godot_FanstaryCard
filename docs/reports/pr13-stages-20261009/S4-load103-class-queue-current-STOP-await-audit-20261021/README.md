# 职业保存和排队等待中断通过；完整等待点验收保留两个当前边界

按用户“仅使用当前云主机，资源不足项保留未通过”继续。本轮只在现有云主机的临时独立Program/PG运行两个未包裹原主程序，各启动一个当前Native。共新增2账号、0数据库对局、0完成周期；原业务及容量门槛未放宽。本地只有无窗口、Dummy音频、低优先级的解析校验，没有窗口、登录、数据库或对局。

职业保存真实PUT /api/v1/players/me已经在服务端返回200（136字节），代理暂停交付并写外部STOP，客户端13ms后读到停止，进入原取消职业选择分支。数据库保留所选Mage枚举2，没有准备/票据/对局。代理1000ms后尝试原样交付，同一trace/请求及响应摘要不变，但客户端已关闭连接，记录owned_peer_closed_before_HTTP_write。Native没有该请求的终态HTTP记录，因此不声称“迟到成功响应被客户端消费”，也不补写成功审计。原stage仍是login，保持真实来源。

排队账号真实进入原250ms等待时票据Queued、无room/activeMatch/settlement；外部STOP在等待开始后3ms写入，Native按单调时钟17ms读到。原收尾读取权威票据，再DELETE204取消同一票据及准备，独立PG只有这一份Cancelled准备/票据，无第二准备、对局/成员/receipt/ACK/在局装备锁。准备快照Mage maximumHp=70符合GDD，不是异常。Native读到STOP早于协调器自身落戳231ms，两种观测时点保持各自含义，不强行对齐。

两个原主程序均130/operator_stopped/passed=false；两个Native均OS0/cancelled/cycles0/errors0/cleanupPassed，无强杀、解析错误、引擎资源泄漏，音频释放各164ms。完整审计分别13和32条，分片字节、身份、序号、高水位及主报告摘要一致。46项独立核对通过。59成员raw（含PG dump）与106文件输入包、2148输入清单、生产器和独立审查脚本封存至G；2148由当前2147加明确私有场景覆盖及一份只读观察脚本组成，未把私有覆盖称为原Root完整文件相同。49个封存包成员不是场次。随后核对所有106包文件和2148输入、owner、unit PID0/inactive及自有容器消失，只移除精确临时云输入；云raw、G、局部源和共享缓存保留。生产容器身份/镜像/启动时间/环境摘要与health200一致。

冻结计划原先期望职业保存也会产生迟到drain HTTP，但实际是原请求被取消、对端已关闭；这是观察预期的限定，原件和冻结计划保留，没有伪造HTTP终态或改业务标准。控制器沿用旧模板的kind和SQL异常文字仍有FourPreRoom/worldcap1等旧标签，实际SQL谓词是matches>=0、players>=2，实际仅class/queue两模式且0对局；报告以执行条件和数据库事实为准。

完整12等待点复核支持当前10点。两个特定边界仍需当前原主程序证据：任何READY发出前的Matched进入、原400ms活动Pve等待内读STOP。旧R12/R11确有对应特定等待证据，但与当前相比_graceful_cleanup、_on_event等函数已变化；当前READY积压/晚入局和MOVE在途测试只能作为补充，不直接替代这两个精确边界。旧成功和整批失败均保留，不把整轮false改为true。下一步仅补这两点，不再重跑已完成的10点；本轮不关闭T03 LIVE/POSTGRES，不授予CAPACITY或整项通过。

88 Accepted /36 Partial /8 Ready、44未整体验收、164个case/profile缺口及所有gate保持。资源不足的容量项依用户决定保留未通过，不申请新主机或扩容；可执行功能验证继续。无UI/资源/数值/协议修改、无Git提交/合并/推送或生产部署。
