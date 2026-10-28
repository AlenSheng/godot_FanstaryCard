# PR13 A08.1-T02 dirty 编译来源真实数据库验证

腾讯云独立 Git 仓库中 328 份当前产品源原件先提交为基准投影，再只在真实 PostgreSQL 测试类插入一个冻结方法。真实 git status 从干净变为且仅为该 tracked 文件修改，基准提交保持不变，provenance 记录原 SHA 与 dirty SHA。该独立快照提交不是 release 提交，两者分别记录。

云端以 dirty 测试源实际编译并执行原九方法与新增方法，共十条通过、零跳过、零失败、无 OOM。新增方法在真实 PostgreSQL 默认 Guardian 20 卡房间存储期间调用当前 gameplay_load_validation.provenance，校验真实 Git 状态、源码 hash、基准提交和实际执行测试程序集 SHA。持久完整快照、数据库字节及 matches／room_snapshots 各一条均未变化。生产 Domain 程序集保持原 SHA 844065af...；这不是产品逻辑改动或上线镜像切换测试。

完整 1,095 原件、归档 SHA／CRC、全部成员 SHA、328 当前 Git 源码及十条 TRX 复核通过。所有原件存 G:/PR13Evidence/A08-dirty-source-PG-r1。实际终态无容器、无绑定占用后，只清理本次通过的云端 work 与 persistent-output，回收 51,675,136 已分配字节；共享源码、运行时及失败原件保留。仅对应一个 POSTGRES 来源判据，其余缺口和总体验收保持。
