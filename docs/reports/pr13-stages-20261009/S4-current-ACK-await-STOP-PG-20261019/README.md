# 当前 ACK 等待中 STOP 的真实 API/PG 补测

针对 LOAD-05.3-T02 补齐当前组合的两个定向案例：提交前暂停 ACK、提交已落库但响应尚未交给客户端。使用当前 Runner 原 _run / _finish；观察器调用原 _ready / _process / _graceful_cleanup。夹具只把新建账号和探险入口替换为已有账号登录、已有权威 receipt，实际 Game.login、Bootstrap、Gateway、WebSocket 和 Store ACK 均保留。不是从 stop_requested=true 或关闭实时处理开始，已有9例恢复测试未重跑。

当前 Server DLL 为245265ff，Domain为57ba955a；60个当前客户端代码/数据输入、328个服务端输入前后字节核对一致。2次实际 Native 均退出0，原 Runner 的8项检查及两例共22项独立检查通过。提交前 SQL ACK 为NULL，提交后为已持久时间；两例都先观察到原 _process 读取 STOP、busy=true、pending receipt 保留、cleanup=Unknown、finished=false、cycles=0，再释放响应。

两例随后实际 ACK 成功，原 _run 在 STOP 分支跳过自然完成计数；最终 outcome=cancelled、ok=false、退出0符合取消契约，不能把 ok=false 误报成测试失败，也不能改成 completed。cleanup 各遇1次保留的已解码 bootstrap500，读取重试1次后权威 Passed。每个500同时经 Gateway.failed 和转发的 Game.notice 产生2条原始notice，共4条保留；不是4次失败请求。初次只读复核器误假定errors为空、每例5项检查，已按实际notice和每例4项检查修正并保留旧复核器，没有重跑产品。共18次回环HTTP、4条真实WS通道；每例会话WS的101握手及496字节服务端帧转发可核验，未伪造online状态。

9张资产表共28316行，在恢复后、API启动后及每个案例后4个检查点行数/内容哈希完全一致。已有100玩家、180对局、720结算不变；新本地副本中未ACK从9变7，另7条不属于本次两个定向案例，不构成本轮新失败。新账号、对局和云端调用均0，原600专项预算占用保持180+420，未追加采样。

初次R1在沙箱内 pg_ctl 创建受限令牌时报87/3，PG/API/Native实际启动0，原stderr及副本保留；R2通过同一require_escalated审批机制执行，实际1套PG/API、2次Native，没有绕过审批或放宽正确性。每次Native峰值约113MB，执行中保留5%磁盘/内存余量。两个Native、API/监督器、PG的5个自有PID均已消失，API退出0、PG正常停止，无强制结束。原停止PG来源及失败R1副本全文件SHA未变。

本次只支持当前本地API/PG/实时组合的两个ACK取消时序，不能据此验收WAN、容量、UI渲染或整项LOAD-05.3；待holds及其他await层继续分列。原100客户端容量失败和其他历史失败仍保留，旧41b执行不改称245执行。无产品代码变更。702项本地保留状态/内容、132任务/396案例及77未验收保持，register/gate/MAIN未改；GDDv0.70优先及牧师神器合法80/70原始边界保持，整体验收未完成。
