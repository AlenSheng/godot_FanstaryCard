# PR13 战斗机器人分层汇总

来自原始逐战样本；超时、死亡和错误均保留。候选未启用。

共 360,000 条，运行错误 0 条。每个主要层合并三段互不重叠的种子，分位数从原始样本重算。

默认裸装、直接进入指定遭遇的离线模拟；不代表合法完整探索、联网容量或真人体验。Boss 层也不代表完成装备准备后的难度。

| 职业/武器/场景/策略/规则 | N | 胜/死/超时 | 全结果观测秒 P50/P95 | 最长无有效动作秒 P95 |
| --- | ---: | --- | --- | ---: |
| Guardian/0/default/BOSS/baseline_all_hand/Baseline | 3000 | 0/3/2997 | 300.0/300.0 | 4.0 |
| Guardian/0/default/BOSS/baseline_all_hand/FractionalRemainder | 3000 | 0/3/2997 | 300.0/300.0 | 4.0 |
| Guardian/0/default/BOSS/basic/Baseline | 3000 | 0/9/2991 | 300.0/300.0 | 12.0 |
| Guardian/0/default/BOSS/basic/FractionalRemainder | 3000 | 0/9/2991 | 300.0/300.0 | 12.0 |
| Guardian/0/default/BOSS/build/Baseline | 3000 | 0/68/2932 | 300.0/300.0 | 12.0 |
| Guardian/0/default/BOSS/build/FractionalRemainder | 3000 | 0/68/2932 | 300.0/300.0 | 12.0 |
| Guardian/0/default/E1/baseline_all_hand/Baseline | 3000 | 0/0/3000 | 300.0/300.0 | 4.0 |
| Guardian/0/default/E1/baseline_all_hand/FractionalRemainder | 3000 | 0/0/3000 | 300.0/300.0 | 4.0 |
| Guardian/0/default/E1/basic/Baseline | 3000 | 4/0/2996 | 300.0/300.0 | 12.0 |
| Guardian/0/default/E1/basic/FractionalRemainder | 3000 | 4/0/2996 | 300.0/300.0 | 12.0 |
| Guardian/0/default/E1/build/Baseline | 3000 | 241/0/2759 | 300.0/300.0 | 12.0 |
| Guardian/0/default/E1/build/FractionalRemainder | 3000 | 241/0/2759 | 300.0/300.0 | 12.0 |
| Guardian/0/default/O1/baseline_all_hand/Baseline | 3000 | 3000/0/0 | 60.1/64.1 | 4.0 |
| Guardian/0/default/O1/baseline_all_hand/FractionalRemainder | 3000 | 3000/0/0 | 60.1/64.1 | 4.0 |
| Guardian/0/default/O1/basic/Baseline | 3000 | 3000/0/0 | 64.1/72.1 | 12.0 |
| Guardian/0/default/O1/basic/FractionalRemainder | 3000 | 3000/0/0 | 64.1/72.1 | 12.0 |
| Guardian/0/default/O1/build/Baseline | 3000 | 3000/0/0 | 60.1/72.1 | 12.0 |
| Guardian/0/default/O1/build/FractionalRemainder | 3000 | 3000/0/0 | 60.1/72.1 | 12.0 |
| Guardian/0/default/O6/baseline_all_hand/Baseline | 3000 | 3000/0/0 | 68.1/72.1 | 4.0 |
| Guardian/0/default/O6/baseline_all_hand/FractionalRemainder | 3000 | 3000/0/0 | 68.1/72.1 | 4.0 |
| Guardian/0/default/O6/basic/Baseline | 3000 | 3000/0/0 | 72.1/84.1 | 12.0 |
| Guardian/0/default/O6/basic/FractionalRemainder | 3000 | 3000/0/0 | 72.1/84.1 | 12.0 |
| Guardian/0/default/O6/build/Baseline | 3000 | 3000/0/0 | 68.1/80.1 | 12.0 |
| Guardian/0/default/O6/build/FractionalRemainder | 3000 | 3000/0/0 | 68.1/80.1 | 12.0 |
| Guardian/2/default/BOSS/baseline_all_hand/Baseline | 3000 | 0/0/3000 | 300.0/300.0 | 4.0 |
| Guardian/2/default/BOSS/baseline_all_hand/FractionalRemainder | 3000 | 0/0/3000 | 300.0/300.0 | 4.0 |
| Guardian/2/default/BOSS/basic/Baseline | 3000 | 0/0/3000 | 300.0/300.0 | 12.0 |
| Guardian/2/default/BOSS/basic/FractionalRemainder | 3000 | 0/2/2998 | 300.0/300.0 | 12.0 |
| Guardian/2/default/BOSS/build/Baseline | 3000 | 0/3/2997 | 300.0/300.0 | 12.0 |
| Guardian/2/default/BOSS/build/FractionalRemainder | 3000 | 0/13/2987 | 300.0/300.0 | 12.0 |
| Guardian/2/default/E1/baseline_all_hand/Baseline | 3000 | 0/0/3000 | 300.0/300.0 | 4.0 |
| Guardian/2/default/E1/baseline_all_hand/FractionalRemainder | 3000 | 0/0/3000 | 300.0/300.0 | 4.0 |
| Guardian/2/default/E1/basic/Baseline | 3000 | 4/0/2996 | 300.0/300.0 | 12.0 |
| Guardian/2/default/E1/basic/FractionalRemainder | 3000 | 4/0/2996 | 300.0/300.0 | 12.0 |
| Guardian/2/default/E1/build/Baseline | 3000 | 232/0/2768 | 300.0/300.0 | 12.0 |
| Guardian/2/default/E1/build/FractionalRemainder | 3000 | 239/0/2761 | 300.0/300.0 | 12.0 |
| Guardian/2/default/O1/baseline_all_hand/Baseline | 3000 | 3000/0/0 | 60.1/64.1 | 4.0 |
| Guardian/2/default/O1/baseline_all_hand/FractionalRemainder | 3000 | 3000/0/0 | 60.1/64.1 | 4.0 |
| Guardian/2/default/O1/basic/Baseline | 3000 | 3000/0/0 | 64.1/72.1 | 12.0 |
| Guardian/2/default/O1/basic/FractionalRemainder | 3000 | 3000/0/0 | 64.1/72.1 | 12.0 |
| Guardian/2/default/O1/build/Baseline | 3000 | 3000/0/0 | 60.1/72.1 | 12.0 |
| Guardian/2/default/O1/build/FractionalRemainder | 3000 | 3000/0/0 | 60.1/72.1 | 12.0 |
| Guardian/2/default/O6/baseline_all_hand/Baseline | 3000 | 3000/0/0 | 68.1/72.1 | 4.0 |
| Guardian/2/default/O6/baseline_all_hand/FractionalRemainder | 3000 | 3000/0/0 | 68.1/72.1 | 4.0 |
| Guardian/2/default/O6/basic/Baseline | 3000 | 3000/0/0 | 72.1/84.1 | 12.0 |
| Guardian/2/default/O6/basic/FractionalRemainder | 3000 | 3000/0/0 | 72.1/84.1 | 12.0 |
| Guardian/2/default/O6/build/Baseline | 3000 | 3000/0/0 | 68.1/80.1 | 12.0 |
| Guardian/2/default/O6/build/FractionalRemainder | 3000 | 3000/0/0 | 68.1/80.1 | 12.0 |
| Guardian/4/default/BOSS/baseline_all_hand/Baseline | 3000 | 0/0/3000 | 300.0/300.0 | 4.0 |
| Guardian/4/default/BOSS/baseline_all_hand/FractionalRemainder | 3000 | 0/0/3000 | 300.0/300.0 | 4.0 |
| Guardian/4/default/BOSS/basic/Baseline | 3000 | 0/0/3000 | 300.0/300.0 | 12.0 |
| Guardian/4/default/BOSS/basic/FractionalRemainder | 3000 | 0/0/3000 | 300.0/300.0 | 12.0 |
| Guardian/4/default/BOSS/build/Baseline | 3000 | 0/0/3000 | 300.0/300.0 | 12.0 |
| Guardian/4/default/BOSS/build/FractionalRemainder | 3000 | 0/1/2999 | 300.0/300.0 | 12.0 |
| Guardian/4/default/E1/baseline_all_hand/Baseline | 3000 | 0/0/3000 | 300.0/300.0 | 4.0 |
| Guardian/4/default/E1/baseline_all_hand/FractionalRemainder | 3000 | 0/0/3000 | 300.0/300.0 | 4.0 |
| Guardian/4/default/E1/basic/Baseline | 3000 | 6/0/2994 | 300.0/300.0 | 12.0 |
| Guardian/4/default/E1/basic/FractionalRemainder | 3000 | 4/0/2996 | 300.0/300.0 | 12.0 |
| Guardian/4/default/E1/build/Baseline | 3000 | 261/0/2739 | 300.0/300.0 | 12.0 |
| Guardian/4/default/E1/build/FractionalRemainder | 3000 | 244/0/2756 | 300.0/300.0 | 12.0 |
| Guardian/4/default/O1/baseline_all_hand/Baseline | 3000 | 3000/0/0 | 60.1/64.1 | 4.0 |
| Guardian/4/default/O1/baseline_all_hand/FractionalRemainder | 3000 | 3000/0/0 | 60.1/64.1 | 4.0 |
| Guardian/4/default/O1/basic/Baseline | 3000 | 3000/0/0 | 64.1/72.1 | 12.0 |
| Guardian/4/default/O1/basic/FractionalRemainder | 3000 | 3000/0/0 | 64.1/72.1 | 12.0 |
| Guardian/4/default/O1/build/Baseline | 3000 | 3000/0/0 | 60.1/72.1 | 12.0 |
| Guardian/4/default/O1/build/FractionalRemainder | 3000 | 3000/0/0 | 60.1/72.1 | 12.0 |
| Guardian/4/default/O6/baseline_all_hand/Baseline | 3000 | 3000/0/0 | 68.1/72.1 | 4.0 |
| Guardian/4/default/O6/baseline_all_hand/FractionalRemainder | 3000 | 3000/0/0 | 68.1/72.1 | 4.0 |
| Guardian/4/default/O6/basic/Baseline | 3000 | 3000/0/0 | 72.1/84.1 | 12.0 |
| Guardian/4/default/O6/basic/FractionalRemainder | 3000 | 3000/0/0 | 72.1/84.1 | 12.0 |
| Guardian/4/default/O6/build/Baseline | 3000 | 3000/0/0 | 68.1/76.1 | 12.0 |
| Guardian/4/default/O6/build/FractionalRemainder | 3000 | 3000/0/0 | 68.1/76.1 | 12.0 |
| Mage/0/default/BOSS/baseline_all_hand/Baseline | 3000 | 0/3000/0 | 96.8/96.8 | 7.6 |
| Mage/0/default/BOSS/baseline_all_hand/CoreCardsSpent | 3000 | 0/3000/0 | 96.8/96.8 | 7.6 |
| Mage/0/default/BOSS/basic/Baseline | 3000 | 0/3000/0 | 101.8/111.8 | 11.6 |
| Mage/0/default/BOSS/basic/CoreCardsSpent | 3000 | 0/3000/0 | 101.8/111.8 | 11.6 |
| Mage/0/default/BOSS/build/Baseline | 3000 | 0/3000/0 | 101.8/111.8 | 11.6 |
| Mage/0/default/BOSS/build/CoreCardsSpent | 3000 | 0/3000/0 | 101.8/111.8 | 11.6 |
| Mage/0/default/E1/baseline_all_hand/Baseline | 3000 | 1/2999/0 | 100.0/100.0 | 7.6 |
| Mage/0/default/E1/baseline_all_hand/CoreCardsSpent | 3000 | 0/3000/0 | 100.0/100.0 | 7.6 |
| Mage/0/default/E1/basic/Baseline | 3000 | 35/2965/0 | 110.0/120.0 | 11.6 |
| Mage/0/default/E1/basic/CoreCardsSpent | 3000 | 0/3000/0 | 110.0/120.0 | 11.6 |
| Mage/0/default/E1/build/Baseline | 3000 | 602/2398/0 | 110.0/120.0 | 11.6 |
| Mage/0/default/E1/build/CoreCardsSpent | 3000 | 0/3000/0 | 110.0/120.0 | 11.6 |
| Mage/0/default/O1/baseline_all_hand/Baseline | 3000 | 3000/0/0 | 36.1/40.5 | 7.2 |
| Mage/0/default/O1/baseline_all_hand/CoreCardsSpent | 3000 | 3000/0/0 | 36.5/40.5 | 7.2 |
| Mage/0/default/O1/basic/Baseline | 3000 | 3000/0/0 | 40.9/48.1 | 11.6 |
| Mage/0/default/O1/basic/CoreCardsSpent | 3000 | 3000/0/0 | 42.5/48.1 | 11.6 |
| Mage/0/default/O1/build/Baseline | 3000 | 3000/0/0 | 39.7/44.9 | 11.6 |
| Mage/0/default/O1/build/CoreCardsSpent | 3000 | 3000/0/0 | 40.1/44.9 | 11.6 |
| Mage/0/default/O6/baseline_all_hand/Baseline | 3000 | 3000/0/0 | 40.5/46.5 | 7.6 |
| Mage/0/default/O6/baseline_all_hand/CoreCardsSpent | 3000 | 3000/0/0 | 40.9/46.5 | 7.6 |
| Mage/0/default/O6/basic/Baseline | 3000 | 3000/0/0 | 46.9/54.9 | 11.6 |
| Mage/0/default/O6/basic/CoreCardsSpent | 3000 | 3000/0/0 | 47.7/54.9 | 11.6 |
| Mage/0/default/O6/build/Baseline | 3000 | 3000/0/0 | 44.9/52.5 | 11.6 |
| Mage/0/default/O6/build/CoreCardsSpent | 3000 | 3000/0/0 | 45.3/52.5 | 11.6 |
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
| Priest/0/default/O6/baseline_all_hand/BaselinePairedControl | 3000 | 3000/0/0 | 62.9/67.7 | 10.8 |
| Priest/0/default/O6/basic/Baseline | 3000 | 3000/0/0 | 68.1/76.1 | 12.0 |
| Priest/0/default/O6/basic/BaselinePairedControl | 3000 | 3000/0/0 | 68.1/76.1 | 12.0 |
| Priest/0/default/O6/build/Baseline | 3000 | 3000/0/0 | 64.1/72.1 | 12.0 |
| Priest/0/default/O6/build/BaselinePairedControl | 3000 | 3000/0/0 | 64.1/72.1 | 12.0 |

