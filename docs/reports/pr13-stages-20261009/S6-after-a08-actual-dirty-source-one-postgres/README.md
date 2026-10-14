# PR13 A08 dirty 来源一项 PostgreSQL 证据登记

当前 provenance 对真实独立 Git 基准投影与 tracked dirty 测试源分别记录：Git 基准相同，dirty 为真，原源与 dirty 源 SHA 不同；投影提交与 release 提交分开。dirty 源确实用于云端编译，实际执行测试程序集 SHA 与产物一致。十条 PostgreSQL 测试通过、零跳过，实际默认 Guardian 房间的快照和持久数据库字节不变，生产 Domain 程序集未变。

只补齐 PR13-A08.1-T02 的 POSTGRES 格，缺口 101 降为 100。A08.1 仍 Partial，T01 的 marker／实际构建来源测试未补齐。1,095 原件及完整归档 SHA／CRC、全部成员 SHA 和当前源码复核已经完成，本次通过副本的云端清理有完整 G 回执。其余 LIVE／EXPERIMENT／CAPACITY／AUDIT／RENDER 缺口、失败项、依赖、门禁和总体验收均不变。
