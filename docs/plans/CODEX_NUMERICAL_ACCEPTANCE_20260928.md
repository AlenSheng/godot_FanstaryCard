# 数值集成：Codex 验收与剩余实现交接

日期：2026-09-28。主 PR：#12。工作分支：`codex/numerical-integration-20260928`。生产 release 未修改。

## 1. 真实阻塞与已处理问题

此前 PR #7–10 是未编译的分支切片，不能视为可实装完成。
本轮已修复 CardResolutionDraft 盾余量字段放错位置、候选策略未随快照恢复、盾上限整数恰好填满时保留小数余量、测试/路线工具静态检查错误。
另修复客户端配置导出器把 Protobuf 省略的 false/零值误当 null 的问题；类型由源表列元数据还原，显式空值仍为 null。
Godot 测试从提前编译 autoload 的 SceneTree --script 改为项目普通场景 `client/tests/numerical_integration.tscn`。

GitHub Codex 已收到 PR #12 的 @codex 请求，但机器人明确回复：需要为此仓库创建 Codex 云端环境。请求评论 ID 5870331787，阻塞回复 ID 5870335148。**这不是 Codex 已启动测试的证据。** 本文也可交给已经打开本地项目的 Codex 桌面版，不依赖云端环境。

## 2. 已实装的调用链

| 模块 | 当前代码 |
| --- | --- |
| AG01 现行基线 | 真实 Resolver/房间预览测试，首张定核、线性共振、公共主核增抗、逐卡floor；46/72/113 |
| AG02 法师候选 | R1/2返0、R3/4返1、R5返2；连携仍影响蓄能；旧策略保留；策略随权威快照恢复 |
| AG03 盾候选 | 十分位确定性余量、预览不写状态、真实结算提交、满盾/溢出/离格处理、PVP与重连 |
| AG04 路线切片 | 真实地图/移动/基础掉落查表；可见Boss最短合法路线、分位数、三角格必经精英几何测试 |
| AG05 怪物池 | 服务端击杀来源、清格后接纳/跳过、最多5个增补位、只替换怪物卡、不补抽、幂等、快照、结束清理 |
| AG06 机器人候选 | 战斗装备与显式搜刮预算分离、白绿+0预算、确定性实例ID、可死亡PVE候选、遗物单次生成 |
| AG07 配置与协议 | 源表NumericalRules、默认关闭、房间创建锁定、快照、增量Protobuf字段、编解码与路由 |
| AG08 客户端 | 五语言怪物选择、失效命令丢弃、对手可搜刮物单列、强化真实收益与上限显示、盾余量显示 |
| AG09 验收 | GitHub Actions 已建立 Windows/隔离Postgres/Godot回归；仍需要 Codex 独立验收和完整体验证据 |

不能把上表“实现存在”误读为所有计划项已经完成。以下内容仍未完成：完整净现金流/死亡/交易/成长仿真、机器人来源贯穿持久数据库和交易的审计、完整极值构筑/性能与人工视觉验收。

## 3. 已有测试证据

配置版本：`gdd-0.70-numerical-1`，源表原有13张表数据不改，新增NumericalRules。
五个实验布尔开关均 false；服务器和客户端配置包逐字节相同。

源提交 `8874ee8b67e3452ae7b0667c7cb01c877e9ed285`，Actions run `36423780883`：
- Domain：297通过、0失败、0跳过（已下载并读取 TRX）。
- Server：187通过、0失败、62跳过，总249；跳过包含未提供隔离PostgreSQL的数据库与真实网络用例。
- 路线工具曾因分析器失败，后在 `a4e882e8f2f0197729781b83a592b29db4ec8394` 修复，不能把旧失败执行称为10k仿真已完成。

新工作流 `.github/workflows/numerical-acceptance.yml` 提供一次性PostgreSQL18，运行整个解决方案、Domain、全部Server、1/2/4人各10000地图样本和配置校验。读取最新run结果，不沿用旧通过结论。
`.github/workflows/numerical-client.yml` 使用仓库Godot4.7，在无网络命名空间里导入并运行数值测试场景；这避免触达生产服务器。

