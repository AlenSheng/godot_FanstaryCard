# 真实 ACK 请求截止超时恢复：LIVE 案例证据已补

补LOAD102-T02当前LIVE支持，整项仍Partial。当前8eb Program、真实PG18.6和四个原生法师执行原_run／expedition／真实结算／ACK，当前Python协调器监督。代理把首个目标ACK真实转给后端，收到200后先由独立宿主查询确认PG收据已确认、幂等记录只有一条，再暂扣全部响应头与响应体。没有伪造200，没有提前关闭连接，也没有修改客户端10秒attempt或30秒logical时限。

原客户端实测第一attempt在10016ms返回timeout/status0；以同logical_request_id／trace／Idempotency-Key／请求体重试，11232ms内收到实际后端重放200。代理第一连接到12515.009ms才关闭，晚于Native timeout，证明这次是真正的请求截止超时，不能与旧peer-close丢回复混为一谈。这测的是10秒单次attempt恢复，未宣称耗尽30秒逻辑请求后还能继续重试。

全轮5次物理后端ACK对应4个逻辑完成和4条唯一持久确认；目标有两次物理请求、一次逻辑成功。目标PG收据及完整幂等记录在第一次提交后、超时重试后逐JSON字段完全相同，acknowledged_at没有再次推进；两份真实protobuf回复逐字节一致，字段1收据ID和字段2时间独立解析，与Native用户／match／cycle及PG记录绑定。四名玩家均Dead且已确认，holds0、无未确认收据、items0；未把空资产方案当作新增实物发奖正例。

238条原始审计连续，四Native退出0且verbose无退出资源警告，代理所有bridge线程／socket归零。原协调器仍实际退出1/incomplete：generic4、fallback4、normal0，符合受控兜底负例，不是四局自然通过。R1的ObjectDB2／资源1告警继续Open，R2/R3干净没有证明其原因或修复，不授整项、全系列、容量或原30自然局通过。

先在本地最小无窗口工程对同一真实Gateway跑过10001ms截止超时：两个物理请求／一个逻辑成功、同键同体，后端为明确受控HTTP夹具，不冒作PG。首个私有GDScript因Variant表达式使用推断bool导致解析失败，原日志保留，补显式bool后才继续；无Root产品改动。所有本地Native均headless／Dummy60／CREATE_NO_WINDOW／BelowNormal，零真实登录／数据库／对局，不抢焦点。

独立审查20个deadline／幂等条件加2209项基础来源与运行条件通过。时间观察器最初Python3.10解析7位小数失败，原源码／错误保留；按准确100ns整数刻度比较wire与缓存响应，二者精确相同，PG列按其1微秒分辨率保存，本次差0.2微秒，不能当作数据损坏。全PG对象前后仍精确相同，原始字节与SUT未改，也没有放宽业务要求。依据：[PostgreSQL 18日期时间类型](https://www.postgresql.org/docs/18/datatype-datetime.html)、[Npgsql时间精度说明](https://www.npgsql.org/doc/types/datetime.html)。

完整原件、PG dump、源／二进制、代理原始5份ACK、源校验及观察器失败共367成员G SHA／CRC，引用父3042全量源码的2148输入而不重复1.50GB资源。随后owner、108包内文件与2148客户端SHA、unit PID0/inactive、自有容器不存在、生产ID／镜像／启动时刻／环境hash与health200均验证后精确清理本轮云源码。云raw、全部本地代码、共享基础缓存和G保留，生产未改。

本轮新增1世界／4玩家周期，专项累计3／20世界、12／80周期；所有旧配额、失败、原9自然局1200/2400秒修订与原30局严格失败保留。资源功能底线5%磁盘／500MB不冒作原容量15%门通过。GDD两全文、合法80/70及基础L盾保持，无玩法／配置／UI资源、Git提交／推送或部署变化。

登记保持88 Accepted、36 Partial、8 Ready、44未验收，case/profile缺口171→170。LOAD102只剩三个CAPACITY显式层级，同时原30自然目标与R1强制退出问题仍不得忽略，整体未通过。

原件：G:\PR13Evidence\load102-actual-ACK-deadline-20261021-r3-originals。
