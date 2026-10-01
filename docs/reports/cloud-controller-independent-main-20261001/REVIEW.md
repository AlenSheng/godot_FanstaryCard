# 最小部署控制器独立有界验收

**控制器组件可签 Passed**。固定 release `65361bcc27c51c28651c86c5dbba4f083a9b39e0`、main stub `1517f9fae8d865b8d663fa27d9fd38e95cb03d28` 在两个独立 detached sparse worktree 实测；原 work 分支 b39841d3 保持干净。参考报告固定于 `249297a17411b87de37303ef60d286ed83ac20e5`。未修改被测源码或断言。

实际原 41 controller tests：41Passed / 0Failed / 0Skipped，exit0。测试涉及真实本地文件、模拟子命令、真实受控 Python 子进程/stdio 握手、事务失败补偿和授权/白名单判定；API/SSH/镜像操作按原测试 patch/fixture 模拟，不能称实际 SSH 或部署成功。

actionlint 1.7.7 对 release Cloud、旧 Numerical、release deploy 及 main registration 四 workflow 均 exit0，无诊断。安装包 SHA256 与候选 workflow 的固定 `023070a287cd8cccd71515fedc843f1985bf96c436b7effaecce67290e7e0757` 一致。使用原 `-shellcheck=` 配置，没有冒称运行 ShellCheck；另13 Python AST和5 Bash `bash -n` 均通过。main stub40行、六输入与release一致，permissions空，唯一job恒`${{ false }}`，没有checkout/secret/Environment。

独立 fixture 实际调用候选 `export_evidence.py` CLI 和 GITHUB_OUTPUT，ZIP 只有 `version.txt`、`import.log`、`numerics.log`、`evidence-inventory.json`；三报告逐字节/哈希保持。原旧版不生成的五个 `preview-parity/{input.json,results.json,manifest.json,server.log,client.log}` 在 inventory 的 missing 明列，无 rejected。不输出 runtime/debug.keystore、`.env` 或其他非白名单路径；这些私有路径仅为此次本地合成 sentinel，并非读取真实凭据。

分别去掉 exporter 的 profile/source/destination，真实 CLI 各 exit2。完整合成 dispatch context 的生产 preflight为exit0；分别去掉 PR_NUMBER、COMMIT_SHA、CONFIRM_SOURCE_SHA、CONFIRM_RESTART、ROLLBACK_BASELINE_SHA、CONFIRM_ROLLBACK_COMPATIBILITY，真实子进程各exit1，均不生成preflight/GITHUB_OUTPUT。此补充探针只 patch固定 API回复，不修改生产验证逻辑、不接真实 API；失败异常/命令退出均保留在本地 evidence。

REPORT.json 包含范围和未验项，COMMANDS.json及 evidence/*.command.json 给原始argv、cwd、精确SHA、版本、耗时、exit和log哈希；SOURCE_HASHES.json覆盖release24改变路径/main1路径的Git blob和SHA256，实际参与测试的worktree文件与源字节一致。FIXTURES.json给子命令、ZIP成员和三报告哈希；MANIFEST.json给小审查产物清单。

这次只签控制器组件。**完整应用回归、最终镜像、真实SSH、实际部署、真实保护API及集成后workflow UI可发现性仍未验，application_deployable=false**。已知旧Domain.Tests十项编译错误未重跑，Domain库编译也未在本有界审查中重验；没有跳过/弱化镜像或Rooms门槛，也未套用其他SHA的应用证据。用户授权的最小集成由父协调执行，本任务未merge、push release/main、触发CI、改账户/权限/预算/变量、读取secret、接服务器或部署。小报告仅本地保存。
