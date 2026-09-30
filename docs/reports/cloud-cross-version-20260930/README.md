# 固定源码跨版本兼容验证：仍不可直接部署或热回滚

本批次只在独立云环境构建测试，未连接测试服、读取服务器 `.env` 或 Environment secret、修改应用业务或部署 guard、合并 PR、推送 release/main。四个 Rooms 路径的现有兼容性阻断继续生效。预期风险成功复现不等于回滚安全。

## 固定输入与证据边界

| 用途 | 完整标识 |
| --- | --- |
| 旧服务器源码 | `8489fe97c7da71e1a5bfe1a860faf86fd4e0a4af` |
| 新应用源码 | `cc6da2e7b8a2c7ba46d867af74ce28a58ccfeac3` |
| 原样 PR14 控制器 | `262390134e98f169899d076e6fa21926d44ba1aa` |
| 两输入组合 | `c9e87904ec7ce516015defb3628481d007f77483` |
| 冻结镜像验证候选 / Draft PR17 | `94ab80ebb4585f52d2ba632ba025da0913f08876` |
| 已记录线上旧镜像 | `sha256:e7defa05caeb1188afb4cfc4390d96900bfc10afb4996ced23a042fb09132697` |
| 本批次冻结最终镜像 | `sha256:1eda55446df57d500c187540bb6aceaf52e4d7c508cd04e0c46d6b827ced3467` |

本地旧镜像 inspect 返回 No such image，见 [记录](old-image-availability.log)。跨版本测试只能证明**固定旧源码重建 DLL 替代物**的行为；没有验证真实线上旧镜像。新旧源码分别编译同一个测试 harness，通过现有友元程序集访问实际 repository、actor、registry、recovery worker、settlement coordinator；未替换应用实现。每次仅一个版本进程运行，相同隔离 PostgreSQL 数据库在各版本之间保留，各案例使用独立 schema。每次启动都执行真实 migrator，比较 26 条迁移记录的 version/name/checksum 及应用 DDL 指纹。源码工作树的 server 内容与指定 SHA 精确比较，重建 DLL 哈希列在原始报告中。

恢复 HTTP 200/503 来自真实版本的 RoomRecoveryWorker、RoomRegistry、RoomRecoveryHealthCheck 加一个 loopback ASP.NET 健康探测 fixture；**不是完整服务器 Program readiness**。冻结时钟和休眠 ticker 隔离恢复/路由行为，不证明长时间运行或负载。DDL 指纹涵盖列、约束、索引、函数和触发器，只排除明确注入的 compat_fail 故障函数/触发器。终态反例通过真实 PostgreSQL BEFORE UPDATE 触发器拒绝 snapshot 写入。

## 最终跨版本结果

[最终 attempt-6 原始报告](cross-version/attempt-6/report.json)：15 场景 / 58 次顺序运行，全部预期观察得到验证；每一阶段迁移 checksum 和 DDL 均相等。`unconditional_application_rollback_safe=false`。所有阶段原始日志在同一目录保留。

| 场景 | 实际观察 | 对回滚的含义 |
| --- | --- | --- |
| 8489 → 新 → 8489 checkpoint | revision 11 → 21 → 31；RNG、配置、玩家状态、装备及遗物内容哈希不变；存活玩家装备仍 InMatchEquipped；死亡玩家保持 Settled，独立遗物装备仍 RelicPile | 此合法 Domain 死亡生成的 checkpoint 可双向读取并重新写入；仅为有界替代物证据 |
| Launching 提交响应丢失，两个方向 | 代理在 PostgreSQL COMMIT 完成后的 ReadyForQuery Idle 丢响应；Launching 已持久化；另一版本启动同一房间后 Running；装备预留 movement 始终 1，药水始终扣到 0 | 此 fixture 未发现重复资产预留 |
| MarkRunning 提交响应丢失，两个方向 | Running 已持久化，双方恢复原房间且资产预留仍 1；新版本接受 Running 重放；旧版直接重放 MarkRunning 拒绝 | 旧版的已提交结果重试不幂等；不能把恢复成功概括为所有重试安全 |
| 新版终态 snapshot 写失败 | 内存 Dead，持久 snapshot 仍 ActionBar；snapshot failure 被记录；durable player 仍 Active、结算 0 | 新版避免在 checkpoint 未落盘时释放资产；恢复只能回到旧 checkpoint，终态内存进度仍可能丢失 |
| 旧版终态 snapshot 写失败 | 内存 Dead，持久 snapshot 仍 ActionBar，但 durable player 已 Settled、结算 1；新版恢复隔离 ready 503；旧版恢复 ActionBar 且 ready 200 | 已结算玩家复活的负向风险；旧版 200 明确不算安全通过 |
| 已结算玩家残留 ActionBar | 新版隔离旧房间，ready 503，无该玩家路由；旧版恢复 ActionBar、ready 200 | 禁止以健康 200 为回滚放行依据 |
| 旧 snapshot 与下一房间同时存在 | 新版保留下一房间路由并整体 ready 503；旧版把玩家路由指向旧房间，整体也为 503 | 健康码本身不足以发现或证明玩家路由正确 |
| 结算 COMMIT 响应丢失，两个方向 | 跨版本重放相同 receipt；receipt / hold / ledger 各 1；钱包只增加 23；首个恢复方提交 hold 1，重复提交及反向重放为 0 | 此 fixture 未发现重复结算或重复资产入账 |
| 排空拒绝 | Launching、Running 均拒绝；Pending hold 单独存在时拒绝，active=0 / pending=1 / contradiction=0；历史 Completed 的矛盾快照单独存在时也拒绝，active=0 / pending=0 / contradiction=1 | 不能只看活跃房间数量；历史矛盾数据同样阻塞 |
| 空 schema 阳性对照 | 新旧均允许，active / pending / contradiction 全 0 | 只证明 harness SQL 判定，不是已实施的线上部署排空机制 |

