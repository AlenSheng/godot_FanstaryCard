# LOAD-01.1 独立重验：e06037f5

**独立结论：LOAD-01.1 在固定源码 `e06037f58738d0fbff86090e86d8bd06f8608e04` 满足原 OFFLINE 输入 schema 合同，可由父任务 MAIN 按 FixedWithEvidence 接受。** 本次没有写原 PR13 或 Accepted 登记；LOAD-01.2/.3/.4 保持父任务原裁决，本次12-case复跑仅为同SHA回归。

实施报告固定为 `c68bd4aadf59676096b93ce8e5a972b12575cc08` 的 `docs/reports/pr13-takeover-20260930/schema-second-e06037f5/REPORT.json`。上一版ee8的三个真实失败见独立提交 [`dac6fdbd43d9c925a696a18f9774d9392c06c302`](https://github.com/AlenSheng/godot_FanstaryCard/tree/dac6fdbd43d9c925a696a18f9774d9392c06c302/docs/reports/pr13-independent-main-20260930/ee8adcf4)。旧失败收据不可覆盖；本结论只对新固定SHA有效，不推广至其他任务、完整负载容量或后续源码。

## 实际重放

| 输入/测试 | 实际结果 |
| --- | --- |
| 原 `finite-overflow`：两个合法有限1e308，HTTP500/okFalse | 均值/min/max/p95均1e308；http count、valid latency、samples、errors全部2；invalid_metric_count=0；quality=insufficient；无异常、不丢样本、不写负载通过。 |
| 原 `archive-match-list`：cycle.started、match_id=[] | Owned status/archive归属与序号合法；归类invalid_business_match_type；明确invalid/exit3，零虚假ACK/完成，无异常。 |
| 原 `archive-type-list`：合法context、event_type=[] | 归类invalid_event_type；明确invalid/exit3，零虚假ACK/完成，无异常。 |
| 旧五例 | type=[]/{}、10**400耗时/状态时间/事件时间全部明确invalid/exit3；零未处理异常。 |
| 原12 canonical case | 12/12通过，0失败，0跳过。只重新裁.1三case。 |
| 完整原Python回归 | 122/122通过，0失败，0跳过；未filter，exit0。 |
| 五个有限同类边界 | 最大有限float pair保留正确均值、2/2分母和insufficient；match_id={}、event_type={}各invalid/exit3；合法cycle.started的match_id=None/空串均兼容且不冒充已完成。 |

所有入口使用真实 owned OS 子进程写出的JSON/JSONL，依次调用原生产 `read_owned_statuses → new_events → aggregate_window/workload_snapshot`，archive再经 `read_audit_events → reconcile_cycles`。归属/序号检查没有绕过；八个三例/边界输入均ownership/event loss为0。17个专用子进程全部由自身owner `wait()` 回收。

原三个反例使用上次byte-identical的 [probe_schema.py](probe_schema.py)，未改变输入或被测函数。[verify_replay.py](verify_replay.py) 对已保存的实际输出作严格断言，并调用固定源码的生产 `classify_stop`：archive错误返回invalid3；合法小样本诊断仍是incomplete1、passed=false。[REPLAY_CHECKS.json](REPLAY_CHECKS.json)列出每个断言与真实分类输出。没有执行需要网络的完整 `--run` CLI，不能把这些决策函数返回码描述成公网运行退出码。

probe/检查器进程exit0表示重放或断言成功，和load Passed无关。旧五例harness同样退出0来记录五个invalid3。完整argv、cwd、环境、SHA、工具版本、进程退出码和日志hash在 [COMMANDS.json](COMMANDS.json)，实际全套回归日志在 [C-PY.log](C-PY.log)。

工具链：Python3.12.14，`/workspace/relicround-env/venv/bin/python`，Linux x86_64/glibc2.41，Git2.52.0。所有命令使用同一个clean detached e060源码工作树。原canonical harness相较上一版只有固定SHA字符串更新；原检查断言、阈值和分母均未改变。五个新增边界事先写死输入、断言和5s写入deadline/15s子进程寿命/5s回收预算；没有fuzz或结果筛选。

## 原合同与metadata

原.1三类case分别验证None/list状态不异常、bool PID/NaN耗时拒绝且已知失败保留、合法/坏行混合保留合法样本并使证据无效。加上当前真实file-path反例及同类边界，已确认容器/标量校验在membership/hash之前，有限值不会因中间求和溢出终止采样，坏值不会变成0延迟或成功。`statistics.mean`替代fmean仅改变内部均值算法；同SHA全套回归保留既有合法行为。

完整schema验收基于冻结OFFLINE合同、有限确定输入和实际重放，不宣称进行了无限输入证明。此次没有发现需owner继续修补的同类反例。

实施包78个manifest文件的大小/SHA256均一致；10个source proof与e060 git blob一致，6个测试源码同样与固定SHA逐字节一致。.1任务根记录和七个阶段收据共8条记录均含canonical必填字段，null均有missing_reasons，profile_hash/algorithm_version匹配实际文件与成员源码hash。见 [STATIC_CHECK.json](STATIC_CHECK.json) 与 [SOURCE_PROOF.json](SOURCE_PROOF.json)。

实施profile hash：`36874896b02ea70ae04151ae641809af32799e51bf4a144a7087e013bd114d95`。

算法版本：`sha256:8a44f0828f6aa8436812892de2bb75012fbc12e2a07aecc95f3bf71e44bf53fd`。

计划hash仍为`5176ee139d4e632ba34469ae531ce7ec16478f356480e2d8e320cd51f3bcd703`。ee8→e060的运行变化仅两个accounting文件及两个测试文件；e060→c68实施报告commit的tools/client/server/protocol/config无变化。业务、UI、配置与协议不变。

最小依赖LOAD-11.1来源/hash和LOAD-06.4本地身份/时间/null/脱敏合同都可用；无需整个上游Accepted，不增加CI/LIVE/POSTGRES/RENDER/真人前置。S5按原合同NotApplicableWithReason。server/AGENTS已读；固定树没有根/tools AGENTS或.agents/skills，保留canonical缺server_create的既定例外；本次不做server任务。

实施报告有少量历史文档残留：S1文字仍提f812但引用的是ee8三反例；旧rollback只列一个runtime文件；先前MAIN来源URL当时为null并附原因。本独立收据已补齐正确before/after引用、上次独立提交和完整rollback范围。这些不形成额外运行门。正确rollback是整体回退独立e060代码提交，恢复两个runtime文件及两组测试，同时保留所有原始证据；未实际执行回退。

[REPORT.json](REPORT.json)仅有LOAD-01.1的完整S6 report_fields、null理由、profile/algorithm、源/命令/退出码、case输出、最小依赖、rollback和零剩余运行阻塞。推荐FixedWithEvidence接受，最终签署交父任务；Accepted登记仍未写。.2–.4的旧Accepted不重新裁决。

## 重现与发布边界

从本审查commit根目录开始，用Python3.12和新的输出目录。先取得固定对象、建立隔离工作树，再复用本包原probe与边界probe；不修改原分支：

```bash
git fetch --no-tags origin e06037f58738d0fbff86090e86d8bd06f8608e04 c68bd4aadf59676096b93ce8e5a972b12575cc08
git worktree add --detach /tmp/pr13-e060-replay e06037f58738d0fbff86090e86d8bd06f8608e04
source_checkout=/tmp/pr13-e060-replay
review_packet="$PWD/docs/reports/pr13-independent-main-20260930/e06037f5"
PYTHONDONTWRITEBYTECODE=1 python3 "$review_packet/probe_schema.py" --source "$source_checkout" --fixture finite-overflow --output /tmp/pr13-e060-finite
PYTHONDONTWRITEBYTECODE=1 python3 "$review_packet/probe_schema.py" --source "$source_checkout" --fixture archive-match-list --output /tmp/pr13-e060-match
PYTHONDONTWRITEBYTECODE=1 python3 "$review_packet/probe_schema.py" --source "$source_checkout" --fixture archive-type-list --output /tmp/pr13-e060-type
PYTHONDONTWRITEBYTECODE=1 python3 "$review_packet/probe_boundaries.py" --source "$source_checkout" --output /tmp/pr13-e060-boundaries
```

同SHA回归：在固定工作树执行 `python3 -m unittest discover -s tools/tests -v`；从c68 commit取 `schema-second-e06037f5/run_load01.py`、`reproduce_old_five.py` 到临时目录，依该实施README实际运行。完整记录和新输出的强断言脚本已附；`verify_receipt.py`保留本次原workspace依赖路径来复核原命令，不是便携运行入口。

本次小发布只增加本目录到现有私有独立审查分支，保留ee8审查目录与commit。包含非敏感报告、日志/退出码、八个最小synthetic输入、回归摘要与hash；不含旧255raw完整包、账号凭据或私人服务器数据。没有上传Library、生成新CI重跑、开PR或dispatch工作流，提交带[skip ci]。

[MANIFEST.json](MANIFEST.json)给出本小包逐文件相对路径、大小、SHA256；[MANIFEST.sha256](MANIFEST.sha256)锚定manifest。原始文件、测试源码和assertions未改。
