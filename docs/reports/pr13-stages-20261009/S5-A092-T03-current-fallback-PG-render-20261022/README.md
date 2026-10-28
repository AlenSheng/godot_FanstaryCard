# A09.2-T03 自动弃战负例：POSTGRES / RENDER闭合

本轮仅补T03的POSTGRES/RENDER两层，68→66。旧LIVE实际Guardian截尾及弃战清理样本原样保留，不重复计数、不把它的UID与新DB样本混为一谈。100 Accepted、24 Partial、8 Ready、32未验收和六道全局门不变。A09.2保持Partial：T01第二局旧事件、T02十账号30周期中一局Unknown仍各缺LIVE/POSTGRES/RENDER，共六层；三职业正常三局和十号30周期未通过，不用本轮负例替代。

现有唯一云主机上，一次性PostgreSQL18.6依次创建三个独占schema。使用当前DatabaseMigrator、IdentityRepository、BattleRoom和RoomSnapshotRepository，三职业各一个合法默认20张牌、weapon0的PVE起始快照。玩家profile职业是明确fixture输入；未赋予起始护甲或带入背包物品，不能据此声称五部位掉落全覆盖。真实matches/match_players/room_snapshots关联同一自有账号与房间。分别启动当前完整Program，Godot通过真实本地认证、PB HTTP/WS恢复真实持久PVE，不是只把JSON贴到界面。

原client/tests/gameplay_load_client.gd字节不变，私有节点直接实例化其原方法，未重写_try_stagnation_fallback。先设置本节点last_effective_ms为当前ticks，实际不弃战；随后只把本节点的进度时钟输入设成stale61001毫秒，触发原60秒条件并实际发送公共battle.abandon。这个输入是受控时钟故障，不是声称自然等过60秒或复现完整自然停滞，也未更改游戏HP、怪物、时钟或60秒源码。

三职业均在敌人仍活着的真实PVE画面后弃战，得到同match死亡结算并实际ACK返回大厅。当前reconcile_cycles读取真实fallback/ACK事件，逐个导出fallback_cycles=1、acknowledgements=1、completed_cycles=0、normal_completed_cycles=0，evidence_errors空。没有伪造cycle.completed，没有把脚本清理/弃战当成正常击杀或完整周期。原始公开Guardian失败1200秒样本仍独立保留。

实际PG中，三人各只有同match/UID的一份Dead结算，acknowledged_at非空，Pending holds=0、锁定装备=0，当前EconomyReconciliationRepository健康、violation0；最终房间快照、死亡结算/详情和完整DB dump均保管。三职业最大HP按70/80/100核对，截图受真实PVE伤害后出现67/70、77/80、94/100均正常；合法80/70不夹血或误报。

每职业1张真实PVE前图、死亡结算中英三尺寸6图、ACK后大厅中英三尺寸6图，共39张完整尺寸无损WebP。每张解码RGBA与引擎原像素SHA逐字节一致，实际连接仍在线，死亡图的receipt match与PG相等，ACK后旧route/settlement为空。五个图集逐幅审阅，另看4张原尺寸，死亡结算标题、空道具提示、返回按钮及职业大厅清楚可见，蓝金风格统一，无明显遮挡，无须ImageGen重出。此处只验收对应状态的画面与实际GameStore ACK，不声称全部UI按钮交互或三职业正常路线通过。

本轮私有Program日志的内容根为/work，显式提供自有PG schema、Development本地认证、PB HTTP/WS和bot-fill30秒；当前领域嵌入配置及实际快照版本一致。它是受控功能环境，不声称/runtime/appsettings.json被整体加载，或与生产全部运行选项等同；没有执行排队容量或性能对比。

## 重点：私有预置失败、修复与样本预算

R1第一职业已建立自有账号和一个领域房间对象，预置器把两条SQL连成一个预编译命令，Npgsql/PostgreSQL报SQLSTATE42601 cannot insert multiple commands into a prepared statement，native exit=-6。未完成正式预置，公共WS弃战、截图和层验收均0。失败账号、原数据库dump、原二进制/源码及日志147份G原件保留，未清空当作没跑过。

参考仓库已有逐条参数化SQL用法，R2只把私有fixture两个INSERT放入同一显式事务，分别执行后commit，不改产品Repository或事务规则。R1按一个房间构造/一个测试账号计预算，R2实际三个逻辑房间/三个账号，保守累计4/4已单独登记，未追加无限重试。三个职业seed/native/inspect全部退出0。560项独立来源/PG/原方法/像素检查通过。

私有控制器已修正为先保存MemAvailable、空闲字节/比例、生产安全指纹、每个谓词和观察异常，再断言；本轮547个样本各字段完整且都通过，最低MemAvailable约2.16GB，最低磁盘比例约4.99955%。这验证本轮保护和记录完整，不能替旧A09.1缺失的失败采样值补造触发原因。门线仍为>=4.9%且>3GB、MemAvailable>500MB，不改业务、容量或GDD规则；只用原云主机，资源不足CAP继续未通过。

所有/evidence与/screens分别在自有384MiB/256MiB tmpfs，压缩归档也先建在自有/tmp内存，云端验证完整XZ和SHA后分十段下载。有效归档41,618,684字节、SHA fd2cf74e037d8518c83553d6f107f1319be96381f80a31d98bf116da5cdee0f4，118个成员全部G核验后才发ACK，APP/控制器实际退出0，原PG数据和最终dump保留。291份源/原件/生产者完整G保管；两次核对唯一R2输入目录owner/压缩包/plan/100输入/2148源和覆盖/143运行依赖/321源/ACK/PID0无容器/无符号链接/生产指纹后精确删除。R1输入此前也已保管后删除；所有旧cloudraw、共享UI缓存和A073父依赖不删。

生产health200、镜像、启动时刻、环境摘要未变。真人按用户要求排除，actual_human_accepted=false；本地仅headless/Dummy/CNO/低优先级解析与无窗口编译，实际模型/PG仅云端，不影响桌面其他项目。没有正式源码/UI/资产/工作簿/GDD改动，没有commit、push或部署。
