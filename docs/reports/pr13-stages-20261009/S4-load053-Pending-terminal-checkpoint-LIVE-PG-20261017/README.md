# LOAD-05.3-T03：真实 Pending 取消与终态检查点恢复

本轮当前 LIVE 支持通过。四个真实 Godot 客户端进入同一真实房间，通过正常公开操作结束；主账号明确置入的初始 White Feet 先经真实 Bootstrap、准备和房间校验。独立只读事务锁住该装备行，真实合法死亡创建一个 durable Pending hold，资产仍 InMatchEquipped，已有两条移动记录。三名伙伴执行原完整 `_run`、合法放弃、真实 ACK 与收尾，不能冒充自然胜利。

原私有完整 Program 子进程实际 SIGKILL，PID 7→24，仍为同一数据库、同一 21 个缓存运行时文件；本轮源码未重建或上传。重启后的 `/health/live=200`、`/health/ready=503` 是 Pending 恢复期间的实际观测，生产身份和健康保持不变。新连接标记后，原客户端另发真实 `room.snapshot.read`，同请求 ID 获得原 M 的终态快照。只记录解析字段及原 packet 的 hex 编码 SHA256，原 packet 原样传给生产解码入口；没有完整二进制重放验收主张。

此时真实 Pending ACK 请求返回 409，原客户端尚无可 ACK receipt。实际 STOP 文件由原 `_process` 消费；原完整负载流程有界收尾后，原报告 outcome=cancelled、ok=false、cycles_completed=0，cleanup=Unknown／client_terminal_pending。M 仍可经 `_settlement_match_id()` 恢复，Pending hold、receipt ID、asset snapshot、装备和两条移动记录未变，未靠进程退出清业务。原报告保留 Unknown，后续恢复未将其改写成 Passed。

只取消本轮已记录 PID／backend_start／application_name 的只读行锁事务后，同一 hold 变为 Committed，同一装备由 InMatchEquipped 变为 RelicPile，总移动记录为三条。原 GameStore 实际加载同一 receipt，独立人工驱动的公开恢复 ACK 成功；持久 ACK 只有一条，hold 流水没有删除或换 ID，取消主周期仍无完成信用。这里的“人工驱动”是自动测试控制器调用原公开方法，不是真人体验。

**必须保留的两轮失败与条件修正：** R6 主进程 93216 exit 1，R7 主进程 79284 exit 1，均因探针预设“重启必须丢失 room，只剩非空 `_settlement_recovery_match_id`”未成立；都没有发送 STOP，也没有执行到原收尾，不能说产品取消失败或将这些轮次改为通过。R7 已证明四名真实成员 Settled、match Completed，仍收到真实终态快照。查阅当前文档后，LOAD-05.3-T03 要求“保留恢复ID不删流水”，并未要求一个内部字段非空。

当前服务端 `GetOwnedTerminalAsync` 在同一 SQL 校验玩家归属与 Settled 状态，`ResolveTerminalCommandAsync` 可从终态检查点返回无 actor／ticker／资产副作用的投影；`RoomRegistry` 在结算释放前要求终态检查点持久化。因此有效恢复 ID 可合法存在于原 room M，独立丢房标识为空并非异常。R8 按这一当前权威语义重新冻结条件，并增加新进程真实快照／请求 ID 关联，未给 Game 的 room、恢复字段或 STOP 标记赋值，未修改游戏逻辑。未对先前怀疑的丢房清理分支作未经证明的修复，也没有把 R8 当作实际“room 为空、独立恢复字段非空”路径的证据。

三轮共新增 3 场、9 个真实客户端进程，保守计 12 次玩家入房；LOAD-05.3 累计 5/8 场、20/32 次保守入房，单项用户 300 场上限不变。R7、R8 合计六个伙伴功能周期与主账号取消周期分开统计。469 条源数据／归档校验通过，409 个归档成员已逐项复核哈希，114 份云端原件（36+37+41）完整保留。5% 磁盘／内存安全余量满足，原 15% 磁盘容量门仍未通过，无容量或真人体验验收主张。

三轮所有本轮客户端、SSH 通道、行锁、自有容器、网络及私有环境均已收尾，生产身份未变。2127 个当前客户端输入逐项相同，四份解释终态恢复行为的服务端实现也与已验证的 328 文件完整源码缓存逐项对应。先前完整源码包继续按已核对的档案引用，未再复制 1.4 GB 原件。

报告仅补 S4 当前证据，register、MAIN 和 gates 原字节保持不变：55 Accepted、67 Partial、10 ReadyForAcceptance，77 项未验收。LOAD-05.3 仍 Partial；还需补匹配待进房、真实战斗中的 STOP，以及周期间等待的明确证据，再做完整逐案例审查。原件：`G:\PR13Evidence\load053-Pending-terminal-checkpoint-LIVE-PG-20261017-originals`。首两轮失败、恢复 ID 条件的三次表示记录及对应源码解释均已归档；没有放宽 READY／超时／资产唯一性判定，80/70 合法生命显示未作修改。
