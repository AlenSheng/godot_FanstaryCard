# PR13 B12.4-T03 实际资产账链告警 PostgreSQL 补测

腾讯云独立源码副本只向当前 PostgreSQL 测试类插入一个矩阵方法，原九回归及新增方法共十方法运行，生产与共享源码不改。真实默认 Guardian 20 卡持久房间保持完整快照与数据库字节不变。

通过当前 IdentityRepository／PlayerProvisioningService 创建本测试 schema 内的独立用户，按真实 economy_ledger 结构及当前钱包余额建立两个明确拥有的测试流水，第二条 delta5 后余额连续，当前 EconomyReconciliationRepository.InspectAsync 必须 Healthy。仅把第二条 balance_after 加7，其他列及第一条不变；当前真实 SQL 窗口对账必须返回 LedgerChainMismatchCount=1、TotalViolationCount=1、IsHealthy=false。实际读取两条原行、余额和差额，生成对应未解释告警，当前 asset_gate 必须 Blocked／asset_acceptance=false。

健康无告警是明确范围内正控制。不得修复或删除损坏行制造通过：门禁后再次读取原损坏流水并对账，要求告警依旧存在、两个测试行依旧存在、钱包没有额外增加。本案是原告警判据的实际数据库集成，不称实际玩家交易、候选收益、容量、EXPERIMENT／RENDER 或 MAIN 通过；损坏仅发生本测试一次性私有 schema，生产资产不碰。

共享锁等待 B04 当前分包，500 MB 内存和云盘15%不变。真实TRX／完整账链／对账输出／源码和所有原件转存 G，终态无占用且G完整SHA／CRC校验后才清理本次通过副本。未执行前全部验收状态不变。
