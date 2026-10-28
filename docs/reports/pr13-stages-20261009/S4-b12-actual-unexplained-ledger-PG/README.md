# PR13 B12.4-T03 实际账链损坏告警数据库结果

腾讯云原九回归与新增一个实际资产账链矩阵共十方法通过，零失败、零跳过、无 OOM。当前正式 IdentityRepository／PlayerProvisioningService 在本测试私有 schema 创建独立用户，按真实表结构建立明确的测试钱包和两条人工流水；健康时当前 EconomyReconciliationRepository SQL 返回 Healthy、零告警。

仅把第二条 balance_after 增加7，delta5及第一条不变，真实 SQL 对账产生 LedgerChainMismatchCount=1、TotalViolationCount=1、IsHealthy=false。实际两行余额和delta读取推导差额7，当前 asset_gate 对该未解释告警返回 Blocked／asset_acceptance=false。门禁后损坏行原字节保持、两个测试行依旧存在、再次对账告警依旧为1；测试钱包没有额外增加。没有修复或删除坏账制造通过。实际默认 Guardian 20卡房间完整快照与房间持久字节不变；测试账链本身的故障变化有完整前后原件，生产资产未触碰。

生产 Domain parent SHA 未变，328 当前源及策略输入匹配 Git，插入仅限一个拥有的测试方法。670 完整原件、G归档 SHA／CRC、成员 SHA、健康／损坏流水和实际对账输出再次核对，存 G:/PR13Evidence/B12-unexplained-ledger-PG-r1。终态无容器及绑定占用后只清理本次通过的 work／persistent-output，回收48,795,648已分配字节，共享源和旧失败原件保留。

本证据只对应实际资产账链未解释告警的 POSTGRES 格。人工故障不是生产账务问题；没有实际玩家交易、候选收益、容量、EXPERIMENT／RENDER 或 MAIN 通过主张。本阶段记录实际结果，下一阶段登记精确格。