四类 `unsafe_observed`：旧版 MarkRunning 重放、旧版终态 checkpoint 失败、残留旧 ActionBar、旧房间抢新路由。排空 SQL 是只读验证探针，未加入部署 guard；不存在自动豁免 Rooms 的实现。

## 冻结最终镜像与 CI

[PR17](https://github.com/AlenSheng/godot_FanstaryCard/pull/17) 保持 Draft、验证专用、禁止合并。新应用源码相对 b709 仅增加七个 tools 文件；PR14 的 25 个控制器新增文件保持原样。镜像验收复用 `tools/validate_docker_server.py`，并非仅测混淆前源码。

[Cloud run 36755423176](https://github.com/AlenSheng/godot_FanstaryCard/actions/runs/36755423176) 的三个 job 全部 success。下载原始 artifact 后独立验证 ZIP digest、原始 TRX 的 579 个实际结果及执行依赖 DLL 哈希，见 [核验记录](frozen-verification.json) 和 [原始最终镜像证据](frozen-final/image-validation.json)。

- Domain 317 + Server 262 = 579 Passed，0 Failed，0 NotExecuted；执行依赖哈希匹配最终镜像的 Contracts / Domain / Server DLL。
- runtime UID 1654；重启前 16 项、重启后 12 项 HTTP/WebSocket/资产/会话检查通过；Production 本地登录 404；DB outage ready 503 / live 200 / recovered ready 200；fixture 清理通过。
- 最终镜像 artifact `11117887467` ZIP SHA256 `f32c3f60282e00bafe7396f7924fbd1aa49b311265f0c4e86912fe701b8b1255`。
- 本地事务 artifact `11117902924` ZIP SHA256 `42a30f4d95c7962d5e44480e3b25c1006d2e37214cb9ccb0d3612e3e0f10d096`。其中三个隔离事务分别 accepted / rolled_back / rolled_back，资产保留、0600 backup 与 backup list 验证通过。
- 两份 artifact 的 GitHub API head 都是 `94ab80ebb4585f52d2ba632ba025da0913f08876`，原始保留期到 2026-10-14；这里另存完整最终镜像日志/TRX，以免过期丢失。旧 `10302933` 的镜像、哈希和 PR15 证据保持独立，没有复用为本次验收。

六个适用 PR workflow 的最新结果均 success：Cloud `36755423176`、Numerical full acceptance `36755423091`、Numerical regression `36755423089`、Numerical client `36755423283`、PR13 specification `36755423127`、Gameplay load `36755423117`。Gameplay 第一次 PostgreSQL job 在 checkout 被取消，测试未执行；按其 job ID 请求重跑后，最新 PostgreSQL job `110037565773` 实际 262 Passed、0 Skipped。取消日志和成功日志均保留。**Windows server-contract 为 192 Passed / 70 Skipped，不可概括所有 job 零跳过。**原始 [Windows 日志](gameplay-windows.log) 独立保存。

## 失败与证据保留

保留 attempt-1 至 attempt-6 的全部报告和非私密诊断日志。attempt-1 的 fixture 显示名长度不合法；attempt-2 的背包参数/启动装备 fixture 不完整；attempt-3 曾通过预期观察但 checkpoint fixture 使用重复装备 ID，不采用它作为最终装备/遗物证明；attempt-4 的 dotnet 路径错误，未执行应用阶段；attempt-5 的合法 Domain 遗物 checkpoint 已通过，但 Pending hold fixture 同时有矛盾快照。最终 attempt-6 修正这些测试 fixture，显式证明 Pending hold 的独立阻塞。原失败未删除，也没有通过删除历史行、恢复 DB 或放宽业务断言解决。

每次隔离 PG 都已停止；数据目录和 0600 私有 dump 留在云工作区 `/workspace/pr14-cross-evidence/attempt-N/`，未上传 dump、数据库行、DLL、映射、fixture 身份会话值或服务器 secret。源码/日志为测试数据，发布时仍清理 Bearer/JWT/凭据赋值。最终 dump 元数据和校验和见报告。

本地 Godot CI artifact 的文件清单包含引擎自动生成的 `runtime/data/godot/keystores/debug.keystore`。没有读取其内容或另行发布到这里；仅复制明确允许的 JSON/log。未来发布控制器前，应另行审查将 local artifact 上传改为证据白名单，避免打包引擎缓存和生成的 keystore。本批次按范围要求没有修改既有控制器。

## 后续待审批事项（尚未实施）

1. 审阅 [release-controller.patch](proposals/release-controller.patch)：基于 release `28c6c7e7d3898e4d2abd186f53361477ba380330` 的精确 25 文件控制器增量，SHA256 `10030e05d4ae5d8b5448ce47720189ba958fdc48708c4b5f2eb01b21a00372d9`。这只是控制器提案；并未集成应用源码或证明旧 baseline 可回滚。另需审批 Godot artifact 白名单修正，最终发布控制器重新冻结、测试、记录 SHA。
2. 审阅 [main-registration.patch](proposals/main-registration.patch)：基于默认 main `b39841d3f5191c11c9e51c7e6875490789aba53c`，只新增同名手动入口，权限为空、唯一 job 恒为 false、无 Environment/部署/重启。SHA256 `0c13d2cf8b6f0712094e18f9fe02817417d5c792f1b558cc890611ac041fff5e`。GitHub 的 workflow_dispatch UI 要求默认分支存在工作流；[官方说明](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#workflow_dispatch)。这是注册技术依赖；release 继续是受信任工作流来源和发布基准，默认分支不变。注册后的 UI/CLI 需明确选择 release，并再次核验 controller SHA；入口实际注册尚未在线验证。
3. 审阅独占排空窗口方案，不能批准无条件热回滚。停止新入队后，在同一部署互斥锁内核对 Launching/Running、Pending holds 及历史 snapshot/settlement 矛盾全零，保存版本/路由/资产/备份/回退点，再决定固定版本上线策略。历史矛盾可能使窗口长期无法通过，任何修复需另行审批，不能删历史或恢复 DB 来放行。现有 Rooms guard 仍阻塞；需要单独设计与审查安全实现，不能填写兼容确认 true 来绕过。
4. 如以后协调线上验证，需指定真实旧镜像可复核来源或明确接受旧源码替代证据的局限、运行 baseline 与目标应用完整 SHA、已审查构建和可信 release controller 完整 SHA。部署来源 PR 必须同仓库、固定且指向 release；本 PR17 验证分支本身不是可部署来源。审批前本批次不运行部署入口。

两份 patch 再次在临时 Git index 上 apply-check 并核验结果 tree，见 [准确提案元数据](proposals/proposals.json)。没有修改实际工作树或 main/release 引用。

## 重现最终 harness

准备旧源码 detached worktree、新源码与本分支四个测试文件、已验证云工具。harness 只接受 `/workspace` 或 `/tmp` 下的 Unix socket，以及 `fc_compat_` 专用 database/schema；driver 检查 server 源码与两个固定 SHA 精确一致，再创建独占工作目录。不要指向线上数据库。

```bash
source tools/cloud/env.sh
dotnet build tools/cloud/compat/CrossVersion.csproj -c Release \
  -p:SourceRoot="$PWD" --artifacts-path /workspace/repro-compat/new -nodeReuse:false
dotnet build tools/cloud/compat/CrossVersion.csproj -c Release \
  -p:SourceRoot=/workspace/pr14-old-baseline --artifacts-path /workspace/repro-compat/old -nodeReuse:false
python3 tools/cloud/cross_version.py --work /workspace/repro-compat/fresh-run \
  --dotnet "$DOTNET_ROOT/dotnet" --postgres-bin "$FANTASYCARD_CLOUD_TOOLS/postgres/bin" \
  --old-build /workspace/repro-compat/old --new-build /workspace/repro-compat/new \
  --old-source /workspace/pr14-old-baseline --new-source "$PWD"
```

driver 最后的退出码 0 仅表示所有指定的正/负观察按预期出现且隔离 PG 成功停止。评估回滚必须同时读取 `unsafe_observed`、`unconditional_application_rollback_safe` 和上述证据边界。
