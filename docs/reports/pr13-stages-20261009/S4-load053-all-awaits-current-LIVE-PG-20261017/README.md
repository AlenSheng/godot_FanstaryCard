# LOAD-05.3：各等待点当前运行证据汇总

当前源码的 12 类等待点已有对应实测支持：登录、职业保存、准备、入队、票据查询、排队、Matched 待进房、实际 Pve 等待、Pending 结算与恢复 ID、ACK 提交前、ACK 提交后尚未交付、周期间等待。前三份补充报告与本份共同组成证据，`await-coverage.json` 逐项给出来源。本报告不自动改 register、MAIN 或 gate，官方 LOAD-05.3 仍 Partial，55 Accepted／67 Partial／10 ReadyForAcceptance，77 项未验收。

**本次三项补充：** R10 的真实伙伴 9060 在第一局原 ACK 成功、原计数递增为 1 后，进入原 2 秒 between_matches 等待，写实际 STOP 文件；8ms 后由原 `_process` 读取。原报告为 cancelled／exit 0，保留已完成的第一局 count=1；数据库只有一份准备、receipt、ACK，没有第二局，不能把“本轮运行取消”误算为取消了已完成的第一局。

R11 主进程 1932 在真实 Pve 的原 400ms 等待中消化 STOP。主控制器没有调用退出或 ACK；原 `_graceful_cleanup` 自行发送合法公开退出，再真实 drain ACK。原报告 cancelled、cycles_completed=0、cleanup=Passed，独立 PG 只有一个 ACK，该装备三次移动，无 Pending holds 或在局装备锁。这个合法主动退出是功能用例，不是自然战斗胜利。

R12 主进程 15980 收到实际 Matched 查询结果时，原 READY 还剩 13650ms。实际 STOP 先由原 `_process` 读取，再把原查询结果原样交回；没有 READY 调用或实际 READY 写包，没有主账号房间。原收尾先读权威票据、记录 defer_matched，不 DELETE 已 Matched 票据，等待真实 15 秒 READY 移除；原报告 cancelled／exit 0、cycles=0、全检查通过、cleanup=Passed。宿主在原进程实际退出后独立读 PG：同一成员 Removed，同一准备 Cancelled，同一装备回到 Equipped，无结算／ACK／holds／锁。

**原整体失败与观测修正必须保留：** R9 主进程 110460 exit 1，辅助数据库标签含大写字母被控制器拒绝，未发送目标 STOP，整轮 false。R10 主进程 122100 exit 1，辅助前置调用未返回可解析成功，20 秒消费者门自动释放，原 15 秒 READY 截止已到；原 ready_deadline_expired=false 检查正确触发，未发送目标 STOP，具体传输根因未证明，整轮 false。R10 的伙伴 between-wait 单项成功只按该原件单独使用，不能把整轮改成通过。执行前还按实际 V006 结构修正了夹具关联，票据无 SQL match_id 字段，要通过成员及 preparation_id 关联。

R12 客户端与全部四个实际进程均 exit 0，但原独立断言误要求票据也变为 Cancelled，因此原 native_ok／云端整轮 false 与错误断言文件完整保留。该预期与已固定的上下文提醒相悖：历史 Matched 票据可以保留。当前已验证的 `MatchmakingRepository` 到期路径只将未就绪成员置 Removed、取消其准备并释放装备，Matched 票据保留匹配历史；只有 Queued 取消／过期路径才改票据状态。不能把这个历史字段单独当作仍占房的依据。

独立复核使用同一批原件确认，上述旧断言除“ticket 必须 Cancelled”外，其余关联及资源条件全部满足。正确释放事实是 Removed 成员、Cancelled 准备、权威 Bootstrap 无未完成业务、实际没有房间／READY／锁，装备身份与归属正确。原游戏不重跑、原 false 不覆盖、不删除或改写业务数据；当前单项证据结论与旧错误观察器的整轮结论分开保存。不能借修订把未完成的测试当作通过，也不需要为合法历史 Matched 或合法 80/70 显示修改产品。

为了不让辅助观测阻塞真实 15 秒窗口，R12 将 SQL 查询移到原进程退出之后，窗口内依据真实已完成的 Matched 响应立即发出 STOP，再用相同票据／准备／成员 M 逐项核对。原 READY 15 秒、补位 30 秒、业务 HTTP 10／30 秒与原收尾时限均未改变。

**执行量专项修订：** LOAD-05.3 原自设上限 8 场，追加记录阶段失败后，在 R12 执行前冻结修订为 10 场；旧 8 场计划、失败和全部实测计数保留。实际累计 9 场、保守 36 次玩家入房，本次新增 4 场／16 个真实客户端进程，用户单项默认 300 场上限不变。容量门、唯一 ACK／资产、时限和数据身份条件没有放宽。相关正式计划为 `docs/plans/PR13_LOAD053_SELF_BUDGET_REVISION_20261017.json`。

554 条原件与归档校验通过，495 个 G 盘成员再次逐项复核哈希，102 份云端原件（25+25+26+26）保留。当前 2127 个产品输入逐项不变；本轮没有产品修复、服务器重建、游戏源码上传、部署或推送。三个关键主张的原审计日志额外核对为无丢失且序号连续。所有本轮客户端、通道、私有容器、网络与私有环境都已结束，生产身份和健康不变；5% 安全余量满足，原 15% 磁盘容量门仍未通过。

`case-profile-recommendations.json` 只提出三项 canonical LIVE 支持与完整等待点范围供 MAIN 逐案例审查，不直接升级官方状态，整个 132 项目标仍未完成。G 原件：`G:\PR13Evidence\load053-final-awaits-LIVE-PG-20261017-originals`。后续保留所有不通过轮次；不能仅凭某个进程 exit 0、单个正常周期或本报告的局部成功授予整体验收。
