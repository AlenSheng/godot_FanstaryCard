# B08.4 完整统计工具开发阶段

本阶段完成完整统计工具与云端隔离运行器开发。20 项合成元数据负对照、10 项合成存储／状态控制、5 类实际原件元数据门禁通过。全量 360 个逻辑单位尚未齐全，完整统计没有运行，也没有统计结果或 MAIN 验收通过结论。

公共工具为 `tools/pr13_cap_full_statistics.py` 和 `tools/cloud/pr13/cap_full_statistics.py`，分析预注册为 `docs/plans/PR13_B08_CAP_FULL_STATISTICS_20261011.json`。原始静态快照记录了这三份文件的实际字节 SHA；阶段生成时再次核对，源码没有被重新标记成原生运行证据。

`verification/static-check.original.json` 保存原静态回执和 20 项控制结果。`verification/storage-status-controls.original.json` 保存 10 项合成控制结果：精确完整 ID 的只读根目录监控允许通过，其 RW、父目录、短 ID／错 identity 等不能绕过绑定门禁；缺少 MainPID、非零 systemctl 返回、未加载单位或单位身份不同均不能被视为权威终态。这些检查均未调用真实云端命令。

`actual-metadata/metadata-audit.json` 与目录内原件记录五份已有证据的元数据核验：旧原 O1、命名的 Water 缺 raw 独立恢复、r2 Water B1、r2 Water B2、首个 r3 Boss Fire B0。五份原件分属旧原、恢复、r2、r3 四种来源格式；r2 以两个实际单位核验，所以回执列出五个门禁单位。核验覆盖原 JSON、SHA、冻结 source/runtime 及 G／cloud-cleanup 收据链。原外层归档和完整原事件的 CRC 验证沿用既有 G 原收据；本开发阶段没有重新运行业务 oracle、原生采样或统计，也不增加已完成逻辑单位数。

`source-records.json` 记录每份公开原件的原路径、字节数与 SHA。`raw-on-G-anchors.json` 记录五份原 encounter gzip 和完整归档的 G 盘字节锚。完整 gzip、逐事件 JSONL、归档和私有执行辅助文件继续保留在 G 盘，没有复制进本阶段 Git 报告。

正式运行要求一次齐全的 360 单位、120 分层、每层 3 block、720000 场／360000 配对，以及 361 次成功原生执行的对账。后一个数量包含缺 raw 的原成功 B0 和独立恢复两次执行，仍只形成一个逻辑配对单位。90 个旧 B042 单位保留 v1 与原 2 GiB 预算，270 个新混合来源单位保留实际冻结 v2 及显式 16..32 GiB 预算，不替换来源或减少样本。

所有实际业务数值和描述统计计算只允许在腾讯云只读输入、无网络的有界容器中执行。运行器提供 `prepare`、`run`、`status`、`prepare-delivery`、`cleanup` 阶段，并要求明确的 dataset、分析预注册、正式计划和工具 Git 来源字节锚。合成检查与实际元数据核验不构成这些云阶段的运行通过证据，云端内存／耗时／输出预算尚未在完整数据上验证。

输出只描述逐分层的全部原数值、全部配对结局和实际独立验证的 case 分母；没有显著性检验、效果阈值、卡组削弱或因果结论。L5 的 T01 capped 和 L0 below-cap 分开，T02／T03 缺少实际正案例保留 Gap，不能用零盾案例代替或以 N/A 通过。完整统计、正式 case 闭合、EXPERIMENT／MAIN／LIVE、50／100 容量与真人体验均未由本开发阶段授予通过；原主验收表未被提升。

本目录沿用仓库现有 `docs/reports/pr13-stages-20261009/** -text` 原件保护规则。`manifest.json` 排除自身，逐成员 SHA256 与 Git blob SHA1 均依据保护后的原始字节计算，供发布时再次核对将提交的 Git blob。
