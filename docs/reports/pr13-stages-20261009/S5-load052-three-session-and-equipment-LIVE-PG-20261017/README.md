# 跨局状态隔离：同会话三局与带装备 ACK 失败恢复

LOAD-05.2三个规范案例按66项不变量复核通过，补齐三个LIVE、两个POSTGRES缺口。本项实际4个不同match、保守16个玩家房间启动，两个实际测试账号；预先冻结上限6场/24启动、本goal单项300场均保持。第一轮在入局前失败，SQL证明0准备/0票据/0成员/0结算/0ACK，没有把失败预检记成一场。没有产品源码、GDD、协议、配置、HP或UI资源修改，没有放宽业务正确性或执行量标准。

**原轮失败保留。** R1真实登录成功，但原完整_run发起的职业保存PUT /api/v1/players/me被本地测试代理拒绝501，因为夹具只实现GET/POST/DELETE，漏了PUT。原Store.select_class已经有正确的null职业保存逻辑，原hero_class_confirmed=false检查正确反映未保存；不能因此误报产品缺陷。Native113172退出1、第二阶段未启动、全部原日志和零对局SQL保留。R2只给新代理补一行普通PUT原样转发，Godot四个覆盖层、2127个产品输入及所有业务判据逐SHA相同；真实PUT随后到达服务端返回200、原职业确认通过。原失败没有改写为Passed。

T01在实际M1捕获原room.started完整二进制包，同时由原Store._load_settlement发起实际M1结算GET；HTTP传输已经完成、数据原SHA保存，只把消费者返回暂扣。原poll正常取得M1 receipt，原ACK和外层循环完成第一局，再实际进入M2。M2真实主动清退、当前receipt到达后，只在原Probe等待返回处暂缓ACK，保留稳定的真实M2终态。先原样重放M1 started，由序号拒绝；再只抬高外层sequence、原payload不改的M1包，由当前房间关联拒绝。M2 room/receipt、路由、准备/票据、选牌、命令缓存和原Probe active/verified match、ready接受、发送次数及cycle计数均保持，第一种不消费游标，第二种仅消费1个会话序号。原二进制、原payload SHA、抬高后frame SHA、完整前后状态均归档。

随后显式释放未改动的M1实际GET结果，让原始旧_load_settlement消费者在真实M2上下文中继续；原发起session和room/load epoch保留，当前M2完整业务状态及其SHA不变，没有恢复旧room或填入旧receipt。实际源room epoch为2、当前为3，第三局为4：计划文字中1→2是首次/第二次房间的概念性编号估计，登录本身先推进了一次上下文，按真实字段复核，规范并不要求字面序号从1开始。不是据日志数字大小判异常。独立SQL证明当时同账号两场已经真实存在，M1已ACK、M2未ACK，只有一个持久ACK记录，不靠UI清空冒充完成。该HTTP只在传输完成后延迟消费者，不延长原HTTP或服务端业务时限。

T03继续释放M2原ACK，原完整_run随后进入第三局并实际ACK。原始登录、职业确认、三次_run_expedition、外层cycle.completed和cycles_completed递增、最终_graceful_cleanup与原_finish写报告/退出全部实际执行，原主报告ok=true、cycles_completed=3、cleanup=Passed、audit_lost=0；三条原cycle.completed分别位于iso-main:1/2/3，并各自排在同match真实settlement.acknowledged之后。夹具没有覆盖_run或_run_expedition，只在第二局终态_wait和最终_finish调用super之前提供有限等待，最终原_finish仍真正写出主报告并退出0。

三局session_generation始终1，同一原生WebSocket实例，实际room epochs2/3/4。服务端原始started序号8/20/33，客户端观察8/20/34；第三局差1来自第二局明确的外层序号故障接缝，后续真实帧仅外层统一+1以保持连续，原始服务端序号另行完整记录。整个真实原始流递增、客户端游标无重置，没有直接赋值last_sequence或中途重连，没有把注入序号当成服务端新发布。原生socket ObjectID的JSON有带符号64位表示，只按原整数相等验证实例身份，不把它当应为正数的进程PID或异常。原PID103284正常0退出，实际三局均由公共battle.abandon主动清退，是功能周期，不称自然胜负、默认容量或真人体验。

