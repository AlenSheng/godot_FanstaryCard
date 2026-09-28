# 主代理整合记录

## 工作区与保护

- 实际仓库：`F:\GitHubFiles\godot_FanstaryCard`（用户给出的带 godot 子目录路径不存在）。
- 用户后来明确授权先推送原有本地改动；12 个源码/数据/测试文件提交 `e3fed8e` 并推送 `origin/release`。原有 bin/obj、截图、缓存及临时包保留原目录，未纳入提交。
- 改造 worktree：`F:\GitHubFiles\godot_FanstaryCard-protobuf`，分支 `codex/protobuf-migration-20260928-local`，来自远端计划分支 `9ef7704`，先 cherry-pick 源码备份为 `b8e848e`。
- 未 reset、clean、stash、部署、合并或推送改造分支。
- 六个实际代理 ID 与状态见 execution-state.json；运行时 4 个槽位包括主代理，因此最多同时 3 个子代理，E 在 D 完成后启动。

## 共享整合

- Program 注册 Protobuf HTTP 中间件/服务，保留 HTTP 状态、鉴权、限流、业务事务。BadHttpRequestException 保留状态码。宿主默认请求日志关闭原始 URI 信息级日志，已有 WS OTEL query 清理保留。
- 显式旧格式开关默认关闭；既有 JSON 回归进程明确打开兼容开关，不混作默认 PB 验证。
- Retry-After 从限流租约生成，PB typed error 保留秒数。
- Contracts 官方 Protobuf 编译依赖已进入中央版本；Docker 构建上下文调整为仓库根，协议源码进入构建输入；更新脚本只修改输入清单，未执行。
- GDD 网络章、Server spec/guide、README、客户端集成文档与新传输边界一致；玩法规则未修改。
- 原有 xUnit2012 构建错误仅将 Assert.True(Any(...)) 改为等价 Assert.Contains(predicate)，未更改业务断言。
- 审查发现 mail claim-all 可在提交奖励后才超出 PB 响应预算，B 已补事务内、发奖前的完整响应预检，超限整笔拒绝；真实 PG 验证三种超限未发奖/未写成功幂等记录。

## 主代理实际验证

运行目录均为迁移 worktree，Godot 路径为 `F:\GitHubFiles\Godot_v4.7.2-stable_win64.exe\Godot_v4.7.2-stable_win64_console.exe`。

1. `python tools/generate_network_protocol.py --check`：PASS，70 realtime +61 HTTP messages，46 routes。
2. `Godot --headless --path client --editor --import --quit`：exit 0，完整资源导入；扫描日志无 ERROR / SCRIPT ERROR / Parse Error。日志 `work/godot-full-import.log`。设置 `FANTASYCARD_SERVER_URL=http://127.0.0.1:59999`。
3. `Godot --headless --path client --script res://tests/run_localization.gd`：exit 0，ok=true。日志 `work/godot-localization-final.log`。
4. `Godot --headless --path client --script <worktree>/work/run-existing-network-checks.gd`：exit 0；现有 test_session_sequence、test_session_platform、test_card_localization 均 ok=true。日志 `work/godot-existing-network.log`。测试只调用现有 run_test，不连接生产服务。
5. `git diff --check`：PASS（E 修复两处 EOF 空行后）。

Godot 导入将 622 个已跟踪 import 文件换行写回；Git 内容 diff 为空，刷新索引后无素材变更。新增测试与网关的 .gd.uid 随源码保留。

## 环境与限制

- 本机原无 .NET SDK，任务目录安装官方 10.0.400；测试使用隔离输出，未改系统安装。
- 新建本机 PostgreSQL 18.6 测试实例，只监听 127.0.0.1:54329；连接信息在任务 work 目录，不写入报告或仓库。
- 原始源码基线由 QA 在隔离目录执行，包括真实 PG。详细失败与最终对照以 QA 报告为准。
- Docker 不可用，容器构建未运行。部署 shell 脚本未执行；没有可用 bash 进行 bash -n。
- 没有真实 Steam 凭据、生产 TLS/云 ACL 验证；不将本地模拟或配置检查写成线上验收通过。
- 详细分组命令、失败迭代和证据见各角色报告；最终全量测试及性能报告由独立 QA 生成。

## 第三批发现与回修

- 畸形实时帧原先在限流前被解析并返回错误：D 把帧预算置于解码前；100 畸形帧测试覆盖错误响应上限，Realtime 60/60 PASS。
- 真实样本 GDScript PB 解码明显慢于原生 JSON：C 将 >8 KiB HTTP 响应放 WorkerThreadPool，完成后复核会话代次。真实跨语言20项、fixture19项、codec103项通过；3次后台任务推进14帧，最大帧间隔16.703ms，总等待66.723ms，对照同步主线程58.830ms。此改动改善主线程占用，并非总CPU更快。
- 服务端每字段反射导致高分配：A 缓存不可变metadata，22项协议断言（含并发）和10项边界测试通过。真实样本重建后的独立对照编码分配12.86MB→0.779MB，仍高于JSON；最终原始抓包性能以QA报告为准。
- 后台解码实现后的完整工程再次 `--headless --editor --import --quit`，exit0，无脚本解析错误，日志 `work/godot-final-parse.log`。
- 新增真实跨语言复跑入口 `client/tests/run_migration_real_server.py`：自己启动loopback .NET进程与随机PG schema，结束后清理本次资源；不连接生产。
