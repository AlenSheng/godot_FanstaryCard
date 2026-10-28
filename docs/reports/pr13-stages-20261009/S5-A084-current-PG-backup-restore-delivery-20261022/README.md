# A08.4 三个交付事实的POSTGRES缺层闭合

本轮T01/T02/T03各补1个POSTGRES层，缺层80→77；100 Accepted、24 Partial、8 Ready、32项未验收和六道全局门不变。A08.4本身显式缺层全部为空，但A08.3/B12.4等前置未Accepted，本项保持Partial。没有把数据库探针成功提升为生产回滚、应用健康、候选收益或全项目验收。

在当前唯一云主机启动自有内部网络与一次性PostgreSQL18.6，PGDATA使用512MiB tmpfs。核对原生143依赖每份SHA，当前Server dd56dfc4/Domain f91d19f7与实际321份当前生产者源逐份一致；测试探针只引用当前程序集，未修改产品实现。真实DatabaseMigrator建表，RoomSnapshotRepository保存三职业默认合法20张牌组、weapon+1房间。实际matches=3、room_snapshots=3、wallets=0、economy_ledger=0、inventory_movements=0，真实EconomyReconciliationRepository健康且violation0。

对这个自有数据库实际执行pg_dump -Fc，保留原始PGDMP备份，使用pg_restore恢复到另一独占数据库qa_a084_restored，两个命令退出0。第二个原生进程从恢复库读取相同3个房间ID，通过BattleRoom.Restore恢复；每份Capture与原件逐字节及SHA完全相同。恢复库的房间数、资产计数和真实SQL对账同原库。总新逻辑房间3，恢复对象3复用原ID，没有增加第二组新房间、真实认证账号或网络对局。70/80/100生命依GDD核对，合法80/70不夹血或误报。

三个交付事实放入明确标记的owned_delivery_journal私有测试表，实际经历同一次dump/restore并SQL读回相等。这个表不是新增产品功能，也没有用只创建数据库容器或私有表本身代替真实房间/资产恢复证据。

T01保存原独占env副本恢复审计的原件SHA、original_env SHA和restored_copy SHA。该历史记录确实对应341字节原env的独占副本恢复，本次只核对并保留该记录，没有再次读取、写入或恢复生产env，也未归档任何env私密字节。真实deployment_claim仍给historical_environment_restoration_recorded=true、current_runtime_health=Unknown、runtime_rollback_verified=false。当前自有PG恢复是另外一个明确实例，不把它反写成当年数据库或生产应用回滚通过。

T02本项交付范围没有应用HTTP健康观测，数据库迁移、pg_dump/restore、房间恢复成功后，真实deployment_claim(current_health_verified=None)仍Unknown，runtime_rollback_verified=false。控制器另外为安全保护观测了生产health200并核对镜像/启动时刻/环境摘要；这个独立安全观测不冒充本项缺失的应用运行验证，Unknown也不表示生产当前故障。

T03实际输入为B12.4后当前132项登记，其中32项未验收；所有task_id/state与原登记SHA一起固定并经数据库恢复后保持。runtime_acceptance=false、production_activation=false，清单非空。本条原规范要求PR Draft，但用户已明确“在本地总结直接合入release，不写草稿”，原始人类交付决议PR13_DELIVERY_DECISION_20261008.json摘要eb8d253d已验证，既有AUDIT层也记录此覆盖。因此使用已授权本地总结/直接release交付规则，不制造或修改一个不存在的Draft PR，不把上传已验收资源视作其余运行项通过。本轮任务自身仍Partial，未把未验收测试草稿推送release。

378项独立检查通过：真实两阶段原生退出0、dump/restore0、三份快照原字节相等、原/恢复SQL计数和健康对账、历史/当前登记/人类决议摘要、321当前源、21运行文件、143缓存G父包身份、GDD与工作簿固定SHA均已核对。40个云端原始成员流入G盘，原压缩归档42,628字节；143份G清理前文件包含原始PGDMP、完整源/构建/运行输出/控制器/计划和历史依赖原件。实际原始快照、统计与退出码没有改写。

本轮资源门沿用已说明的功能PG范围：空闲字节>3,000,000,000、比例>=4.9%、MemAvailable>500,000,000；原保守5%比例线本次预检相差约3.8MB，具体原观察保留在G。该门只适用于有512MiB tmpfs的自有功能恢复测试，容量目标/覆盖率/持时及业务标准没有放宽；不增加主机或扩容，资源不足的容量项仍未通过。本轮未发生原生或数据库测试失败，也未追加重试样本；不能以本轮通过覆盖旧失败。文档发布脚本初版因跨行字符串引号在语法编译检查中失败，发生于任何登记写入之前；原源码保留，修正只涉及文档拼接，未重跑原生测试。

原件G存储核验后，两次核对本轮唯一输入目录的绝对路径、owner、压缩包SHA、plan、全部输入、20探针文件、143缓存文件、单位PID0、无所属容器、无符号链接和生产指纹，再精确移除该目录。原云端PG/host输出、所有旧cloudraw、共享UI缓存和A073父依赖保留。生产health200、容器ID、镜像、启动时刻及环境摘要不变。本地只进行无窗口低优先级.NET编译，Godot启动0；无产品UI/资产/GDD/工作簿改动，无新增UI/LIVE/容量/真人验收，无commit、push或部署。
