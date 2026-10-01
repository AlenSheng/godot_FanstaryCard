# PR13：11 Ready 项独立 MAIN / S6 验收复跑

这 11 项满足各自原合同，可交父 MAIN 按 **Accepted / NoChangeWithEvidence** 签收。33 个目标 canonical case 实际重放通过；本报告仅给出独立资格判断，没有写入原 Accepted 登记。封存入口为 `2dda41b32ba89f06d5ea722ae8b9469004940c22` 的 `BOUNDED_19_RECEIPT.json` 和 `INDEPENDENT_REPLAY_19.md`。逐 case 的 setup、expected、actual、源 SHA、profile_hash、algorithm_version、最小依赖及不适用字段原因见 `REPORT.json`。

| 任务 | 原合同关键实测 | 独立意见 |
|---|---|---|
| LOAD-02.1 | time_limit exit1；STOP 前既有业务错误保留；redline 与坏 telemetry 同时保留性能/证据失败，exit3 | 可签收 |
| LOAD-02.3 | 正常 STOP 宽限内退出；真实挂起进程满 35 秒后仅强杀自有 PID，旁观 sentinel 存活；写报告失败落 emergency 且 exit3 | 可签收 |
| LOAD-02.4 | preparation-only exit0/Prepared 未启动负载；redline exit2；invalid exit3、operator exit130 与实际调用方兼容 | 可签收 |
| LOAD-03.1 | 同毫秒 seq1/2 恰好一次；1/3 历史 gap 不被最终完整快照抹除、真 coordinator exit3；不同 PID/epoch 分别归属水位 | 可签收 |
| LOAD-03.2 | 真 Gateway/HTTP_SCHEMA 延迟请求保留发起 M cycle 和 playing/settlement phase；旧 auth 单列；legacy 无标签为 unknown | 可签收 |
| PR13-B02.1 | 三个旧 API 真实编译失败；原 20 测试意图保留；新默认和显式模式五连击抽牌/余数正确 | 可签收 |
| PR13-B02.2 | 真 Resolver 顺序/少数核心、情境向量 46/72/113、逐卡 floor12、调谐/双段及牧师普通治疗分别通过 | 可签收 |
| PR13-B02.3 | 重复 preview 的状态/RNG/deck/remainder 不变；真 C#→Godot PB 顺序；生产回调拒绝旧 revision/request | 可签收 |
| PR13-B02.4 | 真 XLSX exporter/ReadNumerics 热更只影响新房；PG 当前策略锁定；PVP→PVE 精确快照；旧字段默认及非法值先拒绝后不变 | 可签收 |
| PR13-A05.2 | A 真入 N、B 继续 M 并正常撤离；实际 OS 宿主替换恢复各自房间；旧 M GET/三次原 READY 不改 A 的 N；审计清零 | 可签收 |
| PR13-A05.3 | 同 key/body ACK 三次资产/响应相同；4 Pending 跨 SIGKILL 恢复后仅提交一次；原实例、钱包、ledger 和重复 READY 守恒 | 可签收 |

SOURCE_CHECK 和 KEY_SOURCE_PROOF 核对了固定源码字节，HARNESS_PROOF 核对原 harness/断言，BUILD_PROOF 记录本地构建 DLL 哈希。各组来源保持收据绑定：LOAD02、B02、A05 业务/UI 为 `f812879e4518fd09bf22656451cb563d62940298`；LOAD03 原工具来源为 `ee8adcf40be9aebb1330156a3524910c08225ebc`，其中业务/UI 字节与 f812 相同。没有将所有组换为一个后来 SHA。A05 canonical 装配加入原报告声明的七个测试文件；独立因果装配加入原声明九个测试文件，生产和已有断言没有被替换。精确 report commit、路径和报告哈希见 PACKETS.json。

| 实际验证 | Passed / Failed / Skipped | exit |
|---|---|---|
| LOAD02 适用 Python | 42 / 0 / 0 | 0 |
| LOAD03 同 SHA、带 .git 的独立 worktree Python | 119 / 0 / 0 | 0 |
| B02 原固定源码 Domain | 317 / 0 / 0 | 0 |
| B02 原 Pooling=false、本地自有 PG 全 Server | 291 / 0 / 0 | 0 |
| A05 原 canonical focused | 4 / 0 / 0 | 0 |
| A05 原 canonical 装配全 Server | 295 / 0 / 0 | 0 |
| A05 真 ACK-await 因果正确性断言 | 0 / 1 / 0 | **1** |

命令、实际环境、时间、退出码和 log SHA256 在 COMMANDS.json；TRX 的独立解析、计数、失败消息/stack 和原文件哈希在 SUITES.json。原配置全 Server 的两次独立阶段分别使用真实本地 PG/Program/Godot，未跳过 PG 测试。协议生成检查以及原 Godot 数值、线序和支持检查通过。LOAD02 模型时钟/遥测 fixture 明确只支持这些 OFFLINE 合同，不被当成真人负载或容量证明；LOAD03 的文件 writer、Coordinator、HTTP/Gateway 和 PB 延迟路径使用实际 owned 进程。

## A05 `.1` 反例与 `.2/.3` 隔离

原 `80687833` focused **3Pass/1Fail** 与原 causal **1Fail** 保留。当前 canonical focused4Pass、全套295Pass 均没有覆盖或改签它们。独立因果重放仍在固定 f812 的真实生产 ACK await 中失败：5473ms 乐观清除，5489ms 放行之前真实 M poll，5556ms 旧收据恢复；5572ms 放行 ACK，5706ms 真 ACK 成功且新 Bootstrap 已确认完成，旧收据仍显示。之后真下一轮 preparation 能执行。SUITES.json 保留真实失败断言，A05_CHECKS.json 保留这条轨迹和最小 raw 哈希。

