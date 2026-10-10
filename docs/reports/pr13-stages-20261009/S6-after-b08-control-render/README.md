# S6 B08.1 控制合同三层覆盖补齐

三个原 case 的 RENDER 补齐：54 组实际显示、3240 次权威状态核对和 54 个额外多状态开发检查。结合此前 54000 行/486000 次权威控制实验，B08.1 从 Partial 转为 ReadyForAcceptance，仍无 MAIN Accepted 签署。

当前 14 Accepted、104 Partial、2 Failed、12 ReadyForAcceptance；RENDER 缺口 66→63，其他层次缺口保持。共 33 包/132 项/396 原检查、其他 131 项、所有门、严格失败/容量暂缓和真人排除完全不变。原失败补充 fixture 与资源启动预检全部保留原始记录。

主界面多行状态高度修正后，三条完整显示矩阵全部重新执行，来源统一为 f478b790ea03139bd5c42cf415c54576a730de71。2089 个输入与该 Git 来源逐字节匹配，旧失败和修前字体诊断分别保留。原生实验来源 90713f2fc032178fdcb2cc26b479070bb822ccaa 和旧 case 历史继续保留，旧结果没有重标。

当前指针转到本目录，回滚可恢复 S6-after-b08-control。GitHub 四个 job 因 AccountBilling 未启动，MAIN、G0～G5 和总体 PR13 仍未完成。
