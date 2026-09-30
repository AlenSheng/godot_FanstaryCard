# 固定 PR13 + PR14 的隔离镜像候选

这是一次独立验证，不是发布、合并请求批准或 PR13 全量验收。

- PR13 源码固定为 `b7099ef716235be68395255360cbd5cf6c67baff`。
- PR14 控制器固定为 `262390134e98f169899d076e6fa21926d44ba1aa`。
- 共同基线及本次 `release` 提案基线为 `28c6c7e7d3898e4d2abd186f53361477ba380330`。
- 本次 `main` 注册提案基线为 `b39841d3f5191c11c9e51c7e6875490789aba53c`。
- 独立分支为 `codex/cloud-compatible-validation-20260930`，工作树为
  `/workspace/pr14-compatible`；PR13、PR14、release、main 均不写入。

组成方式是以 PR13 固定提交为父提交，完整应用 PR14 的 25 个新增文件。
这 25 个路径在 PR13 中不存在，patch 无冲突，blob 和文件模式逐一相等。
只另增独立验证入口、组成核验脚本与本目录的提案／证据。
`tools/cloud/verify_integration.py` 在 CI 用 Git 对象核验整个候选树，拒绝
PR13 源码或 PR14 控制器的任何额外差异；不会用当前移动中的 PR13 head 替代输入。
候选自己的完整 SHA 由 CI 的 `composition.json` 绑定，不在文件内自引用。

## 无服务器秘密的完整验证

`.github/workflows/integration-image-check.yml` 仅响应独立分支 push。
权限只有 `contents: read`；没有 Environment、服务器秘密、SSH、部署或公网测试服
访问。Checkout 不保留 GitHub 凭据。Docker／PG 全部为 runner 上可丢弃的隔离资源。

此入口执行未修改的 PR14 控制测试，然后构建同一候选 SHA 的最终混淆 runtime
和私有 build stage，并复用现有 `tools/validate_docker_server.py`。
必须完成最终 DLL/hash 与混淆差异检查、全部 Domain／Server 测试、真实 HTTP／
WebSocket、强制应用重启、Production 本地认证 404、DB ready 503／live 200／
恢复 200 和清理；任一失败使 CI 失败。不会用 mock 或源码测试代替镜像验收。

每次成功或失败都保留构建／控制／验证日志、最终镜像清洁摘要、完整脱敏测试日志
及实际生成的 TRX，artifact 保留 30 天。JWT、Bearer 和凭据赋值脱敏；不上传
私有 DLL、映射、数据库、runtime state 或真实凭据。原始私有验证目录仍在本次
runner 上，随 runner 销毁；失败诊断不再依赖它。正式结论以该固定候选 CI 的
真实结果为准，未执行的阶段不能标为通过。

## 两份尚未实施的准确待审批 diff

`inputs-and-proposals.json` 记录下列 patch 的 SHA256、精确基线、文件列表、
临时 index 中的 apply 检查结果和预期树。没有修改任何发布分支。

1. `release-controller.patch`：以固定 release 为基线，增加 PR14 的原样 25 个
   文件。使审查过的真实控制器存在于用户指定的发布来源 `release`，但不包含
   PR13 应用代码集成、启用变量、实际部署或秘密值。若 release 后续移动，需重新
   审查差异并重新生成 patch；不得直接覆盖新的提交。
2. `main-registration.patch`：仅新增同路径
   `.github/workflows/test-server-deploy.yml`，保留完全相同的 dispatch inputs。
   `permissions: {}`，唯一 job 恒为 false，没有 Environment、checkout、秘密或
   服务器命令。默认分支 main 上存在同路径文件是 GitHub 注册 dispatch 入口的
   技术依赖。真正运行时必须选 `ref=release`，加载 release 中的完整受控工作流。
   main 不变成发布基准，也不更改 GitHub 默认分支。

`controller-on-source.patch` 是精确 PR13 父提交到原样 PR14 控制器组成的独立
integration diff；它与 release-controller.patch 摘要相同。额外验证／审查文件
在独立分支 commit diff 中逐项可见，不需要合并到 release。

两个 patch 只在临时 Git index 中通过 `git apply --check --cached` 并计算树，
不是已经实施或批准的变更。审批需针对精确基线和 diff；集成 release 后还需
记录最终控制器提交并设置相等的 `TEST_DEPLOY_APPROVED_WORKFLOW_SHA`，以及明确
启用 `owner_dispatch` 模式。其 API 和严格 SSH 校验仍必须真实通过。

## 验证边界

此候选保留原 PR13 应用源码与原 PR14 回滚门槛。旧基线的 10 个缺接口编译
错误是否消失，由实际 build/tests 和最终镜像 CI 证明，不修改用例来迎合结果。
完整 .NET 解决方案在独立 Cloud 已构建成功，0 warnings／0 errors。

首轮本地测试将 artifacts 放在源码树之外，导致寻找服务端／配置的用例无法定位
仓库：Domain 316/317、Server 249/262，0 skipped。全部失败原日志保留在
`/workspace/pr14-compatible-local-evidence/initial-tests-external-artifacts.log`。
测试布局已改为源码树内的独立 artifacts 路径，贴近正式 Docker 验证器布局；
没有修改应用／测试代码。正确布局重跑 Domain 317/317、Server 262/262，
0 failed、0 skipped，私有 PG 已停止；结果在 `local-source-validation.json`，
两轮日志及实际生成的 TRX 在 `local-logs/`。镜像结论由独立 CI 单独记录，
原失败不抹去。

即使最终镜像全部通过，也不能证明从现在线上版本到该候选的数据／快照兼容性，
不能替代 PR13 的 132 项验收，不能绕过 PR14 的保守差异阻断，也不是部署授权。
当前任务不部署、不重启线上服务器、不恢复数据库、不合并现有 PR。
