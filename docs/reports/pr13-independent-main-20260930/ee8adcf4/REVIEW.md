# PR13 LOAD-01 独立 OFFLINE 审查（2026-09-30）

修复前五个异常已实际复现；固定修复源码的原 12 case 和完整 Python 119 tests 均通过，旧五例全部转成明确 invalid/exit3。另三个有限 schema 反例通过真实 owned status/audit 文件入口实际复现未处理异常。因此 LOAD-01.1 不满足完整输入 schema 合同，不能因 12/12、119/119 或旧五例转绿而签通过。

LOAD-01.2–.4 的各自合同与最小依赖产物已核实，未发现直接违约，可以由父任务 MAIN 裁决接受或 NoChangeWithEvidence。本报告只给独立审查意见，没有写原任务的 Accepted、register、PR 或业务代码。

| 子项 | 原 case | 独立完整合同意见 | 依据/缺口 |
| --- | --- | --- | --- |
| LOAD-01.1 输入 schema | 3/3 Passed | Failed，不能 Accepted | 两个合法有限 duration_ms=1e308 的可表示均值发生 fsum 中间溢出；archive match_id=[] 和 event_type=[] 触发未处理 TypeError。违背“所有负例有分类，采样函数不异常退出”。 |
| LOAD-01.2 唯一进程归属 | 3/3 Passed | 可由 MAIN 接受 / NoChangeWithEvidence | 本轮归属字段先验过滤；同 PID 新 epoch、外部 run 不计人数；真实 exit0 尾部三事件保留，最终 ACK=completed=1，alive/online=0。 |
| LOAD-01.3 拆分负载人数 | 3/3 Passed | 可由 MAIN 接受 / NoChangeWithEvidence | 活着且新鲜但离线：room_state=1、active=online=0；成功退出在线0；server_confirmed_in_room=null 并有缺来源说明。spawned 对应 runner clients=len(processes)，alive/fresh/online/room/active 分列，各采样截止点明确。 |
| LOAD-01.4 真实进程反例 | 3/3 Passed | 可由 MAIN 接受 / NoChangeWithEvidence | 真子进程写文件；慢启动宽限内不 missing；真实 exit7 定位 owned failed_process；反事实墙钟跳变不影响单调宽限，receipt+31001ms 陈旧状态不在线；全部回收。 |

这里的依赖按最小产物检查：LOAD-11.1 的 source/hash provenance、LOAD-06.4 的本地字段/时间/缺失/脱敏合同均可用。.2 使用身份过滤与启动台账，.3 使用这些归属输入及人数定义，.4 使用真实启动和接收单调时钟接缝。没有要求整个上游先 Accepted，也没有因 .1 的数值/业务键 schema 缺陷自动拒绝 .2–.4。它们的通过意见不替代整个 coordinator 的完整 schema 安全裁决。

## 固定来源与边界

- 被测修复源码：`ee8adcf40be9aebb1330156a3524910c08225ebc`，detached 工作树 `/workspace/pr13-main-review-fixed`。
- 被测修复前源码：`f812879e4518fd09bf22656451cb563d62940298`，detached 工作树 `/workspace/pr13-main-review-before`。
- 新报告包：`d9f957cbd5ae4a1145ebc4d701baddfe8211708c` 的 `docs/reports/pr13-takeover-20260930/schema-safety-ee8adcf4/`。
- 旧报告包：`3c9aaa96fdef4a0a0c0fc1b5e99c4faaefcdeb84` 的 `docs/reports/pr13-takeover-20260930/offline-acceptance-f812/load01/`。
- canonical 计划 SHA256：`5176ee139d4e632ba34469ae531ce7ec16478f356480e2d8e320cd51f3bcd703`。
- 原始工作区保持 `work` 分支、`b39841d3f5191c11c9e51c7e6875490789aba53c`、clean。两个被测工作树也 clean；源码/测试/断言未修改。
- `server/AGENTS.md` 已读；两个固定源码树不存在根 AGENTS.md 或 `.agents/skills`，也没有 tools 范围 AGENTS.md。server_create 缺失例外已经写在 canonical `state_contract.server_guidance`；本次不改 server，没有引入 dotnet 或其他额外验收门。
- 合同四子项 profiles 均仅 `OFFLINE`，S5 为 `NotApplicableWithReason`。只运行隔离本地 fixture、纯函数和轻量进程；没有接测试服、重试 GitHub CI、部署、合并或上传 Library。

修复前到修复后仅四个有关运行/测试文件变化：`tools/gameplay_load_validation.py`、`tools/pr13_runtime_evidence.py` 及各自回归测试。修复 SHA 到报告 commit 的 tools/client/server/protocol/config 没有变化。业务、协议、UI 和配置字节没有变动。

