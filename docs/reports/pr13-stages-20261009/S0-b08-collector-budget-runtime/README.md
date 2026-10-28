# PR13 B08：采集预算修订的云端构建与等价性门禁

本阶段通过腾讯云上的混合来源构建、原有 56 项 Domain 回归、三组小样本逐事件等价性检查和 G 盘完整备份门禁。正式实验仍有 270 个单元、540,000 场未在本阶段验收；MAIN 和整体任务保持未通过。

业务来源为 `b0423bfe6fedc3f034ba12c8400df5ebb8713f32`。真实混合 Git 来源为 `581cd9f74962dd61424e77c529b1259afbb39fe7`，父提交是业务来源，仅覆盖采集器与 Python 验证器两文件；这两文件的公开来源为 `66c7420532536431b906d1fdb1e68d6d3448e6b9`。372 个输入中的其他 370 个保持原字节。Domain 的 DLL、PDB、deps 三文件 SHA 与原运行时相同；Numerics DLL/PDB 新 SHA 独立列于 [构建原件](build-result.json) 与 [汇总](summary.json)。

云端比较原采集器默认 2 GiB、新采集器默认 2 GiB、新采集器显式 16 GiB 三组 Mage/E1/Water/L5/B0，复用种子 440001–440003。共执行 18 场，代表同一组 3 个配对种子，每组 6 场。每组完整保留 226 次 cast、3,190 次 tick、4,604,437 字节逐事件原文及全部 6 次胜利结局。两次等价比较中，仅 selected 卡牌 InstanceId 使用持续一致的语义双射；其余字段、装备、状态、次序和结局精确相同，未使用数值容差或全局 UUID 删除。12 个原业务 oracle、6 个新采集元数据及 4 个等价性负对照均被拒绝。

未显式声明时累计事件原文预算仍为 2 GiB；新选项允许声明 128 MiB 至 32 GiB，后续正式修订预登记为 16 GiB。128 MiB 分片及 encounter ledger 上限保持不变，512 MiB 压缩持盘预算独立。小样本实际原文仅约 4.6 MB，因此本报告没有完成超过旧 2 GiB 上限的正式单元，也没有把旧预算失败改写为通过。长时间但仍推进的战斗不据此判为平衡性失败，卡组和数值没有修改。

[原预登记](preregistration.original.json)的 `passed:false` 和等待状态原字节保留；它们记录预登记时点。本阶段以独立 [构建](build-result.json)、[TRX](test-results/cap-runtime-recovery.trx)、[pilot](pilot-result.json)、[等价性](equivalence.json) 和 [G 收据](G-backup/local-backup-receipt.json) 证明门禁已满足。原 90 个逻辑正式单元、91 次成功原生执行及 180,000 场正式分母保持原来源和预算主张；本次小样本未加入正式分母。

G 私有归档为 26,414,902 字节，1005 个原始成员全部 SHA 复核；逐事件 gzip CRC、原文 SHA 和计数完整。源码树、Git bundle、程序集和私有归档保留在 G 盘，不发布到本报告。原执行 runner SHA `56b131dbfcb769f474fc3772115d2c6c1becc86c43bc12ecb50550264503cf26` 在 [不可变 runner 证明](frozen-runner-proof.json) 中由 inputs 与 G 成员相互锚定。

独立存储助手仅补充 exact 只读监控容器检查例外，未重跑构建、回归、小样本或等价性，也未修改原 runner 和 inputs。G 备份完成后仅清理云端通过的构建 tmpfs 27,344,896 字节；持久源码、运行时、三组小样本及失败原件保留。NuGet 完整 G 备份后另清理 207,843,328 字节，健康端点前后均为 200；未来 .NET 构建须先完整恢复并验证该缓存。独立原始证明位于 [storage](storage/)，完整存储验收见 [checkpoint-10](../evidence-storage-20261010/checkpoint-10/)。本机只做元数据、归档和字节验证。

所有原件以 `write_bytes` 原字节复制，新生成文本采用 LF；本地传输辅助收据原有的 11 个 CRLF 原样保留。仓库对本目录 `-text`，因此 [manifest](manifest.json) 的字节数、SHA256 和 Git blob SHA 对应提交字节，manifest 本身不递归列入。原 inputs 中准备时点的 `private-test-source` 及构建/pilot 的未授权正式调度标志同样保持原件，不用事后状态重写历史证据。
