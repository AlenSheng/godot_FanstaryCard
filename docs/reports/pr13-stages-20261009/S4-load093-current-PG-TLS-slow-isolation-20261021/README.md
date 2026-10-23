# 慢连接隔离当前 PG／TLS 实验验收通过

LOAD-09.3三个案例OFFLINE／POSTGRES／EXPERIMENT共9个支持完整，补六个PG／EXPERIMENT缺口。LOAD-09.2及LOAD-06.3依赖已Accepted。当前Root及Server8eb的NotifyRequired已在同一match内最多并行4人，同时每人await found→required；本轮确认该机制，不修改实现或生产限制。

**实际PG和实际字节。** 云端独立PG18.6新容器／新数据库，经真实DatabaseMigrator、IdentityRepository／Provision、Progression、Preparation、Enqueue及TryCreateMatch建立6个真实match、24名玩家／准备／成员，非只造GUID。没有创建自然PVE房间／启动Ready后RoomActor或伪造容量通过。Kestrel独立loopback TLS监听与ClientWebSocket实际握手，临时自签证书只在这些客户端精确pin，不写系统信任。实际当前RoomReadyCoordinator、ConnectionRegistry、RealtimeConnection、ProtobufCodec及EventStore负责发送／重放；为明确控制连接，此purposebuilt端点手动把实际PG玩家绑定Registry，不冒作Program／HTTP登录／票据鉴权路径。

**配对设计。** 三对轮次按AB、BA、AB交替，A是复制当前完整NotifyRequired方法、唯一将MaxDegreeOfParallelism4→1的隔离串行参考，不是假称旧发布二进制。B调用实际8eb中的当前方法。每次四名实际PG成员，首名慢端在每个真实Socket.SendAsync前注入1200ms，另三人0；各执行两对found／required，序列1–4，随后新建WSS连接实际发送EventStore.ReadAfter的四个原事件。慢端延迟是受控发送阻塞，不是地域RTT／带宽模型；TLS连接与PG准备在计时前完成。配对消息种类、次数、序列与规范化字节长度profile相同，match／room UUID本就各自不同，不能说全负载字节完全相同。

正常三人的首required接收等待，串行参考各轮均值2421.600733／2402.607033／2400.177800 ms；当前并行4为2.720933／0.606600／0.302133 ms，三对差分别−2418.879800／−2402.000433／−2399.875667 ms。当前单个正常端范围0.2773–3.0133 ms，参考范围2400.1462–2421.7262 ms；慢端首required约2401.7–2404.5 ms。实际接收时点表明本受控条件下三个正常端在慢端完成前收到所需通知，不无限等待它。这个明显的机制差异不等于线上收益、正式SLO或统计精度：只有三对、单机loopback、人工固定阻塞；不宣称WAN／并发容量／跨match启动全部解决，尤其没有把本轮found／required结果外推room.started发送性能。

**顺序与重放。** 实际原始96条与新连接重放96条，共192条解密后的WebSocket二进制消息留存base64／SHA／长度／接收时钟。独立按当前proto字段号解析，每个Envelope的type／event_id／sequence与PG match／room payload绑定一致，每名玩家实际found、required、found、required及seq1、2、3、4；新连接重放各字节完全一致，不只是按目录名推断。六个Registry最后0连接，50个实际Socket上下文结束后ownedslots0；这是本轮句柄／队列检查，不声称长稳内存无泄漏。

**保护边界。** 使用真实TLS底层Socket和当前RealtimeConnection，32个pending存在时第33次尝试触发Abort，全部队列结束后_pendingSends实际0。另由实际Codec找到恰16,384字节的事件，实际二进制收到；16,385字节被当前类CloseOutput MessageTooBig（1009），客户端实际看到关闭，SocketSend调用仍仅1，没有超大消息写入。没有为测试扩大32或16KiB业务保护。这两个边界使用真实已匹配PG成员上下文，但不需要另造match。

**失败与环境修正完整保留。** 首轮PG初始化参数--no-locale令数据库非UTF8，现有姓名normalize查询在第一名玩家前返回42601。该轮0 match／0 Socket，native退出139、OOMfalse及完整托管异常、控制器失败和PG转储原样保留，不能记成发送隔离失败或吞成成功。第二轮仅加--encoding=UTF8，驱动DLL及本地验证原件复用不冒称新编译；实际PG转储含CREATE DATABASE ENCODING=UTF8和SET client_encoding=UTF8。两轮私有native过程均计数，首轮未开始的六场不是已完成场景重跑。

回传首轮时，本地Python不支持tar.extractall的filter参数，已下载包SHA通过后改用逐regular file、绝对路径／父目录／目标边界校验提取，没有重新传输或重开实验；旧源码与原因保存。第二轮独立观察器曾错误要求initdb stdout重复UTF8，实际显式encoding时该日志不出现；检查改为权威PG转储中的数据库编码声明，原观察器失败源码／修复依据保留，没有放宽UTF8要求或重跑匹配。本轮代码／性能／顺序标准未放宽。

**配额、隔离、收尾。** 实际总6／20匹配上下文、50／100 Socket上下文、192消息＋33pending尝试＋2大小尝试＝227发送尝试；不等于227局，也不以此宣布容量。R1匹配／Socket均0纳入同一累计，不重置其他任务预算（LOAD09299／100、LOAD063104／200等保持）。本地只有CNO／BelowNormal编译和常量／codec验证，PG0／Socket0／Godot0；所有实际PG／TLS在云端cached SDK10.0.400与PG18镜像的两独立容器，PG网络none、tmpfs256m／内存256m／CPU.5，驱动内存512m／CPU1只共享该私有namespace，没有host端口或生产volume。测试资源5%磁盘／500MB内存底线不冒作原容量15%门通过。

成功R2 native0无OOM，两测试容器移除前保存实际PG custom dump。1147独立检查及13项整项审查通过，R2源码／字节／PG转储／原生与714相关源／配置共885成员G全SHA／CRC；R1完整失败源／数据库146成员也已保存。随后逐owner、sourcehash、unit PID0/inactive、无owned容器及生产fingerprint／health200校验，精确删除两轮临时输入源码根。本地代码、两轮云原件和G档保留，其他项目／生产实例身份、启动时刻、环境hash与健康200未变。当前bounded4继续保留，不新增调度改动，不部署、不推送。

本项不含RENDER，本轮无Godot窗口或新美术资源。GDD两卷固定；生命与护盾等玩法不改，合法80/70及基础L盾没有被重解释或钳制。实验跨2026-10-20／21，输入原件沿启动日命名，最终报告归2026-10-21。

原件：G:\PR13Evidence\load093-current-PG-TLS-slow-isolation-20261021-originals；首轮失败：G:\PR13Evidence\load093-r1-UTF8-startup-failure-20261020-originals。
