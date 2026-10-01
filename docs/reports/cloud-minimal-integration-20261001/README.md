# 最小控制器与默认分支注册候选：待父任务独立审核

用户于 2026-10-01 00:31 UTC 明确批准审核和测试后的最小 release/main 集成。本批次只准备固定候选、差异和证据；**未修改远端 release/main，未触发部署，未读取 secret，未修改预算、支付或权限**。父任务独立审核确认前不应用。

## 固定候选与精确差异

| 目标 | 核验基线 | 固定候选 | 最小差异 |
| --- | --- | --- | --- |
| release | `28c6c7e7d3898e4d2abd186f53361477ba380330` | `65361bcc27c51c28651c86c5dbba4f083a9b39e0` | 24 文件；23 个新增控制器/工具/说明，1 个既有 Numerical 工作流只改暂存/上传 |
| 默认 main | `b39841d3f5191c11c9e51c7e6875490789aba53c` | `1517f9fae8d865b8d663fa27d9fd38e95cb03d28` | 仅新增 `.github/workflows/test-server-deploy.yml`，40 行 |

候选分支为 `codex/cloud-controller-minimal-20261001`、`codex/cloud-main-registration-minimal-20261001`。本证据分支不应整体集成；应只使用上表固定候选/patch。release 的首轮 `507334dd` 已被最终 `65361bcc` 替代；前者尚未包含旧版 Numerical 上传修正。

完整 [release-controller.patch](release-controller.patch) SHA256：`def15f7981db28bc623f84236ec91ad819ed2cdbea6ebd88535facea4990b598`。
完整 [main-registration.patch](main-registration.patch) SHA256：`ec4f20528424ad293bdf1c94ef1adb7529bed46813a577b47ece7df7259ac76b`。
两份 patch 均在独立 Git index 从指定基线 apply-check/apply，得到与候选一致的 tree；完整逐文件字节数、SHA256、来源和 tree 在 [candidate-review.json](candidate-review.json)。

来源只取 PR14 `262390134e98f169899d076e6fa21926d44ba1aa` 的控制器、工具和部署说明，以及 PR18 测试代码 `cc216e07cb63a1fb2d96430f09effc6452ae57fa` 的 Cloud 白名单、导出器和测试。部署 workflow、deployment/remote/ship 及原兼容 guard 与 PR14 字节相同。没有合并 PR15/17/18 验证分支，没有带入 PR13 业务/UI、跨版本 harness、冻结验证工作流或大份历史报告。

release 有旧版 Numerical 工作流，故只套 PR18 的白名单暂存/上传 hunk。结构检查将此 hunk逆向还原后，整个工作流与 release 基线相同：原 Godot 4.7、导入命令、用例、触发路径、权限等全部保留；未携带 PR18 的 .NET 安装、Godot 4.7.2/命令调整和 preview 脚本。其现有三个报告使用受限合成 fixture 验证完整字节保留；五个本来不产出的 preview 文件明确记为 missing，非已执行。release 没有 Gameplay 工作流，该项白名单修正留在 PR18，不能拷入整份 PR13 工作流来凑齐。

server/client/config/protocol/GDD 对各自基线均无差异。main 与 release 的 dispatch 输入完全相同，main `permissions: {}`，唯一 job 恒为 `${{ false }}`，没有 Environment、secret、checkout 或服务器操作。main 只用于 GitHub 默认分支 workflow_dispatch 的发现/注册；release 仍是开发发布和受信任控制器来源，默认分支不变。注册后的 UI 可发现性及选 release 加载实现尚待实际集成后只读核验。

## 验证结果与限制

