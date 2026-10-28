# PR13 LOAD-02 真实协调器判定 PostgreSQL 集成补测

腾讯云独立源码副本仅向当前 PostgreSQL 测试类插入一个冻结矩阵方法，保持生产和共享源码原字节。原九方法及新增方法全部执行，共十方法，新增方法在真实 PostgreSQL 默认 Guardian 20 卡持久房间保持期间执行八种外部 Python 子进程故障模式，覆盖七个尚缺 POSTGRES 的格。

协调器使用当前 gameplay_load_test 和现有完整故障 fixture：短时限未达负载、CPU／内存超线与最终 audit loss 同时发生、最终 report.json 写失败、仅准备、纯性能超线、无效证据、人工 STOP。既有 fixture 的时钟、观测及子进程是明确的故障注入；只保留原 TemporaryDirectory 原件以便归档，不重新写判定算法，不作为真实负载或容量统计。hang 模式用两个真实独立子进程测试当前 stop_all 只强退指定本轮 PID，另一进程仍活，最后由单独 fixture finalizer 回收；其 3 是故障包装器分类，强退事实来自原 stop_all。

每模式断言当前协调器或实际 CLI 的返回值，并把真实子进程退出码、原报告、多维结果、first／all triggers、应急文件与完整原 raw 保存。每模式后从真实 PostgreSQL 恢复完整快照和持久字节，必须保持不变。生产 Domain 程序集需保持既有 SHA。仅对应结果／有界清理／退出码判据；公开容量阶段保持推迟。

共享资源锁等待 B04 当前分包结束，遵循 500 MB 内存和云盘 15% 安全线。完整原件转存 G 盘；仅通过、终态、无占用且 G 完整校验后才清理本次云端副本。当前尚未执行，不修改验收状态或门禁。