T02用独立第二账号和另一原生进程，避免中断前述三局真实原循环。初始夹具只在该单元专属临时PG中，为全新且装备为空的指定账号创建一件绑定、白色、0级、Fire/DrawInterval的Feet，并更新Mage=2配装。写入前有独立one-shot intent、账号/空装备/空槽/无对局检查，真实写入及后续Bootstrap、装备入局、资产流水都保存。它是声明的隔离初始资产，不是正常掉落、免费礼包、经济收益或历史修复；不修改正式账号/物价/规则。真实角色带该物品入局，再通过合法主动死亡取得实际结算。

原_run_expedition在终态得到receipt后调用原Store ACK，UI清空及pending ID由原实现完成；同一逻辑请求的三次原重试均由代理在后端之前断开，保留原10秒单次/30秒逻辑时限和原退避。真实Bootstrap确认仍未ACK的receipt，原逻辑有限返回失败，原settlement_acknowledged=false检查保留，before/after完整业务状态逐字段相等。非空真实装备身份具体位于恢复的preparation.equipmentIds及snapshot；当前死亡后的room.equipped_items和receipt.items实际为空，不能宣称它们在LIVE中为非空。当前终态queued/pending/latest命令也依法清空，不能为测试向死房间强填活动命令。为覆盖非空缓存事务，另运行明确标注OFFLINE的非空装备展示、选牌顺序、queued/pending请求及重试/成功清理夹具，实际原Store六项检查通过且引擎干净；这不是有效LIVE死房间的声称。

查阅协议文档§13.2后按真实资产状态裁决：装备死亡时已经经Equipped→PreparationLocked→InMatchEquipped→RelicPile三条流水，ACK失败前后及实际公共重试后始终在RelicPile，流水各只有一次。失败ACK恢复客户端结算上下文，不是撤销死亡或把掉落装备补回身上。失败前后独立PG的装备、流水、准备、票据、成员、结算和幂等记录均相同，ACK0且acknowledged_at空；公共重试实际200后只增加一个唯一ACK，资产状态和流水仍相同。合法状态按文档解释，牧师80/70允许边界也保持，未触碰HP判断或显示。

R2实际两个原生进程103284和83048正常退出0，原生/服务端引擎无错误、无强杀、专属通道关闭。完整PG最终两个真实账号分别3和1个Settled准备/成员/结算，4个历史Matched票据合法、4个receipt均已ACK；4个成功wire请求ID与4条持久幂等记录一一对应，失败逻辑请求ID没有出现在成功记录中，无资产锁或待处理holds。第一轮零对局失败与第二轮4场合计仍4场，保守16启动。

两轮专属完整Program512MiB/1CPU、PG384MiB/.4CPU、256MiB临时数据库/max_connections25，均使用无主机映射端口的内部网络。Auth/写/读余量100/200/500及关闭OTel出口仅在隔离实例，生产容器身份/镜像/启动时间/环境SHA和健康200保持。四个专属容器、两个网络和两份私密env均已删除并独立复查；夹具资产随临时数据库结束，不复制到生产。默认READY15秒、botfill30秒、HTTP10秒/30秒不变，goal5%资源余量通过，当前磁盘约14.24%，**原容量15%磁盘门仍未通过**。

2127个当前客户端与实际两个G盘硬链接项目及冻结清单逐SHA相同；328个当前服务端源码与21个完整缓存运行文件已资格复核，不重建、上传游戏源码0。52个云原件、两个轮次全部控制/原生日志、原三局完整报告/状态/连续审计、旧started二进制和GET原data、装备种子intent/SQL/检查点/资产流水、离线六项原件均保存在G盘并重校验；当前全量源码及实际完整服务运行库沿用已重新SHA验证的共享原件，不重复生成约1.4GB包，不复制auth userdata/私密env/import缓存。

本次只关闭LOAD-05.2五个缺失profile，54→55 Accepted、78→77未验收、68→67 Partial、10 Ready不变；其他任务和六个全局门不自动提升。下一项LOAD-05.3须验证各await取消，不能用这三局ACK成功替代STOP、写结果未知或Pending holds等独立故障条件。
