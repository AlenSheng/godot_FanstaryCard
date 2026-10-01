# PR13 云端接管当前收据

MAIN已正式接受15项：LOAD01四项，以及LOAD02.1/.3/.4、LOAD03.1/.2、B02.1–.4、A05.2/.3。每项保持原来源/profile/S6，不把旧源改写为新候选。[新11项裁决](MAIN_S6_bounded11_20261001.json)与[ee8三项](MAIN_S6_ee8adcf4.json)、[e060修复](MAIN_S6_e06037f5.json)分别记录。ROOT没有代签。

A05.1新固定源 `62772be2a1bc28affffc3d057f259c8c5ded8e37` 已封存：完整Server299Passed/0Failed/0Skip、原canonical3及全部ACK/旧poll/普通终态/newN/资产窗口通过；2173私有文件52,314,867字节逐项SHA匹配。只在GameStore增加一行pending-ACK guard，生产提交 `7231c7499b7220b85c27be48ebbd127d7c0b7038`。33host已收回，ownedPG停止且data/socket删除；退出zombie实际状态保留。原2dda反例和76d完整296/3夹具204错误没有覆盖。[完整去敏报告](a05-guard-62772be2/report.json)、[独立重放](a05-guard-62772be2/REPLAY.md)、[原始索引](a05-guard-62772be2/PRIVATE_ARTIFACT_MANIFEST.json)交MAIN S6，A05.1仅Ready，未Accepted。

选定19项当前15Accepted/2Ready/2Partial。132项为15Accepted/2Ready/40Partial/72NotRevalidated/3Blocked；G0–G5未签署，历史27显式runner回执不作总覆盖。剩余两项Partial为LOAD03.3/.4；LOAD02.2真实PG timeout→STOP完整补证，新harness源码 `dfb3f88a73efd85cc4ed12b8d49038bebbb1f953` 已封存，业务未新改。10s/30s预算和cleanup22s、BotFill30s保持。LOAD02原三case在focused与完整矩阵各通过：Server302/0/0、Python122/0/0；原10个Git元数据环境错误保留，源码未修改才补足元数据后通过。39host收回、ownedPG停止清理、1486私有文件48,520,987字节逐SHA匹配。[LOAD02完整报告](load02-timeout-dfb3f88a/report.json)、[最小重放](load02-timeout-dfb3f88a/REPLAY.md)仅Ready待MAIN独立S6。没有开始LOAD03 telemetry，未修改主题美术或UI组件。

历史19项[封存收据](BOUNDED_19_RECEIPT.json)保持当时内容，原业务f812、工具e060及组来源分别保留；[逐项登记](TASK_CHECKLIST.md)、[机器登记](register.json)、[case映射](CASE_MAPPING.json)、[下一队列](NEXT_QUEUE.json)记录接续。历史dirty/多cohort/容量失败、50/100原raw缺口和全局ledger mismatch=1保持，owned局部审计不关闭全局异常。

四份raw ZIP31,096,278字节已获用户授权保存私有Library，两次批准尝试均在保存返回前报同一network错误，无ID，原大小/SHA不变；父已明确暂停继续重试。[第二次失败收据](RAW4_LIBRARY_RETRY1_20261001.json)。没有换目的地。新的A05 raw也只留授权本地，Git提供去敏摘要、fixture及文件SHA索引。

免费月额度恢复由MAIN实际run36769267487 attempt2证实，额外budget$0/StopYes保持；两批本地稳定后仅必要最终候选CI一次，中间文档推送skipCI。后续组合记录release新基线 `65361bcc27c51c28651c86c5dbba4f083a9b39e0`，main `1517f9fae8d865b8d663fa27d9fd38e95cb03d28`；这里只fetch核验，没有合入、合并或部署。缺失server_create技能按canonical已授权例外记录，未虚构已读。

最终候选CI当前另有[新release工作流冲突](load02-timeout-dfb3f88a/NEW_RELEASE_CI_CONFLICT.json)：PR13与65361的numerical-client.yml需要父/controller负责人组合Godot4.7.2/preview与named-export；这里未修改其文件、合入release或触发无效/中间CI。该阻塞不加入A05/LOAD02原离线合同门槛。
