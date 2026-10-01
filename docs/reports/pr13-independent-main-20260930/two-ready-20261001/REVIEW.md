# PR13 两项 Ready 独立 MAIN 复验

本次实际只复验 PR13-A05.1（62772be2）和 LOAD-02.2（dfb3f88a）；现有15Accepted保持原登记。两项均以真实本地 Program、一次性 PostgreSQL18.6、生产 Game/Godot4.7.2 实跑，未改源码/断言或10秒attempt、30秒logical/BotFill。

**A05.1 三个 canonical、causal/guard/ACK失败恢复和M/N资产均通过；完整验收目前有缺口。** 原2dda+原始九文件测试overlay，实际RED exit1、两个stale=true；62772实际同causal两个stale=false。三种guard窗口覆盖ordinary成功、ACK未提交失败恢复并重试、ACK已提交丢回复后的完整Bootstrap权威核实。Pending4个holds跨OS重启后一次性Committed4；8个最终只读审计×8个counter均为0；原instance/owner和23gold/2potions一次性一致。完整C-SERVER为298Passed/1Failed/0Skipped，exit1：MarkRunning_commit_response_loss_retries_same_room_and_restart_restores_it在原line75期望Running，实际Launching。一次同源同PG配置单项诊断1Passed/0Failed/0Skipped、exit0。保留二者，不认定根因，也不能用filter替代未过滤全套。建议Partial：owner定位该不稳定性并给同合同证据后再签无保留接受；这不否定已实测的A05目标修复，也不重新裁15Accepted。

**LOAD-02.2** 的focused三例已独立通过。实际T01原业务timeout发生于STOP前，最后仍failed、client exit1；T02正常ACK等待，STOP时pending，结束cancelled且无服务error/Completed；T03真实PG先ACK提交，三次同key/body/backend200回复丢失时client仍pending，持有真实完整Bootstrap三权威字段null+ConfigVersion后释放才收尾cancelled，client exit0。原报告是业务结论主证据，观察适配器只读原scenario/checks/finish计数，未替换实现/断言或合成权威字段。最终完整302/Python122结果和是否可接受以REPORT/SUITES为准。

两项原Git派生报告58文件逐hash核验；原private manifest2173/1486文件索引均匹配seal；历史private raw字节未在本环境取得，不冒称做过原raw抽查。新独立raw本地保存，RAW_HASHES给关键原始命令/receipt/结果/TRX的SHA与本地完整manifest哈希。REPORT各项保留原26字段、profile_hash/algorithm_version，不适用null+missing_reasons。依赖按真实所需durable checkpoint/asset exactlyonce/classifier/initiating context最小产物审核，不要求整个上游父包先Accepted。

SOURCE_METADATA_CHECKS证明964/967固定声明文件与精确Git树blob/bytes一致，RED952源码+原9测试overlay一致；各自DLL从内部Release新编译。部分源码拷贝不能称全干净checkout，原因明列。原work/b398分支保持干净。COMMANDS保留原argv/cwd/SHA/版本/时间/exit/loghash，SUITES保留全部分母、skip和失败，不上传完整raw。

只清理本次owned schema/PG/子进程，详见CLEANUP。没有合并部署、原PR/Accepted写入、GitHubCI触发/重试、Library上传或生产账号/服务器数据读取；最终MAIN登记由父协调。
