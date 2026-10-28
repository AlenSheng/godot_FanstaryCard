# A03.2：当前旧局和旧账号回调隔离验收通过

MAIN接受PR13-A03.2三例，关闭各LIVE/POSTGRES共6个缺口。90 Accepted／34 Partial／8 Ready，42未整体验收，case/profile缺口156→150；其他131任务及所有全局gate保持。A03.1依赖已Accepted，A03.3的ACK未知和A03.4同账号三局仍各自待验，不能用本项2个A房间+1个B房间替代同账号三局。

当前完整Root GameStore/Gateway/codec业务逻辑未修改。私有Store仅在原_ready构造器选择继承的Gateway，并在声明的真实M错误到达时暂停原_on_event消费者；私有Gateway始终先await原request，实际传输与解码完成后才延迟原成功返回值。四份私有脚本/场景和明确autoload覆盖、2151输入及原SUT五文件SHA均固定，未直接赋room、receipt、recoveryID、epoch、游标或认证UID。原error payload和成功值JSON SHA前后一致，服务器包及sequence均未改。

R2一个真实Native进程完成M、N、B三个不同match，两个实际账号。M/N同一A UID、同一generation1和同一原生socket实例，实际room epochs2→3；socket实例ID为带符号64位opaque数，按原值相等判断，不因负值误报。M的真实NOT_IN_ROOM在Gateway正常处理后，原Store消费者暂停，N已真实终态时再调用原父消费者，N完整业务字典及原生指纹保持。

M结算详情实际传输50ms、Bootstrap253ms；原成功返回值分别暂停36260ms、35337ms，均在真实N epoch3/gen1下原样交回。HTTP10秒单次/30秒逻辑时限未延长，报告明确35–36秒是传输结束后的测试消费者等待，不称原HTTP总耗时小于30秒。M正常收据通过独立权威ready-only返回恢复；若该返回先于详情捕获，仅以<=5秒私有返回门保证实际详情GET发生，不伪造收据或状态。

随后取得实际A的N Bootstrap，传输282ms，暂停35730ms。公开ACK N后真实logout/login B，B拥有不同UID、generation3、新socket和epoch6，公开选择Priest并实际入房/结算；旧A成功DTO确实含A UID/Mage和N收据，返回到B后B完整业务状态、Priest及其receipt保持，公开ACK B成功。实际房间ID均唯一；同ID M-N-M和旧session同ID反例由同源当前OFFLINE另行验证，不假造真实账号共用相同房间ID。

三份旧HTTP返回前后、旧错误调用前后都逐字段比较N/B完整业务、receipt、路由/revision、恢复和pending归属。七个Native→宿主PG握手分别确认world/UID/receipt/ACK为1/1/1/1、2/1/2/1、2/1/2/1、2/1/2/2、3/2/3/2、3/2/3/2、3/2/3/3；旧回调窗口钱包/材料/ledger/收据/ACK数据保持。最终3个不同收据、3条唯一ACK，A两次/B一次，装备/流水/holds均0；这是明确零物品范围，不宣称非零资产转移、自然胜利、容量或真人。

原Gateway在M错误消费者被测试门暂停时发出的唯一声明诊断原样记录；没有提前写_retry_handled伪装原消费者已执行。真实额外预入局只读NOT_IN_ROOM按requestID、M/room和started前时序逐个核验，未知额外报文不放行。Native59检查全过、OS0、无意外Gateway失败/脚本/解析/资源泄漏，77项独立原件核对通过；完整Native遥测及二进制报文源保持。

**R1原整轮Failed保留。** 首轮只产生1世界/1账号/1收据/0ACK，未执行N/B。测试先暂停Store错误消费者，Gateway已清路由；公开abandon确已完成，终态快照因expectedroom空而被原prior-room保护正确拒绝，Store仍显示旧Pve，明细回调又被扣留且没有公开ready-only重查，25秒内没有收据进入Store。旧70/70画面不被当作HP异常，不为夹具时序改路由保护。R2仅调整私有actor：先建立正常终态并调用原公开retry，随后再延迟旧M错误；失败清理仅释放测试门。Store/Gateway/proxy、HTTP10/30、READY15、botfill30及全部状态不变量保持。

在R2上传前冻结专项累计世界上限3→4：R1实际1 + 本轮必须完整3 = 累计4世界/3真实账号/4收据/3ACK，初始物品0，旧失败和所有跨项历史不重置。原3场计划与预算修订均保留，仍在用户单项几百场范围内，不称原标准整轮通过。

89成员raw、PGdump、109包文件、2151输入和生产器完成G盘SHA/CRC封存。输入由父完整G2100份+当前delta50份+既有原场景补充1份实际重建，旧父该路径的fallback私有覆盖不冒充相同文件。确认owner、109/2151逐SHA、unit PID0/inactive、自有容器消失、生产指纹/health200不变后，只删除精确临时云输入；本地代码、云raw、G和共享缓存保持。

本机仅headless/Dummy/60FPS/CNO/BelowNormal解析校验，没有本地登录/对局/PG/窗口/输入。GDD完整v0.70主卷及v0.69基础卷固定，合法70/80/100及80/70边界按文档处理。未改UI资源、无需ImageGen，没有新Git提交/推送或生产部署；先前release86ddee23正式资源推送仍独立完成。继续其他未验收项，当前主机资源不足容量项保持未通过，真人体验排除。