## 候选差异

+2/+4 护盾候选的收益必须分别评估；下表直接展示有效护盾变化，不能描述为全等级加强。胜局时长与全结果观测时长已分列于 JSON。

| 分层 | 胜数变化 | 有效护盾均值变化 | 60秒伤害均值变化与95%区间 |
| --- | ---: | ---: | --- |
| Guardian/0/default/BOSS/baseline_all_hand/Baseline → FractionalRemainder | 0 | 0.00 | 0.00 [0.00, 0.00] |
| Guardian/0/default/BOSS/basic/Baseline → FractionalRemainder | 0 | 0.00 | 0.00 [0.00, 0.00] |
| Guardian/0/default/BOSS/build/Baseline → FractionalRemainder | 0 | 0.00 | 0.00 [0.00, 0.00] |
| Guardian/0/default/E1/baseline_all_hand/Baseline → FractionalRemainder | 0 | 0.00 | 0.00 [0.00, 0.00] |
| Guardian/0/default/E1/basic/Baseline → FractionalRemainder | 0 | 0.00 | 0.00 [0.00, 0.00] |
| Guardian/0/default/E1/build/Baseline → FractionalRemainder | 0 | 0.00 | 0.00 [0.00, 0.00] |
| Guardian/0/default/O1/baseline_all_hand/Baseline → FractionalRemainder | 0 | 0.00 | 0.00 [0.00, 0.00] |
| Guardian/0/default/O1/basic/Baseline → FractionalRemainder | 0 | 0.00 | 0.00 [0.00, 0.00] |
| Guardian/0/default/O1/build/Baseline → FractionalRemainder | 0 | 0.00 | 0.00 [0.00, 0.00] |
| Guardian/0/default/O6/baseline_all_hand/Baseline → FractionalRemainder | 0 | 0.00 | 0.00 [0.00, 0.00] |
| Guardian/0/default/O6/basic/Baseline → FractionalRemainder | 0 | 0.00 | 0.00 [0.00, 0.00] |
| Guardian/0/default/O6/build/Baseline → FractionalRemainder | 0 | 0.00 | 0.00 [0.00, 0.00] |
| Guardian/2/default/BOSS/baseline_all_hand/Baseline → FractionalRemainder | 0 | -4.69 | 0.00 [0.00, 0.00] |
| Guardian/2/default/BOSS/basic/Baseline → FractionalRemainder | 0 | -4.11 | 0.01 [-0.02, 0.04] |
| Guardian/2/default/BOSS/build/Baseline → FractionalRemainder | 0 | -4.09 | 0.02 [-0.01, 0.05] |
| Guardian/2/default/E1/baseline_all_hand/Baseline → FractionalRemainder | 0 | -4.49 | 0.00 [0.00, 0.00] |
| Guardian/2/default/E1/basic/Baseline → FractionalRemainder | 0 | -4.12 | 0.01 [-0.03, 0.05] |
| Guardian/2/default/E1/build/Baseline → FractionalRemainder | 7 | -4.35 | 0.05 [0.01, 0.09] |
| Guardian/2/default/O1/baseline_all_hand/Baseline → FractionalRemainder | 0 | -1.04 | 0.00 [0.00, 0.00] |
| Guardian/2/default/O1/basic/Baseline → FractionalRemainder | 0 | -0.99 | -0.02 [-0.06, 0.01] |
| Guardian/2/default/O1/build/Baseline → FractionalRemainder | 0 | -1.03 | -0.00 [-0.03, 0.03] |
| Guardian/2/default/O6/baseline_all_hand/Baseline → FractionalRemainder | 0 | -1.09 | 0.00 [0.00, 0.00] |
| Guardian/2/default/O6/basic/Baseline → FractionalRemainder | 0 | -1.09 | -0.06 [-0.12, -0.01] |
| Guardian/2/default/O6/build/Baseline → FractionalRemainder | 0 | -1.06 | -0.01 [-0.06, 0.03] |
| Guardian/4/default/BOSS/baseline_all_hand/Baseline → FractionalRemainder | 0 | -8.94 | 0.00 [0.00, 0.00] |
| Guardian/4/default/BOSS/basic/Baseline → FractionalRemainder | 0 | -8.18 | 0.00 [-0.06, 0.06] |
| Guardian/4/default/BOSS/build/Baseline → FractionalRemainder | 0 | -8.06 | 0.14 [0.08, 0.21] |
| Guardian/4/default/E1/baseline_all_hand/Baseline → FractionalRemainder | 0 | -8.55 | 0.00 [0.00, 0.00] |
| Guardian/4/default/E1/basic/Baseline → FractionalRemainder | -2 | -8.48 | 0.05 [-0.02, 0.12] |
| Guardian/4/default/E1/build/Baseline → FractionalRemainder | -17 | -8.34 | 0.16 [0.10, 0.23] |
| Guardian/4/default/O1/baseline_all_hand/Baseline → FractionalRemainder | 0 | -2.02 | 0.00 [0.00, 0.00] |
| Guardian/4/default/O1/basic/Baseline → FractionalRemainder | 0 | -1.98 | -0.01 [-0.04, 0.02] |
| Guardian/4/default/O1/build/Baseline → FractionalRemainder | 0 | -1.93 | -0.01 [-0.04, 0.02] |
| Guardian/4/default/O6/baseline_all_hand/Baseline → FractionalRemainder | 0 | -2.11 | 0.00 [0.00, 0.00] |
| Guardian/4/default/O6/basic/Baseline → FractionalRemainder | 0 | -2.05 | -0.10 [-0.16, -0.03] |
| Guardian/4/default/O6/build/Baseline → FractionalRemainder | 0 | -1.99 | -0.06 [-0.13, -0.00] |
| Mage/0/default/BOSS/baseline_all_hand/Baseline → CoreCardsSpent | 0 | 0.00 | -2.05 [-2.21, -1.89] |
| Mage/0/default/BOSS/basic/Baseline → CoreCardsSpent | 0 | 0.00 | -2.21 [-2.41, -2.02] |
| Mage/0/default/BOSS/build/Baseline → CoreCardsSpent | 0 | 0.00 | -1.23 [-1.36, -1.08] |
| Mage/0/default/E1/baseline_all_hand/Baseline → CoreCardsSpent | -1 | 0.00 | -2.41 [-2.61, -2.22] |
| Mage/0/default/E1/basic/Baseline → CoreCardsSpent | -35 | 0.00 | -3.75 [-4.03, -3.50] |
| Mage/0/default/E1/build/Baseline → CoreCardsSpent | -602 | 0.00 | -12.48 [-13.04, -11.92] |
| Mage/0/default/O1/baseline_all_hand/Baseline → CoreCardsSpent | 0 | 0.00 | 0.00 [0.00, 0.00] |
| Mage/0/default/O1/basic/Baseline → CoreCardsSpent | 0 | 0.00 | 0.00 [0.00, 0.00] |
| Mage/0/default/O1/build/Baseline → CoreCardsSpent | 0 | 0.00 | 0.00 [0.00, 0.00] |
| Mage/0/default/O6/baseline_all_hand/Baseline → CoreCardsSpent | 0 | 0.00 | 0.00 [0.00, 0.00] |
| Mage/0/default/O6/basic/Baseline → CoreCardsSpent | 0 | 0.00 | 0.00 [0.00, 0.00] |
| Mage/0/default/O6/build/Baseline → CoreCardsSpent | 0 | 0.00 | 0.00 [0.00, 0.00] |
| Priest/0/default/BOSS/baseline_all_hand/Baseline → BaselinePairedControl | 0 | 0.00 | 0.00 [0.00, 0.00] |
| Priest/0/default/BOSS/basic/Baseline → BaselinePairedControl | 0 | 0.00 | 0.00 [0.00, 0.00] |
| Priest/0/default/BOSS/build/Baseline → BaselinePairedControl | 0 | 0.00 | 0.00 [0.00, 0.00] |
| Priest/0/default/E1/baseline_all_hand/Baseline → BaselinePairedControl | 0 | 0.00 | 0.00 [0.00, 0.00] |
| Priest/0/default/E1/basic/Baseline → BaselinePairedControl | 0 | 0.00 | 0.00 [0.00, 0.00] |
| Priest/0/default/E1/build/Baseline → BaselinePairedControl | 0 | 0.00 | 0.00 [0.00, 0.00] |
| Priest/0/default/O1/baseline_all_hand/Baseline → BaselinePairedControl | 0 | 0.00 | 0.00 [0.00, 0.00] |
| Priest/0/default/O1/basic/Baseline → BaselinePairedControl | 0 | 0.00 | 0.00 [0.00, 0.00] |
| Priest/0/default/O1/build/Baseline → BaselinePairedControl | 0 | 0.00 | 0.00 [0.00, 0.00] |
| Priest/0/default/O6/baseline_all_hand/Baseline → BaselinePairedControl | 0 | 0.00 | 0.00 [0.00, 0.00] |
| Priest/0/default/O6/basic/Baseline → BaselinePairedControl | 0 | 0.00 | 0.00 [0.00, 0.00] |
| Priest/0/default/O6/build/Baseline → BaselinePairedControl | 0 | 0.00 | 0.00 [0.00, 0.00] |
