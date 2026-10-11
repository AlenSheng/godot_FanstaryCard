# 存储检查点 8：成功镜像构建目录回传与清理

成功构建的原生测试镜像 context 已完整回传本地 G 盘并核验，随后仅清理云端 `cache/native-image/Dockerfile`、`godot` 及其空目录，释放 **146,423,808 字节（139.64 MiB）**。本次不声称释放 512 MiB。

G 盘压缩包为 `outputs/pr13-tencent-20261009/native-image-context-backup/delivery.private.tar.gz`，77,865,360 字节，SHA-256 为 `57e5a1c438c191505ae5bcf11d10b338ac30736f5355cb063283e5791a99f8d4`。四个原始成员（两份 context 文件、成功构建证明、恢复计划）及归档 manifest 的 CRC、SHA、原权限和成功镜像来源证明已核验。大体积 Godot 二进制保存在 G 盘私有归档，本目录仅保存回执和小型原始元数据。

清理前复核 exact 路径、inode、mode、nlink=1、SHA 和活跃消费者；只豁免完整容器 ID 匹配、挂载 `/` 且只读的既有监控容器。成功镜像 `sha256:6ea92944e8779a5bb6e5c40faca53a40a1b02b5a0dcd47fff0815ba9cfbded1f` 保留。NuGet、当前 Godot 导入缓存、其他 cache、失败原始数据、历史备份和生产服务均保留，清理时健康检查返回 200。

未来重新构建该镜像前，按 `restore-mapping.json` 将两个成员恢复至准确的空 context 目录，复核 SHA 和原权限后再构建。当前 compiled-only 实验和镜像内 Godot 无需已清理 context；原 Godot 下载包与宿主机工具仍保留。

清理后的根盘 15% 安全线上方空间为 267,857,100 字节，仅代表清理时快照。`readonly-cache-components.json` 是清理前的只读库存，不能视为其他组件的清理授权。本次未执行数值、容量或客户端业务测试，不改变 PR13、MAIN 或任何验收状态。

`source-records.json` 保存本地来源及原字节 SHA；回执副本只将 CRLF 规范化为 UTF-8 LF，JSON 值保留，归档中的小型证明与恢复计划保留原字节。提交前后须按 Git 提交对象中的实际字节核对 `manifest.json`，不能仅依据工作目录校验。
