# Release发布与云主机重启

已完成。UI提交[81445f5a](https://github.com/AlenSheng/godot_FanstaryCard/commit/81445f5ab2e137000cd94d4692e7f6964ea11a6b)已推送远端release，包含本轮42个文件。云端工作副本已快进至该提交，之后按用户指令完成整机重启。

重启已由boot_id变化确认：4eab2634-08f1-4535-96d6-6ad1a54b1b3d → 1b19e1b0-8d64-404f-9596-fb484f8417be。原有8个容器均以原容器ID和镜像恢复；PostgreSQL健康，内网与公网/health/live、/health/ready均200。具体状态及SHA见[publication-receipt.json](publication-receipt.json)。

本次复用原服务端镜像，OCI源码标记仍为4a9215fee6f8c50da79e9895e408717fbd9118de。server/src树与本次release完全一致，相关差异仅涉及服务端测试，未构建新镜像或执行数据迁移。云端Git版本与真实运行镜像标记分别记录。

重启后可用内存约2.76GiB，磁盘空闲约3.60GB（5.69%），保留RAM500MB、磁盘3GB及5%的原保护。没有启动容量补测或删除原始失败证据。

工作区其他2974条状态记录在发布前后保持一致，未混入本次提交。25个源码文件仍与验收SHA一致。final-summary.json保留验收结束时“尚未发布”的历史状态，其封存SHA未变；本文件和回执补充后续发布结果。

首次同步SSH会话在Git快进后超时，重新只读确认工作副本干净、更新锁已释放、没有待重启作业，再单独执行重启并核验新启动标识。失败与成功的原始记录均保存在G:/PR13Evidence/ui-release-restart-20261027-r1。
