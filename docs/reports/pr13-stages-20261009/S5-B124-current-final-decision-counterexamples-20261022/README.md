# B12.4 当前最终裁决反例：8个机器缺层闭合

T01补EXPERIMENT/POSTGRES/RENDER，T02补相同三层，T03补EXPERIMENT/RENDER，原有POSTGRES不重复计数。缺层88→80；100 Accepted、24 Partial、8 Ready、32项未验收不变。B12.4自己的显式缺层已空，但B12.2/B12.3/A10.4等前置未Accepted，整项仍Partial。所有全局门仍NotAccepted，不能把反例分类符合预期写成全项目验收通过。

T01把明确标记的有利候选控制输入交给真实gameplay_review：point=.35、CI[.2,.5]、p=.001、drift0，得到EligibleForMainReview且production_activation=false。这个输入不是测得收益：最近B12.2的18次原生遭遇中9对off/on时长逐对相同，没有观察到时长收益，也没有足够统计样本。本轮实际当前132项状态经过生产gate列表推导，G4仍NotAccepted，未完成项为LOAD-10.4/A10.4。自有PG持久化这份评审请求，并在真实Godot进程存活时重算同一裁决。候选有利输入没有抹去原容量不足。

T02实际验证完整规范132项/396案例，在自有PG表记录一个“声明完整但没有执行行”的独立请求，SQL实查executed=0；真实execution_state返回Queued，原生Godot存活时再次观测Queued。这个范围是本案故意未跑的请求，不是声称全项目测试都没有运行，更不把文档完整当执行通过。

T03在一次性PostgreSQL18.6 schema中通过当前迁移、IdentityRepository和EconomyReconciliationRepository运行。两条声明Gold流水+10/+5且wallet+15，真实SQL先IsHealthy=true/violation0；仅把第二行balance_after增加7后，实际LedgerChainMismatchCount=1、TotalViolationCount=1、IsHealthy=false。当前asset_gate返回Blocked、asset_acceptance=false；原账行、差额和DB dump保留，没有修掉故障来获得通过。房间持久化字节不受该账本注入影响。真人资产和生产玩家均未访问。

三个职业的真实默认合法20张牌组、weapon+1房间经当前Server/Domain/Contracts创建、持久化和恢复，每个房间before/after精确一致。Server dd56dfc4、Domain f91d19f7、Contracts f532671e完整SHA及各自来源保留。当前143份测试运行依赖在云端按递归逐hash核对，并再次对应G盘142份原输入加实际生成Linux apphost，不能用顶层57文件冒充143。当前运行源与历史父包、私有增量分开保管，未声称生产已部署这些未提交源码。

Godot正式下游界面从本轮实际PG恢复投影的Protobuf解码显示，三职业×中英×960×540/1280×720/1920×1080为18个基线，加3次UI存活时评审和真实战斗属性面板打开、accepted回调、关闭，共21张原尺寸无损WebP。照片均为面板关闭后的正式画面，不冒称面板内部截图。RGBA像素逐字节与引擎原始SHA一致，Native0、日志无脚本/解析/泄漏错误。3个图集逐幅审阅，另看4张原尺寸：关键卡牌、文字和按钮无重大遮挡，蓝金风格一致，无需ImageGen重出。隔离投影中原有断线/恢复提示仍有显示，英文图可出现原有中文连接失败toast；本轮不是LIVE握手、完整网络路线或全量本地化验收。三次真实策略裁决分别NotAccepted/Queued/Blocked；面板打开关闭不会改写房间状态。

## 重点：私有失败、采样修订和资源门放宽

最初私有C#探针存在匿名对象缺少new的编译错误，原源码和编译日志保留；修正只涉及探针。首次实际PG作业先创建3个房间，再因测试昵称“Owned ledger counterexample”超出正式2–20字符限制失败。查阅PlayerProfile.NormalizeDisplayName后，仅把私有昵称改成“B124 ledger”，不改产品规则。首轮3个房间原件保留；正式重试新建3个，总6个逻辑房间已在采样修订计划登记，未把失败样本归零。

第二次PG作业被原5%磁盘比例门拦在网络/PG/APP创建前，新增房间0。原失败仍保留。现有主机空闲仍超过3GB，PGDATA和/output分别使用自有512MiB/384MiB tmpfs，因此第三次仅对该功能PG作业把准入改为“空闲字节>3,000,000,000且比例>=4.9%，MemAvailable>500,000,000”；UI使用已记录B12.2相同RAM门。该限制放宽、原观察值和新计划单列，不改容量目标、业务标准、正式评审规则或图像质量；不扩容、不增加主机。资源不足的容量项继续未通过，不能从此门放宽推导容量通过。

原始编译失败、昵称失败、资源门拒绝、最终成功均独立保留。最终PG原生/控制器退出0。UI原生结束后由PID1等待G保管ACK，21原图23,022,780字节压缩流直接存G；45个归档成员全部SHA验证后才写owner/run/GarchiveSHA/GmanifestSHA ACK。修正后的控制器先核对ACK，实际成功确认APP退出0后释放自有RAM，没有复用B12.2原竞态false结果来冒充本次成功。

179项独立原生/PG/来源/像素检查通过，清理前566份原始输出、测试源、计划、构建和生产者文件已G托管。71份云端host元数据和第二次资源拒绝原件亦已保存。随后两次核对四个输入目录的owner、压缩包SHA、plan SHA、所有输入和当前2148源/私有覆盖、143缓存依赖、PID0、无所属容器、无符号链接及生产指纹后，精确移除PG-R1/R2/R3和UI-R1输入目录。实际ACK先保存到G才删除。所有旧cloudraw、原PG/host输出、共享UI缓存和A073父依赖保留；生产镜像、启动时刻、环境摘要和health200不变。

## 当前登记纠正

重执行当前生产gate列表推导发现原登记G0–G5的unfinished沿用旧状态，共26个已经Accepted的过期成员。本次仅用当前132项状态更新unfinished，execution_deferred_tasks及其他门字段原样保留；每个门仍NotAccepted，没有新增任务验收。G4当前未完成只剩LOAD-10.4/A10.4，仍需原容量证据。本轮不提交、push或部署新改动，release仍为86ddee23。GDD v0.70和工作簿固定摘要未变，法师70/牧师80/守卫100及合法80/70仍按真实规则，不做夹血或误报。真人按用户要求排除，本轮actual_human_accepted=false。
