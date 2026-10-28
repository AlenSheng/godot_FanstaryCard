# READY接受后无started的当前真实入局验证

LOAD-04.3-T02本轮仅新增1个本地功能局，复用1个既有测试账号，正常补位3机器人。实际当前Runner原_run、_run_expedition和_graceful_cleanup不改；夹具只选既有账号、调用super的观察和音频收尾。当前Server245265ff、Domain57ba955a，60客户端输入和328服务端输入前后字节一致。

实际room.ready_accepted序号4正常交付，全部room.started及重放按中继策略丢弃；本轮实际出现1份started序号5。当前Gateway在accepted后约250ms自行发送1次真实空载荷room.snapshot.read，原上限仍3次，实际服务端返回同requestID的原始snapshot序号6。未生成或修改服务端业务载荷。独立解析11份原始Protobuf包、逐包SHA/交付摘要、真实Game/Gateway及PG的同match/room共同确认Running/Active入局；真实Native的started计数为0，snapshot计数为1。全局序列从正数继续前进，没有清成0。

指定功能边界在独立入局证明后STOP，原报告保持ok=false/outcome=cancelled、退出0、自然周期0；cleanup权威Passed，最终12玩家不变、9→10局、36→37结算及37ACK，Pending/装备锁均0，新增局Completed且无未终结成员。原Runner实际执行5项检查均通过；STOP发生在它的room_started布尔检查前，不冒充该第6项已执行，以独立原始包/SQL/观察证明入局。

**额外故障与标签范围明确保留：**“只允许snapshot.read请求关联快照”的中继策略在入局后还丢掉1个实际battle.abandon请求关联的snapshot。原事件桶名称unsolicited过宽，该包并非无请求快照；独立requestID核对后分列为abandon响应，不改原件。额外丢包下cleanup仍通过，不用于默认路径、时延或容量推断。

独立复核共52项断言通过，Native峰值约113MB，磁盘/内存采样均保持5%余量；Native/API/监督器/PG四个自有PID均消失，Proxy线程/连接关闭，API退出0、PG正常停止，无强制结束。无新账号、云端调用、UI资源或产品代码改动。既有S7公网required丢失报告与LOAD-04.3-T01场景相符，保留其69f67947历史执行入口，不重跑、不改称当前版本；T03旧match snapshot与旧started不是同一输入，继续单独核查。

本报告只建议本例当前本地真实运行/PG的限定支持，不涵盖WAN、容量、整组LOAD-04.3、RENDER或真人体验。原702项状态/内容、132任务/396案例及77项未验收保持，register/gate/MAIN未改；GDDv0.70及牧师神器合法80/70原始边界保持，整体验收未完成。
