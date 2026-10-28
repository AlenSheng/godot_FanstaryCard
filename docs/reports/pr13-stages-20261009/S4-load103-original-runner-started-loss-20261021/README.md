# 开局通知丢失后真实快照恢复：补T01 LIVE，整项仍Partial

当前2147客户端与64475511驱动、8eb真实Program和隔离PG，通过未包裹的tools/gameplay_load_test.py原始入口实际启动4个Godot Native客户端，执行1个functional-cycles周期。代理保留并丢弃4份真实room.started原始二进制，真实room.ready_accepted与room.snapshot逐字节转发，没有伪造房间状态、客户端事件、主程序返回或审计读取结果。原有程序、协议、数值、断言均未修改。

4个Native均实际收到1次ready_accepted、0次started，分别于1318、1319、1318、1325毫秒采用与原始快照sequence、真实UID、match、room一致的完整当前路由，位于15秒票据时限内。随后真实战斗、死亡结算与ACK完成，PG为1个世界、4个玩家／成员、4份已确认receipt、4条对应幂等ACK，无Pending hold。原始主程序返回0，4个Native返回0、业务errors0、cleanup Passed，引擎日志没有脚本错误或退出资源泄漏，音频清理等待160至165毫秒。所有客户端审计分片字节、序号和归属完整，代理最终线程／socket为0，PG dump保留，生产身份、环境hash和health200始终一致。466项独立核对通过。

本轮还真实保留4个开局前快照读取的NOT_IN_ROOM拒绝：每条与Native room.snapshot.read的相同request_id和rejected结果对应，之后由现有有界重试取得正确快照。未把这些实际拒绝重写为成功，也没有为绿灯放宽主程序规则。代理规则会丢弃重复started，本轮实际只观察4份首次started、没有真实replay副本；重复丢弃仅另由本地明确字节向量验证，不能称LIVE重放矩阵已覆盖。本地HTTP echo／字节向量只作工具验证，不算服务端或原生运行证据。

本次新增1实际世界／4身份／4玩家周期，历史LOAD103预算及失败全部保留，不重置LOAD101三玩法世界／12周期与单独SQL夹具、LOAD10238世界／72周期及原保守上界。只用原有auth10／write30／read120／RT30限制，未提升限流；500MB／5percent只是功能运行资源底线，不是容量SLO。4人隔离服务内存1024MiB／CPU1.25，PG384MiB／CPU0.25、临时512MiB数据和64MiB WAL，无host端口。源与原件536成员SHA／CRC封存，完整客户端引用既有G3042中的2145同源文件加当前驱动／普通场景2份覆盖；随后核对102包文件、2147客户端输入、owner、unit PID0／inactive和自有容器消失，精确清理临时云输入。云raw、本地工作代码、共享缓存和G原件保留。

仅补LOAD-10.3-T01的LIVE层级，仍缺T01容量、T02 ACK丢包结合重启的LIVE及容量、T03全阶段STOP的LIVE／POSTGRES／容量。88 Accepted／36 Partial／8 Ready、44未整体验收保持；case/profile缺口166降为165，其他131任务与全局门不变。没有新增本地Godot窗口、输入操作或焦点切换，后续本地校验继续无窗口、Dummy音频和低优先级。没有Git提交／合并／推送或生产部署。
