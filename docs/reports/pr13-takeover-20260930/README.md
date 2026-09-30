# PR13 独立云端接管

已核验仓库 `AlenSheng/godot_FanstaryCard`、PR13 分支
`fix/gameplay-load-evidence-20260929`、集成基准 `release`。
[baseline.json](baseline.json) 保留接管时固定 `73d4e41` 的事实与当时下载阻塞；
后续包取证见 [handoff-review/verification.json](handoff-review/verification.json)。
原收尾报告和历史 raw 没有被改写。

父任务已下载并验证原 ZIP：1,990,894,902 字节，SHA256
`242da4d0bdccb8437a16c310be3b61b131b60f28eae9cbc61ab5df66e05db967`；
3929 个 PACKAGE_MANIFEST 文件全部匹配，147 个关键证据存在，5 个仅 CRLF 差异。
本环境安全取得 Library 小包，12,484,089 字节，SHA256
`60a134a20fe2b997b4e1e44662d10e4df6c348fbad27df30d8a17bfae25e539a`，
核验 Library 归属和 115 个 manifest 文件。其中 24 个源码/报告文件与固定73d4
内容一致，仅换行形式不同。本环境没有重复下载整包，也没有把原大包的父任务核验
称为本机独立重算。小包省略的15份大 JSONL 在原包中存在；两项更早50/100客户端
逐客户端历史 raw 仍缺失，这两类边界分别记录。

接管后已推送的逻辑修复：

- `1bc3910` / `9275ec2`：最终 status、audit loss、尾部指标、JSONL 归属和水位，
  异常 STOP 退出，以及 cycle 完成必须由同局已确认的 settlement ACK 支撑。
- `a828eb5`：只读权威预览绑定完整目标/选牌/状态上下文；手动切目标未确认时阻止
  发往旧目标的 play。保留 GDD 明确规定的死亡后从左到右自动目标回退。
- `b7099ef`：MarkRunning 已提交但应答丢失可重试；terminal checkpoint 成功后才
  持久结算；恢复时隔离与持久终态矛盾的旧房，继续恢复新房路由。
- `d4c3212`：操作者在首个采样前停止保留130；增加真实子进程 STOP 后异常退出、
  缺审计文件和报告写入失败的反例。

`6f3b50fb` 修正模拟完整因子/种子矩阵、来源、预算和删失 P95；
`cc6da2e7` 拒绝采样重叠/倒退与负时间，坏覆盖证据进入最终裁决。
[最终纯提交复测](integrated-cc6da2e/report.json)：Python115、显式回执27、Godot导入与五gate，
新鲜构建零警告/错误、Domain317、私有PG262均通过；数据库已停止清理。
[五个精确head CI工作流](ci-cc6da2e/workflows.json)全部成功；CI merge checkout
`f5a4c981`另列，115项accounting artifact哈希已核验。
精确修改SHA及各批限制见 [batch-results.json](batch-results.json)，交付摘要见 [BATCH_CLOSEOUT.md](BATCH_CLOSEOUT.md)。
只读预览增加的有界流量仍需原负载重测；本批没有修改主题、着色器、美术或PR14部署文件。

[新实际Domain实验](actual-factors-cc6da2e/report.json)在固定cc6源码上新鲜构建：
四个O6单因素各三块×1000配对seed，12/12任务完成，864000条记录，
324000组非O6配对对照和54000条首次预告候选记录检查通过，零raw/control错误。
每因子216000条分开汇总，预算BudgetMet；推荐NotEvaluated，候选关闭。
源在构建前纯净，构建后dirty仅为已记录的bin/obj；C#manifest未输出dirty（Unknown），
preregistration的true及源/程序集/config哈希全部按实保留。
1800权威预览向量再用新鲜程序集核验零差异。原历史792000条没有改写。
四份私有raw ZIP逐文件/整包校验完毕，每份约7.8MB，哈希见
[raw-package-manifest.json](actual-factors-cc6da2e/raw-package-manifest.json)，尚未上传或提交Git。

独立验证包括固定73d4的53项 Python、27个显式离线回执、Godot导入及五个 gate；
以及各修复批次的反例、完整回归和真实一次性PG测试。27不是全部测试数量，也不代表
396个 canonical 案例全覆盖。新增测试作为支持证据另列，不自动写 canonical Passed。

[b7099ef CI 复跑](ci-b7099ef/verified-artifacts.json) 核验了 artifact ZIP 哈希：
PG262项零失败/跳过，客户端17组（含32项目标合同）、HTTP边界13、codec173、
transport24、1800权威预览/Play与Godot对比零差异。CI checkout为PR merge
`cddb353`，独立记录于head `b7099ef`之外。原16:11取消日志仅显示取消，未给出操作者
或原因；重跑的109989804771/109989841572已通过。预览原manifest的build后dirty=true
保留，不能改称纯post-build tree。

[register.json](register.json) 和 [TASK_CHECKLIST.md](TASK_CHECKLIST.md) 保留132项
依赖、负责人、历史状态、修改SHA、命令、证据和阻塞。阶段收据见 [STAGE_RECEIPT.json](STAGE_RECEIPT.json)，396案例的执行与支持证据映射见 [CASE_MAPPING.json](CASE_MAPPING.json)。全部Accepted仍为0，G0–G5
未签署。当前状态为45项Partial、84项NotRevalidated、3项Blocked；Blocked包含两项原始历史raw取证及一项全局ledger归因。下一关键队列见 [NEXT_QUEUE.json](NEXT_QUEUE.json)。服务器和客户端子代理在dirty工作区产生的原报告按原样保存；纯SHA/CI验证独立列示。

尚未闭环的主要范围：历史缺raw差异归因、全局ledger mismatch=1的只读取证，真实同账号
三局/完整准备后Boss路线，全故障与资产矩阵，50/100容量及三组成对A/B/30分钟长稳，
隔离版本回滚，预登记完整实验、真实渲染连续三局、帧率/延迟分层及真人体验。
原900秒十客户端600秒目标覆盖58.3%仍失败；1800秒计划在598.2秒因监控不可用停止，
性能Unknown。792000行按五个源码/武器/因子cohort分列，不合成一个基线。预告实验的
windup025三项Cancelled、windup050三项NotExecuted，均不升级完成。

server/AGENTS.md引用的mandatory `.agents/skills/server_create/SKILL.md` 缺失；
按已有明确授权继续不受影响工作，没有声称读取该技能。[固定SHA线上验证计划](LIVE_VALIDATION_PLAN.json)交父任务协调，重启已有授权；
代码部署须沿用固定构建、工作流、互斥和证据门槛。目前没有访问/部署/重启测试服，
未合并、未启用候选生产数值、未恢复数据库、未改余额/账本。

原262项PG回归中的10项既有真实host HTTP/WS测试也已执行，其中PVP/遗物/撤离强杀及两次冷启动用例通过。新八项恢复故障用例主要采用actor/repository重建；下一批补充新修复路径的实际OS进程矩阵。二者scope分别列于case映射，不合称完整三局/故障验收。
