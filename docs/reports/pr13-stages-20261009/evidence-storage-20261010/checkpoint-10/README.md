# 存储检查点 10：完整 NuGet 缓存回传 G 盘后清理

共享 NuGet 缓存已完整回传并核验，随后云端只清理准确目录 `/home/ubuntu/pr13-acceptance-20261009/cache/nuget`。实际移除 1,157 个文件和 777 个目录，释放 **207,843,328 字节（198.21 MiB）**；原始文件逻辑大小为 202,033,560 字节。清理前后健康检查均为 200，runtime、源码、配置、失败证据和生产服务保留。

G 盘私有归档是 `outputs/pr13-tencent-20261009/nuget-cache-backup/delivery.private.tar.gz`，113,887,684 字节，SHA-256 为 `45feda8eba39e2caeeec40dd6dcadd5417039f773e4e19bc714ef082935780cb`。原始 1,161 个成员、外层 gzip CRC、全部成员 SHA、文件／目录模式和原 inode／nlink 账本已核对；44 个 `.nupkg` 的 1,325 个内部文件通过 ZIP CRC。完整包、DLL 和缓存原始内容留在 G 盘，不复制到本公开目录，也未执行这些程序集。

云端删除发生在新 collector 的原生编译、56 项原回归及三套完整 pilot 等价证据已经回传 G 盘之后。原生 mixed 源为 `581cd9f74962dd61424e77c529b1259afbb39fe7`，业务源仍为 B042，instrumentation 来源为 `66c7420532536431b906d1fdb1e68d6d3448e6b9`；Domain 三个原始 hash 实际相同。该 runtime 私有归档的 1,005 个成员及三套原始事件已独立核验。此次缓存存储操作和报告生成都没有重跑回归、pilot、业务 oracle 或原生游戏。

未来任何需要 NuGet 的 .NET 编译或测试，必须先依据 `restore-plan.json` 恢复完整目录和 1,157 个文件，核对准确名称、字节、SHA、Unix mode、uid、gid 以及完整文件／目录集合后才能使用。恢复后的 inode 身份不声称与旧 inode 相同。当前已编译的 runtime 可以使用其已冻结字节；这不豁免后续编译前的缓存恢复要求。

本检查点只证明缓存回传与清理。既有全实验 G 基线为 90／360 个逻辑单元、180,000 场，基线剩余 270 块、540,000 场；这些数字不宣称新 collector 已完成任何后续完整块。PR13、EXPERIMENT、MAIN、LIVE 与容量验收不由本次存储操作升级，也不根据释放量直接声称下一批 512 MiB 资源已足够。

本目录保留原始 G 收据、原始云清理 JSON、完整 cache／restore 元数据及来源 byte SHA，不保存私有凭据、helper 载荷、包或 DLL。新生成文本使用 UTF-8 LF；原始 JSON 逐字节保存，仓库现有报告目录规则禁止 Git 换行转换。报告生成只复查现有归档大小／SHA和小型元数据，没有再次执行完整 gzip／ZIP CRC核验。根代理提交后仍须对照实际 committed Git blob bytes 核验 `manifest.json`。
