# S1 当前调用链与缺口

现有单元边界已经覆盖 7.999/8.000 秒和目标恢复，当前 ElementMarginalAccountingTests 也证明同瞬时 full+half 不能当作目标不可操作时长之和。原结果仅覆盖 OFFLINE，EXPERIMENT/RENDER 仍缺，不能因同名断言补齐层次。

新工具需要通过 BattleRoom.PlayCards 驱动目标，以实际 CombatResolution.StunSeconds 和目标 StunRemaining 核验全/半/零，再以 room.Advance 触发过期。所有状态 JSON 原文只在首个 seed 的展示向量保留，其他原始行保留状态哈希及全部控制事件指标；分析要核验 gzip CRC、原文哈希、行数、每个职业/等级/seed 的唯一性。

PVP 新目标的窗独立，工作副本执行控制后需真实 Room JSON 重建并 EndDuelSurvived，玩家和 PVE 怪物快照原样返回。新工具不接受客户端预测来裁决实际时长，不把请求或递减后时长误称为新增 union。
