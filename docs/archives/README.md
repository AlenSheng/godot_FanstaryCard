# 历史验收台账归档

pr13-register-snapshots-20261028-r1.tar.xz无损保存135份历史完整register.json，原始总量2,150,459,500B，压缩后1,818,936B。每个成员的原仓库路径、长度、SHA及归档SHA见同名manifest.json。全部成员已经公开证据检查、逐字节往返SHA核验，原失败／待验收／已验收状态均保留。

这些是历史执行台账，不修改2026-10-27用户确认的当前版本处置口径，不启动补测。大部分内容是相同132项台账的重复快照；以整体xz字典压缩保留精确原件，避免把2.15GB重复内容加入每个工作副本。原本已跟踪的register.json不删除，原本未跟踪的135份也继续保留在本机。

如需重放某次历史记录，先还原到私有目录：

```powershell
python tools/restore_pr13_register_snapshots.py --output "G:/PR13Evidence/new-register-restore"
```

也可加--member并指定manifest中的精确路径，只还原一份。输出会保留原仓库相对目录；已存在且SHA相同则跳过，不同则拒绝覆盖。还原前检查完整归档SHA、成员白名单及3GB／5%磁盘保留，不在低磁盘云主机上自动展开全部成员。重新取出快照不代表重新验收或恢复历史接受状态。

其他历史正式报告仍在docs/reports/pr13-stages-20261009，当前决策以本轮正式文件核查README及CURRENT_TASK_DISPOSITIONS_LOCAL_SIM_ACCEPTED_20261027.json为准。
