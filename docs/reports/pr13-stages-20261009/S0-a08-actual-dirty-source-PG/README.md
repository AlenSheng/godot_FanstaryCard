# PR13 A08.1-T02 真实 dirty 来源 PostgreSQL 补测

在腾讯云创建持有 328 份当前产品源码原字节的独立 Git 仓库，提交只作为源文件投影的快照，不当作 release 提交。先用当前 tools/gameplay_load_validation.py 的 provenance 记录真实干净状态，再仅在原 PostgreSQL 测试类插入一个冻结方法，记录 tracked dirty 状态及单独 SHA；使用该 dirty 测试源编译并执行原九条与新增一条数据库测试。

新增方法在真实 PostgreSQL 中保持实际默认 Guardian 20 张卡房间，调用当前 provenance，再核对 Git 真实 status、基准提交、原源 SHA、dirty 源 SHA、配置 SHA 和实际执行的测试程序集 SHA；数据库前后完全一致。生产 Domain 程序集还必须保持已验证 SHA。只关闭准确对应的 POSTGRES 来源审计格，不能代替任意 dirty 产品改动、上线镜像或者新数值实验。

独立调度使用现有共享资源锁，等待当前 B04 分包退出后执行，500 MB 内存安全线和云盘 15% 安全线不变。不得修改生产或共享源码。完整原件在终态后归档 G 盘；真实失败保留；通过且确认无占用后仅清理本测试的云端副本。
