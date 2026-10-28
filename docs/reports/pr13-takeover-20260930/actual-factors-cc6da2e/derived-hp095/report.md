# PR13 遭遇原样本分层汇总

来自输入逐战样本；超时、死亡和错误均保留。候选未启用。

共 216,000 条，运行错误 0 条。各层实际种子块及样本预算见 JSON；分位数从原始样本重算。

少于三个互不重叠种子块或任一块少于1000配对seed时，样本预算为 Inconclusive。预算满足不保证精度；未提供预登记主要终点及多重比较方案，候选推荐为 NotEvaluated。
全结果观测时长保留截止/死亡；胜局时长只描述胜局。胜局数不足全体开战样本的95%秩、删失仍可能改变该秩或存在错误时，全体击杀时间 P95 记为不可识别；不能由胜局 P95 推断。

默认裸装、直接进入指定遭遇的离线模拟；不代表合法完整探索、联网容量或真人体验。Boss 层也不代表完成装备准备后的难度。

| 职业/武器/场景/策略/规则 | N | 胜/死/超时 | 全结果观测秒 P50/P95 | 最长无有效动作秒 P95 |
| --- | ---: | --- | --- | ---: |
| Guardian/0/default/BOSS/baseline_all_hand/Baseline | 3000 | 0/3/2997 | 300.0/300.0 | 4.0 |
| Guardian/0/default/BOSS/baseline_all_hand/BaselinePairedControl | 3000 | 0/3/2997 | 300.0/300.0 | 4.0 |
| Guardian/0/default/BOSS/basic/Baseline | 3000 | 0/9/2991 | 300.0/300.0 | 12.0 |
| Guardian/0/default/BOSS/basic/BaselinePairedControl | 3000 | 0/9/2991 | 300.0/300.0 | 12.0 |
| Guardian/0/default/BOSS/build/Baseline | 3000 | 0/68/2932 | 300.0/300.0 | 12.0 |
| Guardian/0/default/BOSS/build/BaselinePairedControl | 3000 | 0/68/2932 | 300.0/300.0 | 12.0 |
| Guardian/0/default/E1/baseline_all_hand/Baseline | 3000 | 0/0/3000 | 300.0/300.0 | 4.0 |
| Guardian/0/default/E1/baseline_all_hand/BaselinePairedControl | 3000 | 0/0/3000 | 300.0/300.0 | 4.0 |
| Guardian/0/default/E1/basic/Baseline | 3000 | 4/0/2996 | 300.0/300.0 | 12.0 |
| Guardian/0/default/E1/basic/BaselinePairedControl | 3000 | 4/0/2996 | 300.0/300.0 | 12.0 |
| Guardian/0/default/E1/build/Baseline | 3000 | 241/0/2759 | 300.0/300.0 | 12.0 |
| Guardian/0/default/E1/build/BaselinePairedControl | 3000 | 241/0/2759 | 300.0/300.0 | 12.0 |
| Guardian/0/default/O1/baseline_all_hand/Baseline | 3000 | 3000/0/0 | 60.1/64.1 | 4.0 |
| Guardian/0/default/O1/baseline_all_hand/BaselinePairedControl | 3000 | 3000/0/0 | 60.1/64.1 | 4.0 |
| Guardian/0/default/O1/basic/Baseline | 3000 | 3000/0/0 | 64.1/72.1 | 12.0 |
| Guardian/0/default/O1/basic/BaselinePairedControl | 3000 | 3000/0/0 | 64.1/72.1 | 12.0 |
| Guardian/0/default/O1/build/Baseline | 3000 | 3000/0/0 | 60.1/72.1 | 12.0 |
| Guardian/0/default/O1/build/BaselinePairedControl | 3000 | 3000/0/0 | 60.1/72.1 | 12.0 |
| Guardian/0/default/O6/baseline_all_hand/Baseline | 3000 | 3000/0/0 | 68.1/72.1 | 4.0 |
| Guardian/0/default/O6/baseline_all_hand/TargetedO6Hp095 | 3000 | 3000/0/0 | 64.1/68.1 | 4.0 |
| Guardian/0/default/O6/basic/Baseline | 3000 | 3000/0/0 | 72.1/84.1 | 12.0 |
| Guardian/0/default/O6/basic/TargetedO6Hp095 | 3000 | 3000/0/0 | 68.1/76.1 | 12.0 |
| Guardian/0/default/O6/build/Baseline | 3000 | 3000/0/0 | 68.1/80.1 | 12.0 |
| Guardian/0/default/O6/build/TargetedO6Hp095 | 3000 | 3000/0/0 | 64.1/72.1 | 12.0 |
| Mage/0/default/BOSS/baseline_all_hand/Baseline | 3000 | 0/3000/0 | 96.8/96.8 | 7.6 |
| Mage/0/default/BOSS/baseline_all_hand/BaselinePairedControl | 3000 | 0/3000/0 | 96.8/96.8 | 7.6 |
| Mage/0/default/BOSS/basic/Baseline | 3000 | 0/3000/0 | 101.8/111.8 | 11.6 |
| Mage/0/default/BOSS/basic/BaselinePairedControl | 3000 | 0/3000/0 | 101.8/111.8 | 11.6 |
| Mage/0/default/BOSS/build/Baseline | 3000 | 0/3000/0 | 101.8/111.8 | 11.6 |
| Mage/0/default/BOSS/build/BaselinePairedControl | 3000 | 0/3000/0 | 101.8/111.8 | 11.6 |
| Mage/0/default/E1/baseline_all_hand/Baseline | 3000 | 1/2999/0 | 100.0/100.0 | 7.6 |
| Mage/0/default/E1/baseline_all_hand/BaselinePairedControl | 3000 | 1/2999/0 | 100.0/100.0 | 7.6 |
| Mage/0/default/E1/basic/Baseline | 3000 | 35/2965/0 | 110.0/120.0 | 11.6 |
| Mage/0/default/E1/basic/BaselinePairedControl | 3000 | 35/2965/0 | 110.0/120.0 | 11.6 |
| Mage/0/default/E1/build/Baseline | 3000 | 602/2398/0 | 110.0/120.0 | 11.6 |
| Mage/0/default/E1/build/BaselinePairedControl | 3000 | 602/2398/0 | 110.0/120.0 | 11.6 |
| Mage/0/default/O1/baseline_all_hand/Baseline | 3000 | 3000/0/0 | 36.1/40.5 | 7.2 |
| Mage/0/default/O1/baseline_all_hand/BaselinePairedControl | 3000 | 3000/0/0 | 36.1/40.5 | 7.2 |
| Mage/0/default/O1/basic/Baseline | 3000 | 3000/0/0 | 40.9/48.1 | 11.6 |
| Mage/0/default/O1/basic/BaselinePairedControl | 3000 | 3000/0/0 | 40.9/48.1 | 11.6 |
| Mage/0/default/O1/build/Baseline | 3000 | 3000/0/0 | 39.7/44.9 | 11.6 |
| Mage/0/default/O1/build/BaselinePairedControl | 3000 | 3000/0/0 | 39.7/44.9 | 11.6 |
| Mage/0/default/O6/baseline_all_hand/Baseline | 3000 | 3000/0/0 | 40.5/46.5 | 7.6 |
| Mage/0/default/O6/baseline_all_hand/TargetedO6Hp095 | 3000 | 3000/0/0 | 37.3/42.9 | 7.2 |
| Mage/0/default/O6/basic/Baseline | 3000 | 3000/0/0 | 46.9/54.9 | 11.6 |
| Mage/0/default/O6/basic/TargetedO6Hp095 | 3000 | 3000/0/0 | 43.7/52.1 | 11.6 |
| Mage/0/default/O6/build/Baseline | 3000 | 3000/0/0 | 44.9/52.5 | 11.6 |
| Mage/0/default/O6/build/TargetedO6Hp095 | 3000 | 3000/0/0 | 40.9/48.9 | 11.6 |
| Priest/0/default/BOSS/baseline_all_hand/Baseline | 3000 | 0/3000/0 | 209.2/229.1 | 11.6 |
| Priest/0/default/BOSS/baseline_all_hand/BaselinePairedControl | 3000 | 0/3000/0 | 209.2/229.1 | 11.6 |
| Priest/0/default/BOSS/basic/Baseline | 3000 | 0/3000/0 | 223.1/249.7 | 12.0 |
| Priest/0/default/BOSS/basic/BaselinePairedControl | 3000 | 0/3000/0 | 223.1/249.7 | 12.0 |
| Priest/0/default/BOSS/build/Baseline | 3000 | 0/3000/0 | 216.3/241.0 | 12.0 |
| Priest/0/default/BOSS/build/BaselinePairedControl | 3000 | 0/3000/0 | 216.3/241.0 | 12.0 |
| Priest/0/default/E1/baseline_all_hand/Baseline | 3000 | 0/2971/29 | 240.7/294.2 | 11.6 |
| Priest/0/default/E1/baseline_all_hand/BaselinePairedControl | 3000 | 0/2971/29 | 240.7/294.2 | 11.6 |
| Priest/0/default/E1/basic/Baseline | 3000 | 9/1952/1039 | 290.9/300.0 | 12.0 |
| Priest/0/default/E1/basic/BaselinePairedControl | 3000 | 9/1952/1039 | 290.9/300.0 | 12.0 |
| Priest/0/default/E1/build/Baseline | 3000 | 310/1828/862 | 286.9/300.0 | 12.0 |
| Priest/0/default/E1/build/BaselinePairedControl | 3000 | 310/1828/862 | 286.9/300.0 | 12.0 |
| Priest/0/default/O1/baseline_all_hand/Baseline | 3000 | 3000/0/0 | 56.1/62.9 | 10.8 |
| Priest/0/default/O1/baseline_all_hand/BaselinePairedControl | 3000 | 3000/0/0 | 56.1/62.9 | 10.8 |
| Priest/0/default/O1/basic/Baseline | 3000 | 3000/0/0 | 60.1/68.1 | 12.0 |
| Priest/0/default/O1/basic/BaselinePairedControl | 3000 | 3000/0/0 | 60.1/68.1 | 12.0 |
| Priest/0/default/O1/build/Baseline | 3000 | 3000/0/0 | 56.1/64.1 | 12.0 |
| Priest/0/default/O1/build/BaselinePairedControl | 3000 | 3000/0/0 | 56.1/64.1 | 12.0 |
| Priest/0/default/O6/baseline_all_hand/Baseline | 3000 | 3000/0/0 | 62.9/67.7 | 10.8 |
| Priest/0/default/O6/baseline_all_hand/TargetedO6Hp095 | 3000 | 3000/0/0 | 58.9/66.9 | 10.8 |
| Priest/0/default/O6/basic/Baseline | 3000 | 3000/0/0 | 68.1/76.1 | 12.0 |
| Priest/0/default/O6/basic/TargetedO6Hp095 | 3000 | 3000/0/0 | 64.1/72.1 | 12.0 |
| Priest/0/default/O6/build/Baseline | 3000 | 3000/0/0 | 64.1/72.1 | 12.0 |
| Priest/0/default/O6/build/TargetedO6Hp095 | 3000 | 3000/0/0 | 60.1/68.1 | 12.0 |