## 实际执行及关键输出

工具链经 `source /workspace/relicround-env/activate.sh` 验证：Python 3.12.14，实际 executable `/workspace/relicround-env/venv/bin/python`，Linux x86_64/glibc2.41，Git 2.52.0。完整 argv、cwd、SHA、时间、版本、进程退出码、日志 SHA256 在 [COMMANDS.json](COMMANDS.json)。

| 执行 | 实际结果 | 证据 |
| --- | --- | --- |
| 固定源码 `python -m unittest discover -s tools/tests -v` | 119 tests，0 failure，0 skip，exit0 | [C-PY.log](C-PY.log) |
| 报告 commit 原封不动的 `run_load01_acceptance.py` | 12 executed / 12 Passed / 0 failed / 0 skipped，exit0 | [cases.jsonl](load01/cases.jsonl)、[report.json](load01/report.json) |
| 原封不动的 `reproduce.py` 在修复前 SHA | 2 TypeError + 3 OverflowError，5/5 子进程回收 | [schema-before/REPORT.json](schema-before/REPORT.json) |
| 同一个 `reproduce.py` 在固定修复 SHA | 0 未处理异常、5 明确 invalid 决策、各 exit3，5/5 回收 | [schema-after/REPORT.json](schema-after/REPORT.json) |
| 新增三个独立小反例 | 1 OverflowError + 2 TypeError，各探针进程 exit1 | [FINDINGS.json](FINDINGS.json) |
| 两个正常对照 | 两个 1e100 HTTP 耗时、合法 archive cycle.started 均完成，exit0 | [finite-control](counterexamples/finite-control/receipt.json)、[archive-control](counterexamples/archive-control/receipt.json) |

原五例是 telemetry.type=[]、telemetry.type={}、duration_ms=10**400、now_unix_ms=10**400、archive at_unix_ms=10**400。修复前异常位置分别为 aggregate_window、workload_snapshot、reconcile_cycles；修复后没有异常且坏值没有变成成功或0延迟。

schema 重放 harness 的进程 exit0 表示成功记录结果，和 load Passed 无关。五个 invalid/exit3 是 `classify_stop` 返回的明确判定；没有宣称完整生产 CLI 实跑的 exit3。新增反例的 exit1 则是独立探针在相同生产 helper 调用路径上的未捕获异常。没有访问网络来执行完整 `--run` CLI。

真实成功退出子进程 PID908、exit0；status→new_events 保留三个本轮 lifecycle 事件，archive 无错误，最终 completed_cycles=acknowledgements=1，ownership_invalid=lost=0，alive=online=0。慢启动 PID910 写入前 missing=[]、写入后 online1；PID944 真实 exit7 定位 failed_processes=['owned']、online0；PID946 在反事实墙钟0/向前跳变下均保持单调宽限，陈旧后 stale=['owned']、online0。新的 epoch 注入是在同一实际 PID 上更改归属 epoch，未宣称操作系统实际回收重用 PID，也未修改宿主时钟。

四个 canonical 子进程、修复前后十个 schema 子进程、五个新增探针/正常对照子进程，共19个专用进程均 `wait()` 回收。119 tests 内原有进程清理断言同样通过；未修改断言或替换被测函数。

## 三个已复现的缺陷

1. `finite-overflow`：真实子进程写两个 `duration_ms=1e308`、status500/okFalse 的合法 HTTP 样本，operations 与 telemetry 完全对应，event_seq=1,2。reader 接收一个 owned status，ownership_invalid=event_loss=0，`_number` 两次均 true。`aggregate_window → latency → summarize → statistics.fmean` 在 `tools/gameplay_load_validation.py:18` 抛 `OverflowError: intermediate overflow in fsum`。两个样本的均值1e308本身可表示；canonical 只规定有限值，未规定额外的耗时上限，不能事后以新上限排除此例。原始 [status](counterexamples/finite-overflow/client.json.status.json)、[receipt/traceback](counterexamples/finite-overflow/receipt.json)、[stderr](finite-overflow.log)。

2. `archive-match-list`：owned identity、cycle_id、时间、序号均合法，event_type='cycle.started'、match_id=[]。archive reader 接收1行且 archive_errors=[]，窗口和人口取样正常；`reconcile_cycles → derive` 在 `tools/pr13_runtime_evidence.py:135` 的 `seen.add(business_key)` 抛 `TypeError: unhashable type: 'list'`。当前 match_id 类型检查仅作用于 ACK/completed，cycle.started 的坏类型仍到达 hash key。原始 [JSONL](counterexamples/archive-match-list/client.json.telemetry.jsonl)、[receipt/traceback](counterexamples/archive-match-list/receipt.json)、[stderr](archive-match-list.log)。

