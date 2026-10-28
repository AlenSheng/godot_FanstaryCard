# A09.3 当前非零装备 ACK 重启与坏最终状态（2026-10-21）

当前正式业务字节下，在现有云主机的临时 PG18.6 与原始 main／4 个真实 Godot 客户端中执行一次功能房间。每个测试账号真实登录提交后、原始登录回包送达前，控制端仅在本次库中预置一件合法 +0 White/Fire/Feet/DrawInterval 装备并更新既有 Mage 穿戴；原认证回包保持原字节。它是声明的初始输入，不是默认新手赠送，也没有改正式 provisioning。

真实准备锁定、开局、死亡结算后，4 件装备各有且仅有一次 preparation.lock、match.start、settlement.death，合计 12 条转移；4 条 hold 均 Committed、4 个 receipt 与 4 个 ACK 已落库。截留第四个真实 ACK200 回包后，先由独立 PG 连接证明提交，再对精确拥有的 Program PID7 发 SIGKILL，原环境／新鲜 DLL／同库恢复到新 PID132。只在此后移除原回包，目标客户端以同一逻辑键重试，收到完全相同的原始持久化响应。重启前、重启后、最终的八组资源／receipt／ACK 行全部一致，非零装备没有重复转移。

实际 Server DLL 为 `dd56dfc4e3ec3de941f85e12a2d1fa3c25a5b4a07be3d2b17eaed2de624d4ead`，不同于历史 cached8eb；对应当前编译文件及21份运行产物逐项固定。原生进程、UID、match、receipt、逻辑 ACK、事件序号和原始轮转日志可直接关联。此房间运行 functional-cycles，属于明确的功能性死亡／弃战流程，不能称为正常自然胜利或长期路线通过。Gold ledger 为 0，本轮不宣称非零金币奖励路径通过。

同一轮仅在目标 UID 的原始最终 report 和有效 status 已写出后，先保留有效状态原字节，再向声明的最终状态输入注入一字节坏 JSON。四个原生 report 均 ok、1cycle、cleanup Passed、退出0，但未修改的原始 main 正确产生 JSONDecodeError／invalid_file，退出3 `invalid_workload_or_evidence`；`acceptance_passed=false`、`business_cleanup_verified=false` 保留。它没有把先前缓存或正常数据当作本次最终清理成功。原生好数据、显式坏输入和原始拒绝结果均完整保存，没有修补原件让 main 变绿。

MAIN 仅关闭 A09.3-T01/LIVE 的指定 ACK 非零资源恢复性质，以及 A09.3-T03/LIVE、POSTGRES 的最终坏证据拒绝性质。T01 原 PG 层增加当前非零装备佐证，不重复计数。A09.3 仍 Partial，A09.2 前置依赖未整体验收，RENDER、旧房间持续 snapshot 与其他层仍缺。当前控制实验的断言满足预期，不能把原始 main 的拒绝改称整轮验收通过。

前三次失败及所有预算如实保留：

- R1：Linux 入口脚本被 Windows CRLF 污染，原始 main 在启动器阶段失败；0 UID、0 房间，不算目标坏状态反例。
- R2：静默输出未配置，psql 命令标签使控制端 JSON 解析失败；已真实创建 4 UID、提交 1 件初始装备，0 房间。它们计入累计，没有从预算抹去。
- R3：私有 Git 克隆漏空 refs 目录，原始 main 在预检拒绝；0 UID、0 房间。补齐实际 Root 索引、空目录并执行实际 Git 预检后才启动 R4。传输中断及只补齐缺失的父包输入文件均发生在未启动前，原冻结包与原件保留，没有重放已运行对局。

累计实际为 8 UID、1 房间、5 件初始装备，R4 为 4 个功能 player-cycle；上限修订保留在计划中，业务正确性标准未放宽。原始 main 的 `git_commit`／`git_dirty` 字段仍不可得，保持 null；没有伪填 SHA 或 agentID。当前实际客户端、私有状态写入尾部覆盖、原始 main 及新鲜程序集的文件摘要独立约束本次执行，Root HEAD86 仅是引用，不是 clean build 声明。

594 份原始文件与四份 PG dump 已完整 G 盘闭包核对；最后一份 dump 另以离线 pg_restore --list 实际读出 server18.6，未新建 PG 服务。67 项独立断言、777 份源／原件／生产脚本档案及共享当前源引用完成复核后，只清理四个精确拥有的云端输入目录。原云端证据和共享缓存保留，生产指纹与健康200不变。本地仅低优先级、无窗口 headless／Dummy／60FPS 的解析和私有 writer 自检，没有本地 PG、真人输入或对局。

当前仍 100 Accepted／24 Partial／8 ReadyForAcceptance，32 项未验收；缺失 case/profile 116→113。所有全局门保持未通过，现有主机不足的容量与 GitHub 账户启动阻断继续保留。两个 GDD 及用户确认的合法80/70边界不变，本轮未提交／推送 release 或部署。