## 候选差异

+2/+4 护盾候选的收益必须分别评估；下表直接展示有效护盾变化，不能描述为全等级加强。胜局时长与全结果观测时长已分列于 JSON。

| 分层 | 胜数变化 | 有效护盾均值变化 | 60秒伤害均值变化与95%区间 |
| --- | ---: | ---: | --- |
| Guardian/0/default/BOSS/baseline_all_hand/Baseline → BaselinePairedControl | 0 | 0.00 | 0.00 [0.00, 0.00] |
| Guardian/0/default/BOSS/basic/Baseline → BaselinePairedControl | 0 | 0.00 | 0.00 [0.00, 0.00] |
| Guardian/0/default/BOSS/build/Baseline → BaselinePairedControl | 0 | 0.00 | 0.00 [0.00, 0.00] |
| Guardian/0/default/E1/baseline_all_hand/Baseline → BaselinePairedControl | 0 | 0.00 | 0.00 [0.00, 0.00] |
| Guardian/0/default/E1/basic/Baseline → BaselinePairedControl | 0 | 0.00 | 0.00 [0.00, 0.00] |
| Guardian/0/default/E1/build/Baseline → BaselinePairedControl | 0 | 0.00 | 0.00 [0.00, 0.00] |
| Guardian/0/default/O1/baseline_all_hand/Baseline → BaselinePairedControl | 0 | 0.00 | 0.00 [0.00, 0.00] |
| Guardian/0/default/O1/basic/Baseline → BaselinePairedControl | 0 | 0.00 | 0.00 [0.00, 0.00] |
| Guardian/0/default/O1/build/Baseline → BaselinePairedControl | 0 | 0.00 | 0.00 [0.00, 0.00] |
| Guardian/0/default/O6/baseline_all_hand/Baseline → TargetedO6Hp095 | 0 | -3.24 | -1.40 [-1.52, -1.29] |
| Guardian/0/default/O6/basic/Baseline → TargetedO6Hp095 | 0 | -3.65 | -0.60 [-0.81, -0.40] |
| Guardian/0/default/O6/build/Baseline → TargetedO6Hp095 | 0 | -3.24 | -1.59 [-1.77, -1.41] |
| Mage/0/default/BOSS/baseline_all_hand/Baseline → BaselinePairedControl | 0 | 0.00 | 0.00 [0.00, 0.00] |
| Mage/0/default/BOSS/basic/Baseline → BaselinePairedControl | 0 | 0.00 | 0.00 [0.00, 0.00] |
| Mage/0/default/BOSS/build/Baseline → BaselinePairedControl | 0 | 0.00 | 0.00 [0.00, 0.00] |
| Mage/0/default/E1/baseline_all_hand/Baseline → BaselinePairedControl | 0 | 0.00 | 0.00 [0.00, 0.00] |
| Mage/0/default/E1/basic/Baseline → BaselinePairedControl | 0 | 0.00 | 0.00 [0.00, 0.00] |
| Mage/0/default/E1/build/Baseline → BaselinePairedControl | 0 | 0.00 | 0.00 [0.00, 0.00] |
| Mage/0/default/O1/baseline_all_hand/Baseline → BaselinePairedControl | 0 | 0.00 | 0.00 [0.00, 0.00] |
| Mage/0/default/O1/basic/Baseline → BaselinePairedControl | 0 | 0.00 | 0.00 [0.00, 0.00] |
| Mage/0/default/O1/build/Baseline → BaselinePairedControl | 0 | 0.00 | 0.00 [0.00, 0.00] |
| Mage/0/default/O6/baseline_all_hand/Baseline → TargetedO6Hp095 | 0 | 0.00 | -6.00 [-6.00, -6.00] |
| Mage/0/default/O6/basic/Baseline → TargetedO6Hp095 | 0 | 0.00 | -6.00 [-6.00, -5.99] |
| Mage/0/default/O6/build/Baseline → TargetedO6Hp095 | 0 | 0.00 | -6.00 [-6.00, -5.99] |
| Priest/0/default/BOSS/baseline_all_hand/Baseline → BaselinePairedControl | 0 | 0.00 | 0.00 [0.00, 0.00] |
| Priest/0/default/BOSS/basic/Baseline → BaselinePairedControl | 0 | 0.00 | 0.00 [0.00, 0.00] |
| Priest/0/default/BOSS/build/Baseline → BaselinePairedControl | 0 | 0.00 | 0.00 [0.00, 0.00] |
| Priest/0/default/E1/baseline_all_hand/Baseline → BaselinePairedControl | 0 | 0.00 | 0.00 [0.00, 0.00] |
| Priest/0/default/E1/basic/Baseline → BaselinePairedControl | 0 | 0.00 | 0.00 [0.00, 0.00] |
| Priest/0/default/E1/build/Baseline → BaselinePairedControl | 0 | 0.00 | 0.00 [0.00, 0.00] |
| Priest/0/default/O1/baseline_all_hand/Baseline → BaselinePairedControl | 0 | 0.00 | 0.00 [0.00, 0.00] |
| Priest/0/default/O1/basic/Baseline → BaselinePairedControl | 0 | 0.00 | 0.00 [0.00, 0.00] |
| Priest/0/default/O1/build/Baseline → BaselinePairedControl | 0 | 0.00 | 0.00 [0.00, 0.00] |
| Priest/0/default/O6/baseline_all_hand/Baseline → TargetedO6Hp095 | 0 | -0.33 | -2.47 [-2.59, -2.37] |
| Priest/0/default/O6/basic/Baseline → TargetedO6Hp095 | 0 | -0.41 | -1.48 [-1.65, -1.31] |
| Priest/0/default/O6/build/Baseline → TargetedO6Hp095 | 0 | -0.27 | -2.64 [-2.79, -2.49] |
