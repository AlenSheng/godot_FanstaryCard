# B08.4 水属性等级 5 的后续两个原生种子块

本目录只汇总 `Mage-E1-Water-L5-B1` 与 `Mage-E1-Water-L5-B2`，要求每块完整的 1,000 个配对种子、两装备臂合计 2,000 次遭遇，以及原始 G 归档核验和云清理收据。构建器在两块完整证据齐全且各项成功之前不生成通过汇总；失败或未结束的原始数据保留，不转成 Passed。

战斗原生代码和编译 runtime 仍来自 `b0423bfe6fedc3f034ba12c8400df5ebb8713f32`。`bdced93f33415e095de5e580981e8b7cbcdd92f3` 是控制器、G 回传工具及证据管理代码的发布来源，不能重新标记原生战斗来源。恢复 runtime 的八个原始 SHA、372 个 source input hash、G 备份成员及对应的 B042 committed Git blob bytes 都重新核对；各次运行的预注册输入锚点及实际 runner SHA 另存。

两个块新增 4,000 次遭遇、2,000 个配对。cast、tick、event 总数和所有实际 outcome 都从各块原始 summary／cloud validation／raw gzip 动态核对，未沿用 B0 的数字。云端独立 validator 的四个负对照必须拒绝错误数据；本地只核验原始归档字节、成员 SHA、gzip CRC、JSONL 条数、配对身份和元数据，不运行原生游戏、战斗模拟或业务 oracle。

在既有 88 个逻辑 G 单元上，这两个单元使累计达到 90／360，G 原始数据覆盖 180,000 次遭遇及 90,000 个配对；还剩 270 块、540,000 次遭遇、270,000 个配对。成功原生执行结果的尝试数为 91：原先 B0 的原始文件丢失，其成功结果保留，另一个明确命名的恢复尝试补齐同一逻辑单元；两次原生执行不能计为两个独立逻辑块。

每块完整归档和原始事件仍保存在 G 盘 `outputs/pr13-tencent-20261009/cap-experiment-full-r2-raw/`。公开目录只保留实际结果、预注册、native summary、小型原始 manifest、cloud validation、G 与云清理收据和来源 hash。云清理收据必须与完整 G 归档的 SHA、字节和 manifest 对应，才计为已回传清理。

两个完整块回传并清理后，云端解除为这两个原生块保留的公平调度占位。`cloud-render-fair-hold-ended.json` 是解除动作的原始回执，记录 90 个逻辑 G 单元和 180,000 次遭遇；它明确未重启渲染原生任务，不能当作渲染已完成的证据。

全部 720,000 次遭遇的正式统计、用例适用性和 EXPERIMENT／MAIN 仍待完成，原验收 register 不由这两个单元升级。未改卡组、卡牌或平衡数值；守护者长对局只要仍在推进，就不因时长被当作合同失败。多人容量保持暂缓，真人体验不在当前自动测试范围内。

`manifest.json` 记录公开成员的原始二进制或 UTF-8 LF 字节；发布时必须再次核对 committed Git blob bytes，工作树 hash 不足以证明远端证据一致。
