# 当前匹配状态机：真实云端与 PostgreSQL 验收

LOAD-04.1三案完成当前LIVE/POSTGRES补测与MAIN复核。实际4个自动账号、两次真实四客户端组队，加一次默认机器人补位/READY超时，共3个真实match、保守12个玩家房间启动，低于预先6房间/40启动及本goal300上限。两局在room.started边界停止，由真实battle.abandon与结算ACK清退，8次退出/8个ACK，**不称为自然完整对局、容量、强弱或真人体验**。

T01使用原生客户端、真实完整Program服务及独立PG。唯一接缝是短暂扣住主账号实际enqueue HTTP202响应，WebSocket仍为不解析不改字节的通道。实际match.found/ready_required先到、prompt非空，此时ticket/room/gateway路由仍空、预启动验证为false、READY发送为0。扣住期间独立SQL按owner/preparation/ticket实际关联到Starting match和Assigned非机器人成员，match/room与提示精确一致。随后显式释放完全相同202原响应体（SHA一致、5.281秒，原HTTP10秒不变），执行真实GET ticket、每局主账号READY实际成功1次，再接收服务端启动。真实排队取消也通过，SQL票据/准备为Cancelled。

T02从真实第一局捕获原始room.started报文，在真实第二局消费者注入两种可审计故障：原帧直接重放由序号拒绝；仅抬高外层sequence、原始payload字节与SHA不变的第一局帧，由当前房间关联拒绝。两个reason均记录，第二局完整Room状态哈希、当前路由、玩法探针不变，第二种仅消费会话游标。为了保持之后原始流连续，后续13个真实帧只抬高外层sequence1；未改玩法payload或直接赋值房间。这是明确的消费者故障接缝，**不是声称服务端重新发布旧回调**。LiveStore只替换Gateway构造工厂并关闭本夹具持久化，其余ready连接/刷新逻辑与当前原实现相同；原project.godot全部autoload保留，没有排除deployment-info等hook。

T03在生产Gateway实际socket.put_packet成功后观察8次READY的同一encoded buffer：payload字节0、命令字段0、无私塞match/room头，逐次SHA和request_id对应真实room.ready_accepted；4客户端两局的8个room.started均匹配实际match。当前序列化/命令映射不变，原官方RoomReadyCommand定义为空。当前追加的生产代码仅3处trace诊断：成功READY编码观察、有限控制事件重复序号拒绝原因、旧房间关联拒绝原因；不改变既有守卫、游标、重试、路由或序列化，未改服务端、proto、配置、HP或资源。trace不进入metrics标签，不记录令牌或报文正文。

默认botfill30秒和READY15秒保持。第三次主账号不发READY，真实ready_removed使准备Cancelled、成员Removed，本地ticket/准备/房间清空；独立PG四账号均无活动准备/成员、资产锁0、待处理扣留0，各有2个结算与2个ACK。PG schema只有Queued/Cancelled/Matched，超时历史ticket仍Matched、机器人match仍Running是合法状态；此时测试账号已Removed，不冒充Expired、不报占用泄漏。项目文档/GDD及用户允许的牧师80/70边界均未改。

当前2124客户端文件与实际运行副本逐SHA相同，328服务端源码按原缓存清单与当前实现资格复核，实际21运行库逐SHA冻结，运行原完整Program缓存DLL，未重建、未以stub替代，上传游戏源字节0。测试环境在内部私有网络，服务512MiB/1CPU，PG384MiB/.4CPU与256MiB临时数据库，max_connections25，不映射主机端口。Auth/写/读限额100/200/500仅为此隔离功能测试临时余量；OTel出口仅在隔离实例关闭，生产服务ID/镜像/启动时间/环境摘要与健康200持续不变。结束后两个本次容器、网络和私密env均已删除，二次只读复查清理完成，原生PID正常结束、隧道关闭。

**限制和失败原样披露。** 当前按既有goal5%磁盘/内存余量执行，实测磁盘约14.19%，旧容量15%磁盘门仍未通过；功能结果不能升级默认限制容量。四组有针对性的回归全部通过。R1旧测试误把所有telemetry都当请求耗时计量而出现1失败，修正为按type分别检查一次cancelled计量及独立guard trace，原请求唯一计量/状态守卫断言保留，新加分离检查，R1失败保留。原件下载R1在远程进程退出后未读完stdout，留下1376256字节不完整gzip并触发EOFError；R2读到流EOF，328源码+21运行库全部SHA通过，没有再次启动游戏或云测试。两种失败都未改写为通过，未放宽玩法、关联、空协议或超时正确性判据。

全部云原件24项、完整源码/实际运行库、两种旧包故障、HTTP扣放/原体SHA、独立SQL、回归R1/R2、所有日志及当前源码原字节保存在G盘并重新校验。未复制auth userdata或私密env。MAIN独立复核48项不变量，父表48Accepted/84未验收到49Accepted/83未验收，只关闭本项4个缺失profile；六个全局门和其他任务保持。下一项LOAD-06.2按其独立三案执行，不能用本轮匹配成功自动通过玩法停滞判断。
