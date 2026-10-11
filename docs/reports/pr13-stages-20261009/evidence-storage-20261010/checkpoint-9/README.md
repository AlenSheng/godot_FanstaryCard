# 存储检查点 9：已结束的宿主 Godot 输入回传与清理

两个已结束测试使用的宿主 Godot 输入已完整回传本地 G 盘并核验，随后清理云端 `cache/cleanup-authority-godot/Godot_v4.7.2-stable_linux.x86_64`、`cache/godot-linux.zip` 及其空二进制目录，实际释放 **224,280,576 字节（213.89 MiB）**。本次存储操作已完成，不代表 PR13、MAIN、LIVE 或容量验收通过，也不声称回收 512 MiB 或后续长期批次的资源已足够。

G 盘私有归档为 `outputs/pr13-tencent-20261009/host-godot-cache-backup/delivery.private.tar.gz`，155,688,873 字节，SHA-256 为 `f067c6e35639129e8558e77c0abf9c356a27198a08188a36995b2abd6491b369`。7 个原始成员和 manifest 已核对 SHA、原权限与外层 gzip CRC；ZIP 内部 CRC 和单个 Godot 成员 SHA 也通过。本目录保存原始回执、5 份小型归档证明和恢复映射，大体积二进制及 ZIP 保存在 G 盘归档。

来源是旧腾讯云 `cleanup-ticket-authority-r8` 的 OFFLINE 组件结果：85/85 个实际 Godot 断言和 61/61 个协调器回归通过，工作树覆盖和基线来源明确记录，engine SHA 为 `8d106cbe6144c2dc7e881d61d2429c1a8a76e6b22ef48bd5e48dcf934953f71e`。此次仅复核该成功来源与缓存字节，未重跑组件测试。r1～r7 的失败原始记录、普通源码、NuGet、当前 Godot imports、其他缓存、不可变测试镜像和生产服务均保留。

删除前确认准确路径、inode、mode、nlink=1、SHA、旧服务 MainPID=0 和无活跃消费者。唯一豁免为完整 ID 匹配且挂载 `/` 只读的既有监控容器。清理仅执行两个准确文件的 unlink 和空目录 rmdir；镜像及小型来源证明保留，清理前后健康检查通过。根盘 15% 安全线上方空间为 487,120,076 字节，是清理时快照。

未来复跑旧宿主 runner、runtime retry 或 ZIP 镜像构建 bootstrap 前，按 `restore-mapping.json` 恢复准确目标，逐项核对 SHA 和原权限。当前 compiled-only 原生实验及镜像内 Godot 无需这两个宿主缓存输入。原始事件未压缩累计预算（例如 16 GiB）与云盘实际保存的压缩数据预留分别约束，本次回收不能替代下一批资源检查。

本地归档核验器曾遇到 Python 3.10 的 `SpooledTemporaryFile.seekable` 接口差异，改用 G 盘真实 `TemporaryFile` 暂存压缩 ZIP 后，完整核验重新通过，随后才执行云清理。该阶段未展开或运行 Godot 可执行文件。

`source-records.json` 保留来源原字节 SHA；回执副本仅规范化为 UTF-8 LF，归档中 5 份小型证明保留原字节。生成本报告只核对这些小型成员和记录，未再次执行完整归档 CRC 或业务测试。根代理提交后仍须以 Git 提交对象实际字节核对 `manifest.json`。
