# PR13 — YK 本机接手与有界修复

执行电脑：`YK-SHENGJIAHAO`。仓库：
`C:\Users\SHENGJIAHAO\Documents\Codex\2026-10-01\task\relicround-local\pr13`。
本机没有 `F:\GitHubFiles`，因此使用用户获准工作区。隔离分支为
`fix/yk-pr13-local-20261001`；草稿 PR 为 [#21](https://github.com/AlenSheng/godot_FanstaryCard/pull/21)，基于 PR13 的 feature 分支。

本报告随修复提交保存。提交后完整本机回归、自动 CI 的终态及最终源码 SHA
记录在同一工作区的 `../evidence/FINAL_REPORT.md`、`FINAL_STATUS.json`。
下表仅记录已实际完成的结果；尚未完成的运行不会算通过。

## 原始基准与保护范围

- PR13 远端基准：`d2fe95d78c093cc4443c048bb2779352d9d83956`，最后代码 `0d4ec7f23df806da7a86f9d954033a718349de7e`。
- `release`：`65361bcc27c51c28651c86c5dbba4f083a9b39e0`；`main`：`1517f9fae8d865b8d663fa27d9fd38e95cb03d28`。
- 本轮修复提交：`d49a4905d11a44caa10d8fd2dd92194f2a287fc4`、`373cbb4a0a8f189c695743d4d432ed3bbbe1b948`、`7cdd6eb783168112fc0194359d7bbce1ba3ae5cf`，以及包含本报告的 A05 测试夹具修复提交。
- 没有更新原 PR13、release/main，没有 merge、force push 或部署；PR20 归档保持隔离。所有原始失败均保留。
- 本仓库要求的 `.agents/skills/server_create/SKILL.md` 实际缺失；按既有接手说明中的缺失例外继续。已读取仓库说明、GDD 和服务端规格；未假定其他执行器存在。

## 已完成的实现

**LOAD02 收据。** 先在同目录临时文件中写入、flush、关闭，再原子 rename 发布。
可控半写反例观察到旧实现的最终路径暴露无效 JSON，修复后最终路径在写完前不可见。
增加 6 个 open/rename/既有错误 × completed/cancelled 的实际失败反例：旧代码错误被后续 `quit(0)` 覆盖；修复后全部退出 1，原 `_finish` 不再覆盖首个失败。
10 秒、30 秒业务预算和原业务真值断言保持不变。

**B03.1 公开输入。** `Select` 仅使用目标 HP/盾的公开投影评分，真实执行仍使用权威怪物抗性。
满血无装备 Mage、火8/水6/加速、目标 HP7 盾0、当前 Charge/None、只改未来 Fire→Water 的实际测试先红（2 失败）后绿。
选牌和执行之间重验 battle、revision、生命、眩晕、目标和手牌；无有效操作返回带原因的 Wait。
现有未知卡牌等异常继续传播，没有通用 Domain 异常吞噬。新增公开输入及失效操作测试共 15 项。

**B06.1/.2 真实账本。** 新增 17 个实际 Room→PlayerCombatState→CombatDeck 测试，覆盖满手 R1/R3/R5、两种抽牌策略、初始蓄能0/.9、先前 combo0/4、B 不计 CoreCount，以及纯 B + 抽牌请求。
分别核验 ImmediateDraw 请求、实际入手、蓄能兑换和各池 UUID 守恒。没有证据证明原公式错误，因此保留原公式和 ImmediateDraw 请求语义。

**模拟身份及比较器。** 策略版本明确为 `public-target-v2`，进入 manifest、run identity、raw、summary 和分层标签。
`7cdd6eb` 严格验证 raw 的 StrategyVersion 与 manifest 一致，并验证 StrategyProfile 恰为 `Version/Strategy/Profile`，之后才从行为比较排除两个候选标签字段 Profile/StrategyProfile。
StrategyVersion 和所有行为字段继续比较；冻结签名包括版本。伪造/缺失版本、伪造派生标签、混合版本、真正的 Damage 变化均有拒绝测试。

**新 A05 ordinary 夹具竞态。** `7cdd6eb` 的 Gameplay 原始 CI 在 ordinary/success 的两个上下文断言失败，ACK 和防回填断言均通过。
钱包锁保持 Pending 资产，不保持房间路由；终态持久结算被观察后路由释放，延迟快照请求可以合法返回 NOT_IN_ROOM 并建立 recovery。
修复只在本测试的 `fc_runtime_test_*` 隔离 schema 安装终态 checkpoint advisory gate：真实完成事件已发布、路由尚未释放时读取真实 terminal snapshot，随后释放 checkpoint，再继续原 Pending、GET、poll、ACK 流程。
不修改生产代码、PB、快照、资产或收据。保留全部原断言，并加强普通分支必须实际读取 Extracted snapshot 的检查；90/10/30 秒预算未增加。
普通分支另有第二个 `pending-established` / `pending-verified` 客户端 barrier：C#先确认4个真实Pending，客户端在钱包提交前检查无完成收据、原match及ordinary上下文；C#再确认4个Pending和原资产未变后才提交钱包锁。
终态checkpoint释放前的holds=0断言仍保留；两个阶段分开记录，不能把holds0阶段当作实际Pending资产证明。

## 已完成的真实验证

| 来源/窗口 | pass / fail / skip | 原始证据（相对本机 relicround-local） |
|---|---:|---|
| Windows LOAD02 三窗口，373cbb4 | 3 / 0 / 0 | `evidence/tests/final-windows-load02/final-windows-load02.trx` |
| Linux Unix 全 solution，373cbb4 Domain | 349 / 0 / 0 | `evidence/tests/final-linux-unix/` |
| Linux Unix 全 solution，373cbb4 Server | 302 / 0 / 0 | `evidence/tests/final-linux-unix/` |
| Linux TCP A05 两个事务窗口，373cbb4 | 2 / 0 / 0 | `evidence/tests/final-linux-tcp/final-a05-linux-tcp.trx` |
| Windows 离线 Server，373cbb4 | 206 / 0 / 96 | `evidence/tests/final-windows-offline/`；跳过不算集成通过 |
| Windows Domain，7cdd6eb | 349 / 0 / 0 | `evidence/tests/final-7cdd6eb/domain-7cdd6eb.trx` |
| Python，7cdd6eb，UTF-8 模式 | 126 / 0 / 0 | `evidence/python-final-validated-labels.log` |
| 12 个新实际 factor 子进程，7cdd6eb | 12 个 exit0 | `evidence/factor-matrix-7cdd6eb/`；2592 raw，972 controls，162 intent checks，0 errors |
| A05 普通终态快照可控反例，旧夹具 | 2 / 1 / 0 | `evidence/tests/a05-ordinary-controlled-red/` |
| A05 checkpoint 修复前提交，真实 Godot + TCP + PG | 3 / 0 / 0 | `evidence/tests/a05-checkpoint-green-tcp/` |
| Linux Unix 全 solution，728aa96 Domain / Server | 349 / 0 / 0；302 / 0 / 0 | `evidence/tests/final-728aa96-linux-unix/`，总exit0 |
| A05真实4 Pending客户端barrier前提交，Godot + TCP + PG | 3 / 0 / 0 | `evidence/tests/a05-pending-barrier-green-tcp/`；钱包提交前二次客户端检查 |

模拟每层仅 3 samples、每因素 3 独立运行，是有界回归；`main_sample_floor_met=false`、`acceptance_eligible=false`，不得用作主验收规模。

## 自动 CI 的失败历史

- 原 PR13 Gameplay [36810322350](https://github.com/AlenSheng/godot_FanstaryCard/actions/runs/36810322350)：Server301/1/0，LOAD02 STOP JSON 读取半写；原失败 artifact11138764870 SHA256 `cd9e4fcfaa9de99351e9585efeeb061a88021ef1f3917d98662ad0ceaa041dc9`。归档 STOP JSON 后来为1877字节有效，不改变当时失败事实。
- d49a490：4 个 CI success；实际 checkout `aecc2a432ff3a065c19fb0b62ea4a04b6a8a7760`，与 feature Git tree 相同。
- 373cbb4：3 success / 1 failure。Numerical full [36860814381](https://github.com/AlenSheng/godot_FanstaryCard/actions/runs/36860814381) 的972个 control仅 Profile/StrategyProfile 标签不同。原 artifact11162457167 SHA256 `df56846971df115baa9c3484acb13368e2b306c018ef2471648c4d693d96640c`，保留失败；原12组raw哈希不变的派生验证已通过新的严格身份校验。
- 7cdd6eb：3 success / 1 failure。Numerical full [36865291617](https://github.com/AlenSheng/godot_FanstaryCard/actions/runs/36865291617) 成功；Gameplay [36865291633](https://github.com/AlenSheng/godot_FanstaryCard/actions/runs/36865291633) 的 A05 ordinary/success 失败，Server301/1/0。原 artifact11164472740 SHA256 `53ed05b8233a060f0586aec9c87d07f84a2ce221c7904fc77ee16d54c8c4de7d`。同 checkout `a499103a1dac53a4a795b0a0c92a67bb543affd9` 的另一套 Server302/0/0 结果单独保留，不能遮盖该失败。

## 资源与来源

完整逐项来源、大小、SHA256 及本机路径见工作区 `evidence/RESOURCE_INDEX.json`，原 manifests 也保留。

| 项目 | 完成状态 |
|---|---|
| PR13 全 Git 跟踪代码、资源、报告 | 7cdd6eb 为10080文件、2,423,903,737本机字节；最终提交另生成 source manifest。Git fsck成功，LFS fetch/checkout完成，实际无LFS对象 |
| draft release400137322 | 4/4资源，1,990,930,689字节全部校验；主 ZIP1,990,894,902字节，SHA256 `242da4d0bdccb8437a16c310be3b61b131b60f28eae9cbc61ab5df66e05db967` |
| 旧 closeout ZIP 隔离解包 | 3931文件、3,180,587,919字节；3929个 PackageManifest 文件哈希全部匹配。旧源码73d4e41，不覆盖当前业务 |
| PR20 独立归档 d297adc9 | 2,463,279,051字节，SHA256 `a02422d538aedd9936ed45404fe4d15b7ecc17ef107ea84c6b988d8f71249493`；实际受测4f174ac已正常fetch，两提交client/server/config/protocol相同，仅691个报告文件不同 |
| PR13 历史 Actions 归档 | 240/240，113,498,073字节，大小/API SHA256全部核验；剩余下载0，manifest为`evidence/pr13-historical-artifact-verification.json` |
| 本 feature 新 CI 归档 | d49、373、7各7个归档均已下载校验；后续最终提交归档另追加，不重复已有正确文件 |
| PR/评论/review/release枚举 | PR13及PR20已核；列出1个release及4个assets，没有找到可额外下载的PR附件 |

## 不完整项与验收边界

- 4 个 cc6da2e 原始 ZIP，共31,096,278字节，旧云端/失败Library上传留下的源仍无法取得；两轮只读Library搜索无返回ID，不宣称资源齐全。
- 独立 A05 历史封存原始目录清单1678文件/278,078,413字节，没有证明整份私有原始目录已恢复；Git中公开报告、清单和派生材料存在，不等于完整原始目录。
- 原 A05 Running/Launching 偶发问题另列未关闭；本轮 ordinary-context 夹具修复不能证明其关闭。
- Windows 两个旧 A05 事务测试曾在 Unix relay 本机DB路径 guard 失败，证据保留；没有放宽guard。Linux Unix/TCP对应测试已实跑。
- B06仍未补完R2/R4、耗尽库/reshuffle、组合抽牌效果和长序列，17项不代表全覆盖。
- B03.1 前置B01.4+B02.4，B06.1前置B02.4+B03.4，B06.2前置B06.1仍待独立签收；不得提升Accepted。
- register Git blob恒为`10e96294ae534b2fff4b38d36bbd64a23343c7b7`，SHA256 `b792e060ec75f2e61fa2ab159fbe06273844ab44cb80f48bce61d75389288eae`。
  清单只修复重复104/A05.1及遗漏105/A05.2，恢复既有Accepted行；132唯一task/1..132位置/状态逐行一致。
  总数保持16 Accepted /41 Partial /72 NotRevalidated /3 Blocked，新增Accepted=0。

## 本机复跑命令

下列命令使用已记录的官方工具链.NET10.0.400、Godot4.7.2、PostgreSQL18.6；测试连接只指向本轮 owned 本机实例。
合成测试连接值在本机脚本中，未读取凭据、token或私钥。

```powershell
# 从 server 目录；设置 FANTASYCARD_TEST_POSTGRES/A3GAME_GODOT_EXECUTABLE/FANTASYCARD_PROCESS_EVIDENCE 到 owned 实例和独立证据目录
dotnet test FantasyCard.Server.slnx -c Release --artifacts-path .artifacts/yk-final --logger 'trx;LogFilePrefix=full' --results-directory ../../evidence/tests/final
dotnet test tests/FantasyCard.Server.Tests/FantasyCard.Server.Tests.csproj -c Release --artifacts-path .artifacts/yk-final --filter 'FullyQualifiedName~Real_LOAD02' --logger 'trx;LogFileName=load02.trx' --results-directory ../../evidence/tests/final-load02

# 从仓库目录
python -X utf8 -m unittest discover -s tools/tests -v
python -X utf8 tools/pr13_plancheck.py
```

原始 stdout/stderr、TRX、PB、phase收据、源码/程序集哈希及完整实际命令保存在专用本机 evidence，供独立复测使用；不把含真实测试账号上下文的原始PB/数据库状态复制到新公共报告。
