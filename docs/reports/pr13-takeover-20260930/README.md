# PR13 独立云端接管

2026-09-30 用户明确授权接管，旧收尾说明保留为历史。仓库为
`AlenSheng/godot_FanstaryCard`，PR13 分支为
`fix/gameplay-load-evidence-20260929`，集成基准为 `release`。

[baseline.json](baseline.json) 冻结交接 head、CI、包入口和独立复跑；
[register.json](register.json) 与 [TASK_CHECKLIST.md](TASK_CHECKLIST.md)
逐项保留全部 132 子项的依赖、负责人、历史状态和当前状态。尚无新的 Accepted，
G0–G5 均未签署。后续每批记录精确修改 SHA、测试命令、证据与剩余阻塞。

固定纯提交 `73d4e41ca819d533c8d2ce80952c72c0fab6d6b6` 的独立复跑：
53 Python 测试、27 显式离线案例、Godot 导入与五个离线 gate 全通过。
27 个回执来自新的 Linux 纯 checkout；未据此声称覆盖全部 396 案例。

首批 P0 反例通过实际 coordinator main/report/exit 路径注入，时钟和子进程为
确定性 fixture，不是网络容量或真实玩法证据。原 head 的正例及坏 JSON 检查通过，
其余 8 个负例方法产生 10 个断言失败（包括三个畸形 audit count 子例）：

- 最终 status 才出现审计丢失或畸形计数时仍可 exit 0。
- 尾部指标无效、JSONL 中间/尾部缺序号、外部 run 完成事件均未阻止通过。
- 最终 status 消失时缓存可继续证明业务清理成功。
- STOP 后 exit 7 会返回 3，但报告仍可写 `acceptance_passed=true` 和清理成功。

修复要求最终 status 实际存在，检查尾部指标、最终审计计数及业务错误，按启动
run/client/epoch 验证逐行 JSONL 和最终水位。外部事件从计数中排除并保留错误；
缺失原始事件不会由 status 补造。异常退出明确使 execution/cleanup 失败。
HTTP operations 的副本必须与同序号的归属 telemetry 完全一致，不能替换请求结果。
CI 会上传精确 checkout SHA、Python 版本和完整 accounting 测试日志。

交付 ZIP 元数据和预期哈希已核验，但本环境 `gh api` 返回 Forbidden，准确的
私有草稿下载 URL 返回 404。尚未取得 ZIP 字节，不能声称完成整包哈希、
PACKAGE_MANIFEST 或 147 个历史文件的内容核验。需要安全授权的现有 asset 下载
或文件传输渠道。原历史 raw 缺失的两项仍 Blocked，不用新测试替代。

服务端 mandatory `.agents/skills/server_create/SKILL.md` 在仓库和环境中不存在；
已报告并按明确授权继续不受影响工作，没有声称读取该技能。

本批没有访问测试服、部署、重启、合并、启用候选数值、恢复数据库或修改账本。
原 360000/216000/216000 模拟 cohort、未达标容量、全局 ledger mismatch=1
均保留各自来源与限制。新的独立复跑和代码修复不改写这些历史结论。