`.2` 实际最小上游产物是终态 A/Committed holds/ACK 及已释放的 M 路由，这些在真进程和 PG 中存在。A 在 N、健康 B 在 M 的身份/路由/重启/撤离均实测成立，旧终态显示并不提供重新进入 M 的路由。`.3` 所需 `.2` M/N 产物也存在；三次同 ACK、Pending 跨真 SIGKILL 恢复及重复 READY 均只产生一次 gold23 ledger 和一次 owned-item movement。因果 `.1` 正确性断言失败之前，其 **causal-after 只读审计八项全零**，独立证明这条显示反例没有造成重复资产信用。

四组 canonical before/after 加因果 before/after，共 10 次原 SQL 的 READ ONLY + rollback 审计，五次 require_clear after 全部八项零；没有通过删账号/业务行来取得审计通过。Pending 门打开前真实钱包/锁和原实例不变；之后4 Committed/0 Pending。健康场景 A 从 M 到 N 后正常断线死亡会将同一实例移至 RelicPile，符合原允许的资产位置转移，不伪称 N 完成 Boss 全流程。父任务保留 A05.1 Partial；其修复应由原 owner 对真实 ACK-await/过期 poll 的显示更新资格处理，并用保留的因果断言再验。这里没有实施修复。

## 保留的非目标失败与准备问题

第一次 B02 全套额外复跑使用了审查脚本的 `Pooling=true;Maximum Pool Size=8`，偏离原 B02 `Pooling=false`，实际 **290Pass/1Fail/0Skip**。失败为 MarkRunning commit-response-loss：期望 Running，观察 Launching。此失败原命令、log/TRX 哈希、消息/stack 均保留。随后同测试在 false 和 true 各一次 focused 均通过，没有证据把失败归因于连接池。最终采用原 Pooling=false、另一个自有 PG 的完整291Pass支持本范围判断；既没有把第一次失败写成 Pass，也没有添加额外连接池验收门。

LOAD03 初次 packet 没有 prepare_fixture/三个 fixture wrapper，使用封存2dda的原 helper/wrapper 并单独记录来源哈希。初次 Python119 archive 中10项 provenance 检查依赖 .git 而报错；改在精确 ee8 干净 worktree 全119通过，没有改被测逻辑/断言。B02 初次 Godot support 因原资源 import cache 未生成返回1，执行原标准 Godot editor import 后同检查返回0；首个失败记录保留。STATIC helper 的早期 size/key 和被 harness 热更的 fixture bookkeeping 问题只修审查读取映射，原文件另行从报告 commit 还原校验；不是产品测试失败。

## 元数据、范围及复核入口

原 packet 中可取的 **710 文件**逐一 SHA256 校验；11目标的 **86条**阶段/根报告元数据按原完整 report_fields 核对，11 profile_hash 用真实 profile 文件字节重新计算，algorithm_version、case IDs、null + missing_reasons 均核对。历史 A05 1678 raw 未在 Git packet 中提供，本环境无法独立重 hash，明确记为 null + 原因；没有假称看过。这次 fresh focused、causal、whole-PG 路径、原SQL审计以及身份哈希独立建立 S6 证据，未依赖不可见历史 raw 来签收。

依赖逐项按原最小产物判断，没有要求全部上游 Accepted。LOAD02.3 所需正常 STOP/pending直到权威终态/清理上下文由真实 PG ACKSTOP 提供；LOAD02.2 的 PG timeoutSTOP 独占 partition 缺口仍保留且未被这次结果补签。未重裁 LOAD01 四项；未验收 LOAD02.2、LOAD03.3、LOAD03.4、A05.1。未签 G0–G5，未称132全收。原 OFFLINE 合同保持，所需 POSTGRES/AUDIT 实际满足，没有新增 CI/LIVE/render/人工门。

重现时先取 PACKETS.json 的精确 source 和 report commit、封存 helper，再按封存 INDEPENDENT_REPLAY_19.md 准备新的空隔离目录；保留原 harness 测试文件/断言和原 PG profile。COMMANDS.json 给实际完整 argv/cwd/env/exit。本目录 replay/*.py 是此次审查的 recorder、验证器和 PG driver，路径取独立 evidence root；driver 只启动 Unix socket/loopback disposable 本地服务，必须在新空目录使用。LOAD03 Python 回归使用精确 SHA 的独立 Git worktree，不能仅用无 .git archive 替代。A05 因果正确性重放应返回1并保留 Failed，不能以 fixture自检 ok=true 当成修复通过。

本地完整 fresh raw 位于 `/workspace/pr13-main-bounded-20261001/{load02,load03,b02,a05}/evidence`，`LOCAL_RAW_MANIFEST.json` 保存1986文件/36615256字节的路径、大小、哈希，仅留本地。公开到本私有独立 review 分支的只有这份非敏感审查文本、命令、工具/源/harness/结果哈希摘要和审查脚本，未上传全 raw、账号凭据、PB/account rows 或私人服务器数据。CLEANUP.json 确认133个记录PID均已退出、三套自有PG停止；A05停机前 owned schema0/其他client连接0；原 work 分支仍为 b39841d3 且干净。没有 PR13代码/Accepted写入、线上连接、CI重试、Library上传、合并或部署。
