# A04.3／A04.4 当前验收通过：真实MarkRunning提交后丢响应

MAIN接受A04.3和A04.4。累计96 Accepted／28 Partial／8 Ready，仍36项未整体验收；case/profile缺口131→130。只新增1个物理世界／1真实账号／1件声明初始装备／1次ACK，A04.4复用既有完整证据，不重放或重复计场；其他130任务和全部global gate保持。

本次实际Program8eb和Npgsql连接经自有PG协议代理，正常SQL及全部HTTP/WS原样转发。代理按项目既有RegistrationCommitProxy处理Parse/Query及连接池重置消息，首个MarkRunning实际CommandComplete为UPDATE 1，随后ReadyForQuery为I；这些原回复全部保留且未交给程序。独立直接连接PG，确认同M已Running、一份持久快照、同UID一件装备两次预留移动，同时实际DI注册表存在无ticker的暂存actor、协调器仍pendingM，才关闭唯一被选中的自有PG连接。没有伪造SQL响应、持久状态或客户端字段。

原程序真实收到结果丢失异常后移除暂存actor和路由，pendingM保持。原逻辑重试同匹配得到真实UPDATE 0，随后SELECT返回真实Running原行，恢复新的唯一actor并启动ticker、发送一次started。原actor从未启动ticker；因丢响应而发生的第二次注册是同一匹配的恢复，不是第二个游戏世界或重复扣资源。原二进制、源码及10秒命令超时、HTTP10/30秒、READY15秒、botfill30秒均未修改。

恢复已被Godot实际started确认后，再核对自有Program PID、命令SHA、工作目录与startticks两次并SIGKILL，仅该子进程退出-9。新真实OS进程从同DB的Running checkpoint恢复原M/room/seed。原Godot自动重连、同UID/session generation在新peer接收真实权威快照；重启前后六类资源表完全相同，仍一件InMatchEquipped和两条移动，无第二次预留。

主机证明链完成后才允许原公开battle.abandon；实际发送及completed回包同request_id，原完整_run／READY／ACK／cleanup完成一次。最终恰1world／1真实UID／1收据／1唯一ACK，一件脚装备恰Equipped→PreparationLocked→InMatchEquipped→RelicPile三次移动，无Pending、重复死亡提交或返还装备。Native8项、原程序7项及110项独立复核通过，原errors为空、遥测连续、Native退出0、引擎无脚本/解析错误或泄漏。两个Program进程、旧actor移除与替换、PG UPDATE1/UPDATE0/Running原回复和独立提交证明均有原件。

A04.3的T01真实保存失败及重启已经独立通过；T02实际DI registry冲突原件再核对后适用于当前源码：其required全部早于自身accepted，新增的已确认required忽略分支不可达，其余Gateway字节相同。因此三例所需profile及A04.2依赖齐全，MAIN接受A04.3。A04.4既有三例证据也保持：READY前STOP没有accepted，真实重连场景全丢required，迟到旧M故障针对HTTP和command_rejected而非required，新增分支均不改变被验证路径；STOP回收、重连重放和真实同账号多局隔离的客户端终态及PG/route证据已齐。其A04.3依赖现在通过，故MAIN接受A04.4，不把本轮单局冒充三局。

**传输中断未隐藏或计为测试重跑。** Paramiko分块SFTP在已验证前缀后多次10054/EOF，短SSH追加也断链；所有原校验、失败输出和冻结包保留，云端当时没有unit或actor。复查暂存长度/前缀SHA后，用系统OpenSSH相同密钥和StrictHostKeyChecking续传同文件，退出0且完整冻结SHA相同，才安装112文件／2151输入并唯一启动本次任务。只改变传输方法，没有更换主机、重建包、重放actor或放宽验收条件。

私有隔离PG链路为读取协议显式采用SSL/GSS Disable，不更改生产安全设置；参数定义见[Npgsql官方连接参数](https://www.npgsql.org/doc/connection-string-parameters)，帧与流程依据见[PostgreSQL18消息格式](https://www.postgresql.org/docs/18/protocol-message-formats.html)及[消息流程](https://www.postgresql.org/docs/18/protocol-flow.html)。本地代理单测包含连接池重置的C/Z、首个结果丢弃、快速后续查询、正常二进制透传及三个损坏向量，明确不把这些工具假后端结果当真实PG或玩法证据。

完整原PG帧、HTTP/WS、日志、只读DI时序、PG全表/dump、原完整入口、源码和生产器G131封存；2151输入由父G2100+delta50+原场景补充1逐字节重建。核对unit PID0/inactive、自有容器消失、112/2151 SHA、owner/精确绝对目录、生产指纹和health200后，仅清理自有临时云输入；云raw、本地代码、G和共享缓存保持。

本地全部无窗口、headless/Dummy60/低优先级校验，无GUI/全屏/焦点/输入/真实PG或登录。完整GDD主卷v0.70覆盖v0.69基础卷，合法Mage70/Priest80/Guardian100及80/70边界不钳制、不误报。本轮无产品逻辑、UI、图片资源或新像素验收，无需ImageGen。只用当前云主机；功能500MB/5percent余量不代替容量SLO，资源不足容量继续未通过。真人体验排除，无新Git提交、推送或生产部署，全项目尚未验收完成。
