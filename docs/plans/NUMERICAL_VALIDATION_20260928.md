# 数值集成实测记录

日期：2026-09-28。集成 PR：#12，`codex/numerical-integration-20260928`。
本记录是实际执行结果，不是预计值；不表示整个AG01–09计划已经全部验收。

## 1. 原阻塞已经处理

- 盾余量字段曾加错到CombatResolution，CardResolutionDraft缺失导致编译失败；已经修复。
- 候选职业策略没有随房间快照恢复，预览/重连可能回到旧策略；已增加持久字段、兼容默认值与房间/PVP测试。
- 测试和路线工具触发严格分析器错误；修复代码，没有禁用分析器或删除断言。
- 客户端配置导出器将Protobuf省略的false/零值当作null；现按源表类型还原，并区分显式null。
- Godot测试通过SceneTree脚本过早预加载Game单例；改为正常项目场景，实测通过。

## 2. 最新可核验结果

### .NET与隔离PostgreSQL

- Source SHA：`746774a2fd9d11be1f5a413d690ef458f9c49dec`。
- Actions run：`36425098455`（Numerical full acceptance），job `108936987075`，结论success。
- Artifact：`10971552191`，名称 `numerical-acceptance-746774a2fd9d11be1f5a413d690ef458f9c49dec`。
- 解决方案Release编译成功。
- Domain TRX：**297 total / 297 executed / 297 passed / 0 failed / 0 skipped**。
- Server TRX：**249 total / 249 executed / 249 passed / 0 failed / 0 skipped**。
- 包括真实loopback HTTP/WebSocket与一次性PostgreSQL18数据库用例；未使用生产数据库。
- 共546条C#测试通过。此前Windows的187通过/62跳过已被本次完整执行补齐，不能把旧跳过记录混入新统计。
- 双端配置字节一致，版本 `gdd-0.70-numerical-1`；五个候选开关均为false。
- 客户端Protobuf schema SHA-256与源proto一致；false、零、空字符串、显式null的导出检查通过。

### Godot

- Source SHA：`f5c69d2f2058a2230f1c53b845c112d60f663f62`（与上述C#基线的客户端源相同）。
- Godot：`4.7.stable.official.5b4e0cb0f`。
- Actions run：`36425018346`，job `108936722099`，结论success。
- Artifact：`10971601773`，名称 `numerical-godot-f5c69d2f2058a2230f1c53b845c112d60f663f62`。
- 项目导入/脚本检查通过；场景 `tests/numerical_integration.tscn` 输出 `{"failures":[],"ok":true,"suite":"numerical-integration"}`。
- 覆盖装备抽牌下限、元素抗性帽、仅盾减伤、怪物命令/池编解码、重连后失效选择、多语言动作文本。
- 测试使用无网络命名空间。日志中的初始服务器信息请求连接失败为隔离网络拒绝；不据此宣称“完全无日志错误”，也没有连接生产服务。
- 自动脚本测试不等于五语言完整视觉、点击与真实多人体验验收。

### 路线样本

每种playerCount=1/2/4执行seed=0..9999，共3组运行。它们使用相同seed和首个出生点，**不是30000个互相独立的多人战局**，不包含PVP。
三组均为真实地图/合法移动下的VisibleBossShortestLegalPath策略，输出一致：

| 指标 | P10 | P50 | P90 | 均值 |
| --- | ---: | ---: | ---: | ---: |
| 清格数 | 4 | 5 | 6 | 4.7794 |
| 基础金币 | 98 | 120 | 152 | 121.385 |
| 勇士之魂期望 | 21.5 | 27.5 | 35.5 | 27.40555 |
| 职业之魂 | 12 | 15 | 19 | 14.8784 |
| 碎片期望 | 14 | 18 | 23.5 | 18.01735 |

访问三个不同中层小怪角格所需最少不同中层精英格：4。
以上是路径上的基础期望掉落，**不是成功撤离净收益**。没有模拟死亡、药剂、安全格、三选一装备、付费包重购、市场及机器人交战。当前中层精英基础奖励使用服务器实际的Middle层查表，不暗中替换成GDD预期高档。

## 3. 代码与发布边界

主要调用链已接入：可选怪物卡池（归属/幂等/替换/快照）、机器人独立可搜刮预算、可死亡PVE候选、法师/盾候选策略、源表/房间锁定/协议/客户端界面。
当前正式配置仍关闭候选。release仍为 `a234d2e6e76548563aadc10a8da2bd6d9d1c1957`，未合并本PR、未部署、未启用生产玩法。

## 4. 仍需收尾与独立验收

1. 完整日循环和经济守恒仿真：失败局、安全格、资源用途、市场转移/税收、重建时间等。
2. 机器人物品来源贯穿持久存储与交易的完整审计；当前只有确定性实例ID和IsGenerated，不等于已完成来源台账。
3. 全卡池极值构筑、返牌/蓄能真实长序列、性能基线；局部单测不能证明全局平衡。
4. UI视觉/多语言/真实交互验收，特别是未激活或职业不适用的属性不可误标为纯粹“超帽”。

这些在 `CODEX_NUMERICAL_ACCEPTANCE_20260928.md` 中逐项交接，不能把全部AG标为Done。

## 5. Codex状态

已在本PR评论5870331787提交测试/缺陷修复/剩余实现任务。
Codex机器人 `chatgpt-codex-connector[bot]` 在评论5870335148明确回复：需要为该仓库建立Codex云端环境。
因此**云端Codex尚未执行**。当前所有实测来自GitHub Actions，不冒充Codex结果。
云端建立环境后可重新发起该任务；本地Codex也可直接读取交接文档与集成分支执行，不需要覆盖F盘未提交修改。
