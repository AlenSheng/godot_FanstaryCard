# S1 现行统计入口与证据缺口

CombatExperience 使用实际 BattleRoom、CombatResolver、CombatDeck、当前生成地图与真实怪物，策略只读可见状态，现有实际手牌差和自然抽牌统计可复用。现有构筑是 default/theme-single-swap，不覆盖五系 Green 调节的单卡对照；现有 TargetControlSeconds 为“任一目标被控”的 100 ms 采样值，需另记按目标的精确不可操作时间并集。

新入口不再切换职业候选，只有一张 Green 调节牌不同，其他预算一致。基线移入 Green 调节是明确的实验构筑，不重标当前默认牌组。请求抽牌和获得牌数分列，蓄能转抽与即时请求来源要明确；治疗/盾必须对照实际提交前后，不拿面板数值替代上限损失。

原生 ElementMarginalAccountingTests 覆盖请求/实际 draw、重叠控制、满血满盾的离线边界，仍不能替代全量配对 EXPR 或真实 RENDER。B08.1 当前三层证据已齐，保持 ReadyForAcceptance；本轮只使用其控制/冻结合同输入，不提前签 MAIN 或整个父任务。