- 最终 release 候选 `65361bcc` 的 [41 项控制器测试](cloud-tests-final.log) 全通过；首次固定候选测试也保留在 [cloud-tests.log](cloud-tests.log)。覆盖授权、artifact、输入、事务/回滚、断连 unknown 和白名单诊断。
- actionlint 对 Cloud、旧版 Numerical、release 部署 workflow、main 注册 stub 全通过；[日志](actionlint.log) 无诊断。13 个 Python 文件解析、5 个 Bash 脚本语法通过。
- 只读 scope/来源/输入 schema、原有 guard 字节一致性、旧 Numerical 仅暂存/上传修改、三报告完整保留、独立 index patch/tree 检查全部通过。
- **完整回归在测试项目编译阶段阻断**：[Domain build 完整日志](domain-build.log) 明确记录 Domain.dll 已成功构建；10 个 CS1739/CS1061、0 warnings 均来自 Domain.Tests 的 CombatAuthoritativeRulesTests（useConsumptionBasedFenxian/useFractionalGuardianWeapon/快照成员不匹配），测试未执行。这阻断完整回归及最终镜像测试验收，不能称应用本体编译失败。编译在 `507334dd` 上使用工作区外 artifacts 与本地 NuGet cache 完成；最终 `65361bcc` 的 server/client/config/protocol 完全相同。没有为此修改 PR13、跳过用例或降低镜像门槛。
- 本候选没有执行新的最终镜像/restart/Production/DB-outage 或线上验证，不能套用 PR17/18 的不同应用源码镜像证据。**完整部署测试未满足，application_deployable=false，Rooms guard 继续阻断；热回滚 unsafe 与排空 guard 完备性未证明仍有效。**
- 候选/证据分支不匹配仓库现有 push branch 触发规则；候选推送后的 GitHub API head 查询均为 0 workflow runs。未开 PR 或启动批量 CI，避免旧基线的已知编译失败消耗免费分钟。下一有效候选 CI 由父任务统一安排。

## 单次免费 CI 恢复验证

父任务从已登录 Billing 页只读核验：9 月 Actions 2000/2000 included minutes，额外预算 0 且 Stop usage Yes；10 月 0/2000 included minutes 重置。本任务没有改变任何预算/付款/权限，仅按明确授权重跑 [Numerical run36769267487](https://github.com/AlenSheng/godot_FanstaryCard/actions/runs/36769267487)，原失败 head `2f1071763fca5f73a7464471f80168ea0854c3ad` 固定不变。

attempt2/job110160775969 分配 runner1000000562，checkout/.NET/Godot 安装、隔离导入、数值场景、preview 对照、白名单上传均实际执行且终态 success，证明免费月重置后已恢复执行能力；不声称自行复核了运行后的计费总额。完整安全日志见 [job log](october-numerical-job-110160775969.log)，仅做凭据文本脱敏与行尾空白规范化；API 原始安全日志另存云工作区 `/workspace/pr14-artifact-evidence/october-numerical-job-110160775969.log`。运行/步骤/artifact 元数据见 [单次记录](october-one-shot-numerical-20261001.json)。新 artifact11133698689 为 361100 bytes，API digest `sha256:a3cbd14a4614b8bf06f6f871611d5f490f98c9a8992be5b8e6770f31e048e35a`；本批次未另下载或冒称独立核验此 ZIP 内容。

Cloud36769267481/Gameplay36769267480 未重试，仍保留原无 runner/无 steps 的失败状态；不能称 PR18 final head 全 CI 通过。此成功属于 PR18 固定候选，并非上述新 release/main 候选的 CI。

## 父任务审核与后续应用边界

请独立审核上表固定 SHA、逐文件来源和两份 patch，以及完整应用测试仍失败的限制；本批次停在这里。拿到父任务审核确认并满足对应测试条件后，才执行用户已批准的最小分支集成，无需再次询问同一用户授权。应用前再次核对远端两个基线；任一分支变化都重新生成差异和固定 SHA，不硬套旧候选。

没有设置 TEST_DEPLOY_ENABLED/APPROVED_WORKFLOW_SHA 等变量，没有运行部署 workflow。控制器集成与 main 注册不代表可部署；实际操作仍需同仓库固定版本、真实保护 API、可信 release controller、最终镜像测试、兼容 guard、互斥、备份、健康/回滚和证据门槛。本批次不豁免 Rooms，不连接服务器、不恢复数据库、不操作生产。
