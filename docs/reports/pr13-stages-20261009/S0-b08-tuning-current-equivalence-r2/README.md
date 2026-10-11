# B08.3 current selected-source equivalence R2 开发阶段

R2 比较器、云运行器与预注册已完成开发；20 项合成元数据检查和独立只读代码审查通过。本报告没有 R2 实际云端比较结果，R2 等价性与正式验收均未通过。432 场是预注册完整范围，不能作为已完成数量。

R1 已在云端生成两套原生输出：旧来源与当前 selected runtime 各 6 场，共 12 场。两套原独立 oracle 均通过，各自的 4 项原负对照均拒绝错误输入。R1 比较器随后在 `cast.Actual.BattleId` 的独立随机 UUID 上拒绝比较。原 driver 的 `families_completed=0`、空 `comparisons` 和 `total_unique_native_encounters=0` 保留在原件中；这些字段来自成功比较进度，不能解读成没有执行原生测试。本报告另列来自原生／validator 元数据的实际 12 场，不修改原失败记录，也不称 R1 等价性通过。

`r1/failed-native-and-comparator-inspection.original.json` 保存原失败诊断，`r1/UUID-path-inspection.original.json` 保存原 UUID 路径诊断。`r1/frozen-tools/` 保留原 R1 runner、comparator、plan 及冻结证明；原件保持原 SHA 和实际字节。完整失败 raw、云／G 归档闭合由 root 单独执行和记录；本开发报告没有完整归档回执，未伪造 G 备份完成或清理通过。

R2 只允许三个明确身份路径使用限定双射：`Selected.InstanceId` 按语义卡牌、顺序与 encounter 保持稳定映射；`Actual.BattleId` 必须 UUID v7；`Actual.AttackerId` 必须 UUID v4。后两者各自按语义 family／seed／profile encounter 保持稳定且全局无别名的映射。其余 Actual 数值、equipment、state、卡牌语义、顺序、结局、scalar 类型与 decimal 值均精确一致，数值容差为 0；未知字段和其他 UUID 路径不会被统一忽略。

`r2/metadata-controls.original.json` 保存 20 项合成检查，覆盖修改 HP cost／conflict heal、卡牌与 cast 顺序、UUID 不稳定与多对一、跨 encounter 别名、实际伤害变化、类型与 decimal 差异、未知字段及非白名单 UUID。`r2/independent-review.original.json` 是 `/root/remaining_scope_audit` 的只读审查回执，审查对象 SHA 与三份 R2 ready 文件一致。合成检查与代码审查均不是 native、business oracle、云端运行或正式验收证据。

预注册要求 36 个 family 和完整两 namespace 无别名门禁，计划在原 R1 完整 G 闭合后复用其 12 场，并新增 420 场，共 432 场。复用还需完整原字节、SHA／CRC、source 与冻结预注册门禁；本报告没有授予开始或复用的实际运行通过结论，也没有代替这些云端门禁。

source 范围仅为冻结的 51 份相关 selected 输入与实际 old／current runtime 契约，不是整个 Git tree 的 source identity。原 216000 场 tuning 数据仍归属 `3a984bc64f5346b7f1d134926deec54be928a060`，没有重新标成当前 release 或混合来源，也不是已完成 current-source 全量重测。

本阶段没有改卡牌数值、提升主验收表或通过 full EXPERIMENT／MAIN／LIVE、真人体验与严格容量。`source-records.json` 记录所有原件字节锚，`manifest.json` 排除自身，成员 SHA256 和 Git blob SHA1 使用未来公开目录继承的 `docs/reports/pr13-stages-20261009/** -text` 保护后原字节。报告现位于 ignored staging，公开移动与提交由 root 决定。
