# T02 完整协调器审计故障链路：补LIVE与POSTGRES，整项仍Partial

以当前完整2147客户端、64475511退出驱动、8eb真实Program、49ce配置和独立PG执行三组实际协调器main，每组4个真实法师身份、每号一个functional-cycle。三组真实main依次返回0、3、3；正常对照Passed，两种损坏数据的底层运行保持invalid_workload_or_evidence且未通过。负例按预期被拒绝才是本案例观察通过，不把失败运行改成绿色。

注入点明确为原始main最终调用read_audit_events时的私有数据回调：先核对4个真实Popen子进程均退出0、Native终态1周期／errors0／cleanupPassed，保存完整原审计备份；随后仅在本轮可写输出上原子删除一条battle.observed，或把其event_type字符串改为数组。schema场景使用合法JSON尾空白保持精确字节数，其他语义字段、行数与序号不变。然后原始archive reader、cutoff/schema分析、结果维度和main返回继续执行。没有替换统计结果、健康状态、进程对象或计数函数返回；实际入口是明示的数据注入包装器调用原main，不能写成完全未包装的脚本命令，也不是网络丢包测试。

丢事件场景由真实原读取器报告event_sequence_gap_or_reorder及存储／数量损失；schema场景没有归档分帧错误，由原完整main报告invalid_event_type并返回3。因此失败分别源自实际文件丢失与schema校验，没有依靠组件helper或只按目录名推断。

12个Native全部真实登录、准备、入队／READY、战斗／合法终态、结算确认并退出0，业务errors0、cleanupPassed、无音频退出告警。每组结束后由独立宿主查询PG，核对4个新增UID、1个新增世界、4条已确认收据和4条唯一持久ACK，再释放下一组；最终12身份、3世界、12收据／ACK，无Pending hold，PG dump保存。functional-cycles可在胜利后脚本弃战，分类如实保留，不冒作自然通关、容量或完整路线样本。

独立审查3356项实际原始事件、UID、报告、备份／变异字节、PG及当前main／reader／统计源hash条件通过，另一个唯一输出路径检查未计入该持久数字。最初封存脚本误把打印总数3357与持久审查数3356混用，封存前断言拦住后按实际记录修正，没有改运行结果或重启测试。本地预检确实使用复制旧审计、派生1周期资格和fake-poll对象，只验证注入工具，原件明确标注，不作为LIVE／PG证据。

337成员G SHA／CRC封存源码、二进制、原始输出、修改前全备份、PG dump及本地预检；完整2147输入通过父全源2145个相同文件和当前驱动／原始普通场景2个精确覆盖关联，不重复1.5GB媒体。随后owner、101包文件／2147客户端SHA、unit PID0/inactive、自有容器不存在、生产身份／环境hash与health200一致后精确清理临时源码。云raw、本地代码、共享缓存和G保留。

仅临时SUT使用HTTP Auth30／Write120／Read480以容纳12身份连续三组的同IP功能请求，RT30与bypass=false；应用1024MiB／1.25CPU、PG384MiB／0.25CPU、无host端口和生产volume。500MB／5%功能底线不授容量门。源码、断言、schema、玩法／血量／数值、UI、生产、Git均未改。本地没有新增Godot、登录、PG或对局；此前无感运行约定继续保持。

本次新增3世界／12玩家周期，LOAD101此前协议0世界4身份以及所有其他旧预算保留；单项不超几百局。只补LOAD-10.1-T02的LIVE／POSTGRES两个缺口，不能覆盖T03关键环境跳过、T01／T02／T03容量或全部CI。88 Accepted／36 Partial／8 Ready、44未整体验收保持，case/profile缺口170降至168，LOAD101余5项，其他131任务及全局门不变。