## 4. Codex 执行任务（按顺序，不中途问同一问题）

1. 检查当前 remote、branch、工作树和新提交；不 reset/clean，不覆盖用户未提交修改。以本集成PR为基线创建独立验收修复分支，后续PR指向本分支，不能重复合并旧PR7–10。
2. 阅读GDDv0.70、基础卷、NUMERICAL_IMPLEMENTATION_20260928.md，以及实际存在的AGENTS.md。server/AGENTS.md引用的旧skill不存在时记录缺失，按实际GDD和Server规范继续，不能假称已读。
3. 执行全部编译与测试，处理最新CI失败。旧公式不是修复目标，不删除断言、不关闭分析器规避失败。
4. 使用真实CombatDeck证明候选法师在没有自然时间推进时不会靠“被动即时抽+蓄能”自维持；增加即时抽牌牌、调节牌、满手、洗牌、双抽的组合测试，区分局部证明与全卡池穷举。
5. 将所有候选开关打开仅限隔离测试配置，测试创建、快照、重连、PVP冻结副本、结束恢复、怪物池来源及重复请求。正式源表保持false；发布配置变化不得改变已存在房间。
6. 补AG04完整离线账本与日循环：成功/死亡、安全格、背包重购、药剂/刷新、市场本金转移/税收、遗物转移/销毁、机器人来源、卡牌/武器/装备成长和重建；记录失败样本，不偷看撤离点；数据由实际配置读取，价格不拍脑袋改。
7. 记录发现的规则差异：当前服务端基础掉落 `LootLayer(cell.Layer,isBoss)` 对中层精英仍查Middle层。不能在仿真里偷偷修成高档奖励，也不能未经决策改变正式投放。
8. 补机器人持久来源审计或提交明确的存储/迁移实现及测试。现有确定性ID/IsGenerated不是完整来源台账。高强化战斗装不能被复制为可交易战利品。
9. 验证UI：五语言、实际强化前后差、未激活套装和职业不适用不能误标为“超帽”、当前与下一次盾收益、怪物替换、满容量、入侵中断、重连失效选择。基础脚本测试不替代人工画面验收。
10. 汇总每个AG已实现/已通过/未跑/失败/阻塞，附sourceSha/configVersion/seed/样本数/命令/退出码/TRX/截图/性能基线/回滚说明。

## 5. 可复用命令

在仓库根目录：

```powershell
git status --short --branch
git fetch origin
# 已有未提交修改时先保留，不自动切换覆盖。
# 新建 worktree 的目标目录必须不存在。
git worktree add -b codex/numerical-acceptance-fixes ..\_FanstaryCard-numerical-qa origin/codex/numerical-integration-20260928
```

进入新worktree/server，使用 global.json 锁定的SDK：

```powershell
dotnet build FantasyCard.Server.slnx -c Release
dotnet test tests/FantasyCard.Domain.Tests/FantasyCard.Domain.Tests.csproj -c Release --logger "trx;LogFileName=domain.trx" --results-directory ../test-results/numerics
# FANTASYCARD_TEST_POSTGRES 只能指向一次性测试数据库，禁止使用生产连接串。
dotnet test tests/FantasyCard.Server.Tests/FantasyCard.Server.Tests.csproj -c Release --logger "trx;LogFileName=server.trx" --results-directory ../test-results/numerics
dotnet run --project tools/FantasyCard.Numerics -c Release -- --samples 10000 --players 1 --seed-start 0
```

Godot测试通过项目场景启动（不要再用 --script 提前编译依赖Game的界面）。自动测试须隔离外网，不能调用默认生产服务器。

## 6. 不得执行

不自动部署、重启、合并release、访问生产数据或启用正式候选。红装、厄运、钻石仍关闭。测试报告不能把Skip计为Pass，不能把GitHub Actions称为Codex实测。云端未建立仓库环境前只记录委派请求已提交，不能记录Codex运行中。