3. `archive-type-list`：owned identity、cycle_id、match_id、时间、序号合法，event_type=[]。同样在真实 archive reader 接收后、相同 `seen.add(business_key)` 处抛 TypeError。原始 [JSONL](counterexamples/archive-type-list/client.json.telemetry.jsonl)、[receipt/traceback](counterexamples/archive-type-list/receipt.json)、[stderr](archive-type-list.log)。

三例都没有产生 invalid-data classification，classification 保留 null。探针 finally 回收自己的子进程后继续传播异常；记录的探针 exit1 和 status writer 清理 exit-15 分列。reviewer 仅生成输入、调用原函数和记录输出，没有修改被测实现或断言。

owner 建议：AG-01 与 `pr13_runtime_evidence.py` 所属 owner 协調。数值聚合需要明确、可测试的有界或抗溢出方案，并保留已知失败/请求分母；所有参与 business key 的字段需要在 hash 之前校验，允许 cycle.started 合同中的合法可选/空匹配上下文，但不能把 list/dict 偷转为有效字符串。补真实 owned status/archive 回归及最终无异常 invalid 路径，再由 MAIN 独立重放。此次验收没有自行修复。

修复报告的 rollback 文本目前只列恢复 `gameplay_load_validation.py`；`pr13_runtime_evidence.py` 同样发生过 guard 变化，建议 owner 一并写明完整代码/测试回滚范围。这是文档复核意见，不是额外的线上或人工条件。

## 证据与 metadata 核验

旧包67个 manifest 条目的长度/ SHA256全部一致，10个 source proof 均与 f812 git blob一致；最终run-04的4 status + 4 JSONL + 4 child.log共12份 raw存在且已逐一 hash核对。新包75条 manifest也全部匹配，10个 source proof与固定源码一致。

新报告四个任务根记录和28条 S0–S6阶段记录均有 canonical必填字段；null字段都有 missing_reasons。新包 profile_hash实测为 `605dc5011f0a4f5e4d7fc74c1ec6fadc82aa5b8b3bcf790f6e17439bfc92d8b5`；algorithm_version对应 `sha256:03c0d12abe73045a7aea42ace2d14a3343aac9057d6437d87c90002b5ee6acfd`，其两个源码成员hash与固定源码一致。详见 [STATIC_CHECK.json](STATIC_CHECK.json)。metadata完整只能证明报告结构及来源可核验，不能覆盖上面的新运行缺陷。

本次 [REPORT.json](REPORT.json) 的每子项同样有完整report_fields、不适用值为null并附原因、独立profile_hash、命令/版本/退出码、owner与解除条件。原始源码及6个测试文件共16个文件与固定git blob一致，见 [SOURCE_PROOF.json](SOURCE_PROOF.json)。全部本地交付文件在 [MANIFEST.json](MANIFEST.json) 列出相对路径、大小与SHA256。

## 重放

使用干净、精确 SHA 工作树；从报告 commit 取原始两个 harness。输出路径必须新建。以下环境/路径是本次实际来源，完整原始 argv另见COMMANDS.json：

```bash
source /workspace/relicround-env/activate.sh
cd /workspace/pr13-main-review-fixed
PYTHONDONTWRITEBYTECODE=1 python -m unittest discover -s tools/tests -v
PR13_SOURCE_ROOT="$PWD" PYTHONDONTWRITEBYTECODE=1 python /workspace/pr13-main-review/receipts/new/docs/reports/pr13-takeover-20260930/schema-safety-ee8adcf4/run_load01_acceptance.py --output /tmp/pr13-review-load01-new
PYTHONDONTWRITEBYTECODE=1 python /workspace/pr13-main-review/receipts/new/docs/reports/pr13-takeover-20260930/schema-safety-ee8adcf4/reproduce.py --source "$PWD" --output /tmp/pr13-review-schema-new
PYTHONDONTWRITEBYTECODE=1 python /workspace/pr13-main-review/probe_schema.py --source "$PWD" --fixture finite-overflow --output /tmp/pr13-review-finite-new
PYTHONDONTWRITEBYTECODE=1 python /workspace/pr13-main-review/probe_schema.py --source "$PWD" --fixture archive-match-list --output /tmp/pr13-review-match-new
PYTHONDONTWRITEBYTECODE=1 python /workspace/pr13-main-review/probe_schema.py --source "$PWD" --fixture archive-type-list --output /tmp/pr13-review-type-new
```

修复前五例把 `--source` 换成 f812精确工作树。新增三个反例在本固定源码预期各退出1并产生traceback；未来修复后应有明确分类或安全聚合，不能仅把探针异常吞掉。审查结论和原任务最终Accepted仍由父任务裁决。
