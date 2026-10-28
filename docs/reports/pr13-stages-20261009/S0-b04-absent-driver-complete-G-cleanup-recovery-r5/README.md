# PR13 B04 原件完整、清理尚未开始时的驱动恢复 R5

权威本机进程检查确认 R4 驱动66668和发布60484均不存在；没有失败 JSON，stderr为空，退出原因未知，不推定为握手或原生错误。云端原句柄 Priest-E1-build-B0-P0700 已 inactive／PID0／exit0、原生40场及独立验证成功。G盘该包归档、manifest、完整成员和回执均已存在，尚无本地清理回执。

独立云端只读检查证实没有运行中的 controller、输出仍在且原 collect 完全等于原 manifest；云端没有 local-G-receipt、cleanup-intent或cleanup marker。因此清理尚未写入任何状态，不属于未知副作用重试。首个只读检查因pgrep无匹配返回1失败，原诊断保留，第二只读检查显式允许无匹配结果，未执行任何原生或清理变更。

R5取得原独占锁，重新核对1035包归档及manifest／清理链接；复核当前已完整G归档的CRC、归档SHA及每原件SHA，再仅调用原 cleanup 完成已证明尚未开始的操作。未重传、未重跑当前包。随后确认1036闭合、current为空，并继续原下一包；原控制器／计划／运行时／验证器、样本、种子和5,400包／216,000场总量保持。

新隐藏 Python 控制进程用 Win32_Process.Create 创建。实际父进程链和账号核实为当前用户、上级 WmiPrvSE.exe；使用原用户profile与固定SSH主机密钥和Git凭据。没有定时任务、启动项或生产设置变更。原退出原因仍未知；legacy事件名中的FailedTransport仅为继承名称，不作为传输故障证明。旧日志和完整当前G回执保留在 retained-interruptions，本阶段不关闭正式验收格。完整条件发布从6继续，前六条件不重复发布。
