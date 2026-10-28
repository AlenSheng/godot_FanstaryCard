# A09.4-T02：未运行数据库不得判为通过（2026-10-21）

在当前云主机上，以同一份当前测试 DLL `201b00dea646e981d1b7692dbfbb58a2339d7ab7a79a9f53a3136029938c1dab` 和 143 份原字节运行依赖启动一次真实 VSTest。明确清空数据库配置、使用 Docker networknone，没有 PG 容器或数据库连接。真实结果是 native exit0、9 条 NotExecuted、0 条 Passed、0 个数据库方法执行、0 份数据库结果。

当前覆盖检查器实际退出 3，状态 Blocked；正式 canonical 导出器的实际 `require_unskipped()` 也抛出拒绝异常，没有导出 Passed。上一轮真实 PG 九项通过的原始 TRX 只作为同一解析器的正对照，没有重跑或改称本轮结果。MAIN 独立复核据此关闭 A09.4-T02 的 POSTGRES **缺库拒绝反例**，不授予正向数据库执行通过，也不关闭 LIVE/RENDER 或整项验收。

原私有运行器和控制器仍记录失败，原件未改：实际 TRX 的九条逐项结果都是 NotExecuted，但汇总 `notExecuted` 为 0；私有脚本额外假定汇总值必须为 9，因而误报。本次独立裁决使用真实逐项记录、executed0/passed0、实际门禁退出 3 和正式导出器拒绝结果，未把汇总值改成 9，未伪造 XML，未重跑或降低缺库不得通过的标准。这个元数据矛盾本身也被严格覆盖门拦截。其他失败记录与历史 Guardian 数据继续保留。

35 份云端原始文件、143 份运行依赖身份和当前相关源文件经过核对，207 项独立检查通过；这些均不是新增玩法场次。G 盘保留完整输入包、实际 TRX、原失败、两个检查器、原始当前构建与 Linux 启动文件来源。核对 G 盘后仅清理本次拥有的输入目录，SDK 容器已移除，原云端证据和父级运行依赖保留。测试前后生产指纹一致、健康检查 200。本地没有启动 Godot 或 PG，没有窗口、焦点或输入操作。

另已只读核实最新 release 的 [CI 39530626829](https://github.com/AlenSheng/godot_FanstaryCard/actions/runs/39530626829)：四个作业全部 runner_id0、steps=[]，未执行测试。[client 作业](https://github.com/AlenSheng/godot_FanstaryCard/actions/runs/39530626829/job/118995428610) 的当前注释明确为账户近期支付失败或额度需要增加，尚不能判定是哪一种原因。这是当前 API 结果，未沿用旧记录推断；没有重试、dispatch、改账户设置、预算或权限。IAB 未登录，原有连接器未提供 annotations 端点，随后通过已有 Git 凭据的非交互只读接口取得注释；凭据内容没有写盘或输出。真实 READY 触发与 fork 的剩余验收继续保留。

两个 GDD 文件摘要保持不变，主卷覆盖规则及用户确认的合法 80/70 边界未修改。当前仍为 100 Accepted、24 Partial、8 ReadyForAcceptance，共 32 项未验收；缺失 case/profile 从 118 降到 117。所有全局门保持未通过，没有新增 release 提交或部署。
