# 当前协议双进程与实际 Program／PG 联测：仅补 T01 两个层级

LOAD-10.1仍为Partial。当前仅关闭T01的LIVE／POSTGRES两个缺口：4个真实PG身份，当前Program HTTP protobuf登录／bootstrap／一次性票据和真实WebSocket路由，16条命令、20条服务端事件，数据库转储身份与HTTP／WS原件逐项一致。没有创建match、自然玩法房间或宣称容量通过。T02与T03取得了新的组件证据，但实际runner整链路的PG／LIVE／CAPACITY支持仍缺；最终保留7个案例／层级缺口，未把私有控制层fixture升级成完整运行层。

本地使用独立手写二进制向量，不通过被测编码器生成输入。44条正常／边界向量包括未知127字段的varint／fixed64／bytes／fixed32、optional缺省／显式零、int64极值、空RoomReadyCommand未知字段和HTTP可选空字符串；6条负例覆盖截断、非法tag／wire及溢出。当前Contracts256的Google生成解析器与手写服务器codec实际执行，Godot实际读取服务器输出，再由C#读取Godot真实输出；保留字段语义与presence一致。Google生成物保留未知字段，Godot作为语义终端重编码时丢弃未知字段；本项没有宣称透明转发未知字段。旧怪物literal wire仍在140 HP、缺省phase时按phase1处理，不按血量推断阶段，也不冒作旧客户端二进制运行。

最初观察器误把所有解析器对十字节溢出的行为视为相同，发生真实失败。锁定Google.Protobuf3.33.0源码的ParseRawVarint32会丢弃高位，因此生成解析器实际返回protocol_version0，当前应用codec和Godot仍严格拒绝同一输入。只修正跨库观察预期，原负例字节、产品代码及既有测试断言未改，失败源／退出码完整保留。依据：[锁定版本官方源码](https://github.com/protocolbuffers/protobuf/blob/v33.0/csharp/src/Google.Protobuf/ParsingPrimitives.cs)。错误版本2另由实际应用拒绝，不能把schema单独可解析解释为业务有效。

当前14条统计／进程反例零跳过，通过畸形状态、错误HTTP状态／duration、所有权、同毫秒丢事件、phase／旧steady口径、online与active区别、逻辑请求／attempt／取消分母、真实退出7子进程和跳过拒绝。子进程已回收。64个功能案例是44＋6＋14，不把1309条内部断言当1309局；本轮没有任何新自然对局。小型功能套件保持完整，没有为缩量删除反例。

云端实际当前8eb Program经真实HTTP protobuf处理两组带未知字段／两组普通登录与ticket空请求，四个用户的profile／bootstrap与PG转储身份相符。真实一次性票据连接WS，每人收到session.connected、pong、pong、error.invalid_message、pong，序号1–5连续；发送端含expected_revision缺省、显式零及确实存在的未知127字段。错误版本响应后正常ping继续可用。独立解析20条服务端二进制、16条命令的字段／SHA／ID／时间，不是按目录名推断。所有access／ticket只在内存中使用，不保存登录响应或带ticket的URI。此处是loopback WS，不是TLS/WAN、自然完整路线或并发容量。

T02的新反例以这20条真实消息为来源，明确构造派生遥测副本：逐用户删除seq3或把event type设为数组。12个实际Python进程调用当前new_events／aggregate_window／classify_stop，四个正常对照退出0、四个缺事件退出3且lost1、四个坏schema退出3。原始事件没有删改。这是实际wire驱动的组件桥接测试，不是实际Godot发压器丢文件／丢网络包，也没启动完整runner协调器。因此不关闭T02的PG／LIVE／CAPACITY。

T03先在有实际Program／PG的首轮尝试原生关键方法，但Windows构建包只有Windows apphost，Linux VSTest适配器要求无扩展名host而失败，原生子进程退出1、0测试发现；driver随后139、OOMfalse。协议部分已经完成，但整轮仍记失败。随后只用同一不可变DLL的直接dotnet原生入口补跑关键方法，命令选项先经隐藏的本地help验证（help退出2且未执行测试）；支持方式见[xUnit官方迁移说明](https://xunit.net/docs/getting-started/v3/migration)。没有重跑四个正常账号。新原生TRX为1NotExecuted、0Passed、退出0；当前assess_trx为Blocked、require_unskipped拒绝导出、assess_gate仍Blocked。负例观察通过不等于底层PG方法通过，也不自动填满T03的实际runner层级。

两处证据工具局限明示保留。首轮Program stdout仅8192字节，异常退出前私有捕获stream未dispose导致尾部buffer未落盘，末行不完整；没有补造或称完整日志。权威wire、metrics、PG dump和已写出的失败对象仍可独立核对。最初导出仅遍历顶层27文件，漏掉nested零测试TRX；从同一已终止环境递归导出29文件后完整保存，原顶层包也保留，没有重启实验。补跑控制器还出现一次Windows CRLF写盘与LF hash不一致，G校验在SSH前拦住；原字节保留后改为精确write_bytes，未产生重复云端动作或放宽业务标准。

本地Godot为headless／Dummy／60fps、CREATE_NO_WINDOW及BelowNormal；实际显示后端为headless。其他私有编译／Python子进程同为无窗口低优先级，本地PG／登录／游戏0，不抢焦点。云端使用cached SDK／PG，PG内存256m／CPU.5，Program与驱动合计容器512m／CPU1、仅共享私有network-none namespace；补跑只有384m／CPU.5的独立network-none原生test容器，另一个64m只读pg_restore工具只读旧dump、不创建数据库。无host端口或生产volume，业务限额／schema／配置未修改。5%磁盘与500MB内存为功能实验底线，不作为容量门通过。

155项实际Program／PG独立核对、189项本地协议审查通过。程序／PG／wire／原生Skip／失败与源码共1313成员（714相关源／配置），本地协议另853成员全部G SHA／CRC后，两个临时输入源码根按owner、181文件SHA、unit PID0/inactive、容器不存在与生产fingerprint／health200校验精确删除。云端raw、本地代码、PG dump和G保留。最初私有评审曾拟补六个支持，最终因范围不足在公开前否决，旧提案仍在G，final-scoped-review优先。

现有CI的client/tests等新增产品测试路径已有过滤覆盖；本轮私有验收fixture尚未安装进CI，不声称当前完整CI通过。GDD两全文、合法80/70与基础L盾、所有历史预算保持。无产品、UI资源、Git提交／推送／部署或生产变更。

登记保持88 Accepted／36 Partial／8 Ready，44项未验收，case/profile缺口175→173。只T01两层级变化；其他131项和所有全局门不变，整体未通过。

原件：G:\PR13Evidence\load101-current-Program-PG-and-skip-20261021-originals；本地协议：G:\PR13Evidence\load101-current-independent-protocol-20261021-originals。
