# PR13 B08.4：首个 R3 BOSS 正式单元

`Mage-BOSS-Fire-L0-B0` 已在腾讯云完成 1,000 个配对种子、2,000 场原生执行；完整 G 盘备份验收及对应云端 raw 清理均已闭环。本阶段只验收这个正式单元，完整实验统计、MAIN 和整体任务继续待验收。

种子 440001–441000、每臂 1,000 样本均按原完整矩阵执行，没有缩样。保留 110,973 次 cast、1,607,600 次 tick、共 1,718,573 条逐事件记录和全部 2,000 次 Victory 结局。4 个独立业务 oracle 与 3 个采集元数据负对照全部被拒绝，详细分母与控制原件见 [validation](validation.json)。结局分布仅描述这个单元，不作跨矩阵平衡性结论。

实际混合来源 `581cd9f74962dd61424e77c529b1259afbb39fe7` 以业务来源 `b0423bfe6fedc3f034ba12c8400df5ebb8713f32` 为父提交，仅覆盖采集器和验证器两文件；公开采集工具来源为 `66c7420532536431b906d1fdb1e68d6d3448e6b9`。372 输入中的其余 370 个原字节不变，Domain 三个运行时文件与原版本相同，Numerics 新来源单独记录。构建、56 回归、三组小样本等价性和运行时 G 备份门禁沿用 [S0 证据](../S0-b08-collector-budget-runtime/)，本阶段 [来源门禁证明](source-gate-proof.json) 复核五个精确原件 SHA。

完整逐事件原文为 2,390,577,849 字节，超过旧默认 2 GiB 243,094,201 字节。因此旧 2 GiB 合同明确未满足；本次通过的是新采集器预登记的显式 16 GiB 累计原文预算。18 个事件分片各不超过原 128 MiB 上限，encounter ledger 为 2,804,906 字节，512 MiB 压缩持盘预算独立，实际持盘 100,942,518 字节。没有删减事件、修改卡组或战斗数值，也没有把旧预算失败改写为通过。长对局的预算需求仍属于证据收集条件。

[实际 G 收据](G-backup/local-backup-receipt.json) 证明 84,121,788 字节私有归档的外层 gzip CRC、35 个原件成员 SHA，以及 19 个内层 gzip 的 CRC、原文 SHA、配对种子、全部事件和 encounter 计数均完整。原始压缩事件和私有归档继续保存在 G 盘，不加入公共 Git 报告。[collector-proof 原件](metadata/collector-proof.json) 完整保留 native manifest、summary、validation 和三者原字节 SHA。

完整 G 验证完成后，[云端清理原件](cloud-cleanup-receipt.json) 锚定同一 archive/manifest/receipt SHA，清理该单元 raw 输出，移除 allocated 101,007,360 字节，实测根盘可用空间增加 101,015,552 字节；来源、编译运行时和元数据保留。原 [result](metadata/result.json) 中 `G_backup_verified:false` 是传输前历史状态，保留原字节；本阶段验收使用独立 G 收据与清理证明，不覆写历史原件。

在本单元闭环时，旧来源 90 个逻辑单元及原 91 次成功原生执行保持原有来源与预算主张；新增混合来源 1 个单元后，总计 91 个 G 验证逻辑单元、92 次成功原生执行、182,000 场正式分母（91,000 pairs）。360 个正式单元范围不变，尚余 269 个单元、538,000 场；后续单元不由本阶段验收，小样本也不计入正式分母。

原件全部以 `write_bytes` 保留原始字节，新生成文本为 LF，仓库本报告目录使用 `-text`。[manifest](manifest.json) 的 SHA256、字节数与 Git blob SHA 对应实际提交字节，manifest 不递归列入自身。本地没有运行原生业务或业务 oracle，只核对已有备份证明和不可变字节。
