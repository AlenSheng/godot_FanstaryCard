# Release发布与云主机重启

用户在UI验收完成后明确要求将修改推送远端release并重启云服务器。本次只纳入source-pin-final.json列出的25个已验收文件及本报告目录；其余工作区改动保留。

发布准备已完成：源文件SHA与验收一致，六组合318帧／714项检查及交互回归通过。执行结果将补充到本文件及publication-receipt.json；final-summary.json保留验收结束时的原始状态，不修改其封存内容。

云端重启前本地liveness／readiness均200，Docker已启用，现有8个容器均为unless-stopped。服务端运行源码与当前release一致，差异只涉及服务端测试；本次不构建新镜像，保留真实运行镜像版本标记。云端同步采用固定目标commit的快进，整机重启后核验boot_id变化、容器恢复及健康端点。

原始发布／重启记录保存在G:/PR13Evidence/ui-release-restart-20261027-r1。保留云端RAM500MB、磁盘3GB及5%保护，不启动容量补测，不修改原始失败证据。
