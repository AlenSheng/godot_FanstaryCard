# Pending长收尾与局间等待补验；修复只读外部STOP重复写，完整T03仍Partial

本轮使用当前9b客户端、8eb完整Program／49ce配置、独立PG，4个未包裹原主程序各启动1个真实Native并共享一局。私有场景仅在原_process／_wait／_finish入口记录实际值再调用父实现；原主程序退出前没有手动恢复。Pending初始条件明确登记一件绑定白脚、White／0级／Fire／DrawInterval、Mage枚举2，在真实登录回复交付前预置；入局后只锁精确自有InMatchEquipped行，不改行值，阻塞真实资产提交。它是测试初始夹具，不是修改默认发放、70/80血量或PVE规则。另一个账号请求两周期，真实首ACK及cycle1之后进入原2秒局间等待，外部STOP在46ms发出、58ms被Native读到，原取消退出130／Native0／cleanup Passed，保留cycle1且无第二准备。

**前两轮整批失败完整保留。** R1夹具误把当前Protobuf登录请求当JSON读取，4条JSONDecodeError使首回复未交付；错误地先置auth_observed后，客户端重试绕过夹具门，装备未预置、行锁/Pending未建立。该轮实际1世界／4账号／4完成流程／4ACK，超出原预期3完成数也原样保留，不把Pending标签当验证通过。局间等待子例确实有效，13项独立核对后单独复用，不重跑。按现有proto确认请求device1／name2、回复player3与profile UID1／name2后修正夹具，无JSON兼容兜底、不改实际回复字节。旧本地JSONecho只能证明那个假回复控制，不能称真实登录codec通过；新的明确二进制向量／echo门已验证。

R2真实建立Pending并完成了独立手动资源恢复，但原停止整批仍Failed：宿主root创建0644 STOP，Native已实际读到并保留同M；协调器在app用户1000下无条件write_text试图覆盖该文件，PermissionError后42ms即强杀-9，最终报告缺失。归档tar的uid0/gid0/0644与原日志证实原因，不是35秒宽限不够、装备缓存或血量异常。修复tools/cloud_load_test.py的stop_all：只用排他创建缺失标记，已存在常规标记原样保留，目录负例拒绝；不chmod、不换所有者。仅标记创建变化，其他函数AST以及deadline／等待／强杀／报告尾段逐字节相同，默认35秒不变。四个单测含3个真实受控Python子进程与1个目录负例，旧源1失败1错误、新源全过；本地无Godot窗口或对局。

R3保持同一root/0644权限与原原因文本，原主程序正常等待：Pending main130／operator_stopped／passed=false，Native0／cancelled／cycles0／ACK0，原cleanup保持Unknown、receipt空、同一有效M。Native读STOP到父_finish入口34534ms；按协调器自身STOP落戳至Native结束34496ms，两个观测点不同，音频163ms；不把6秒退出＋6秒结算＋22秒核验误当单个22秒上限，也不把1秒轮询实现当毫秒级硬边界。无PermissionError、强杀、最终报告缺失或引擎泄漏；全部审计分片字节、序号、身份、高水位完整。3个同局对照各原完成1流程、main0／Native0／cleanup Passed。49项独立核对通过。

所有4个原主程序已OS终止后，才启动独立新Native，以实际同账号／UID、原保留M走公开API：legacy详情GET200可见原收据，ready-only Bootstrap仍null，Pending ACK409且未写幂等记录。再次保存PG Pending／ACK0后，仅按精确backend PID／backend_start／application_name取消自有SQL睡眠，未写装备值；提交工作器将同收据变就绪，公开ACK200成功。最终1世界／4玩家／4receipt／4唯一ACK、Pending0，声明装备按实际asset_snapshot Destination到RelicPile，恰3条流转／一次结算提交。手动恢复不回填原Native周期或Unknown状态；R2相同独立恢复成功也没有抹去原停止失败。正常legacy GET200、ACK409、ready-onlynull契约已在首次上传前按端点／仓库源码纠正，不把错误GET409提案作为测试标准。

Pending系列预算因必要夹具纠正和真实权限缺陷复验，在R3前冻结由2局增为3局，实际3物理世界／12真实账号；R1原4完成、R2与R3各原3完成，独立恢复各自单列。此前LOAD103 T01/T02两世界／8流程、liveSTOP五世界及所有旧历史不重置，新当前小计10数据库世界再加更早历史，仍在用户几百场上限内。原认证10／写30／读120／RT30未提高，500MB／5percent只是功能资源底线，不是容量SLO。应用1024MiB／CPU1.25，PG384MiB／CPU0.25，tmpfs512／WAL64，无host端口或生产volume。生产身份／镜像／启动时间／环境摘要及health200保持。

746成员源码／raw／PGdump完成G SHA及CRC封存，2149输入由既有当前2147加明确场景覆盖和两个私有GD组成；随后核对106包文件、2149输入、owner、unit PID0／inactive、自有容器消失，仅清理临时云输入。旧R1 G705、R2 G712及原失败都保留。临时完整tools复制触及无关引擎缓存的Windows路径长度限制，恢复时改为只选10个实际Python闭包文件；自动审批以“blocked by policy”拦截删除未执行临时缓存副本，该本地副本保持原位、排除打包且未运行，不重试删除，原仓库与共享缓存不动。

本轮没有修改UI、资源、服务端、数值、协议或客户端9b实现，无需ImageGen，无Git提交／合并／推送或生产部署。完整T03仍需当前class保存与queued等待的明确原主程序证据／完整来源闭合，优先仅补这两个零世界阶段；Pending、between、READY/MOVE/ACK及前四阶段不重跑。88 Accepted／36 Partial／8 Ready、44未整体验收、164个case/profile缺口保持，其他131任务及所有全局gate不变。这里的Unknown是持有声明行锁时的真实未完成状态，不授予全项或容量通过。
