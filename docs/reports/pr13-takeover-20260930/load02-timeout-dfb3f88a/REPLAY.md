# LOAD-02.2 固定源独立重放

运行源固定 `dfb3f88a73efd85cc4ed12b8d49038bebbb1f953`，是在 A05 已验证源 `62772be2a1bc28affffc3d057f259c8c5ded8e37` 上添加三个隔离测试文件，没有新增生产或 UI 修改。原始日志/账号/PB 留在授权云本地；Git 提供去标识派生报告和原始 SHA 索引。原始 manifest/seal 与公开 MANIFEST 分别标明，不能将派生字节误作原日志。

先运行已实际验证的源码准备器；它只读授权本地 Git 对象，核验 967 文件并提供原 Python 工具所需的真实固定 HEAD。结果是声明的部分源码副本，并非干净完整 checkout：

```bash
source /workspace/relicround-env/activate.sh
python3 docs/reports/pr13-takeover-20260930/load02-timeout-dfb3f88a/prepare_load02_fixed_source.py --repo /workspace/godot_FanstaryCard --output /workspace/pr13-independent-load02-dfb3
```

按 `minimal-replay.json` 初始化新的私有 Unix PG：独立 data/socket、`listen_addresses=''`、空闲端口、host reject，不访问已有或远程数据库。设置其中的 FANTASYCARD_TEST_POSTGRES、真实 Godot、源码内部新 Release DLL、唯一证据目录和精确 FANTASYCARD_PROCESS_SOURCE_SHA。在新源码实际运行：

```bash
cd /workspace/pr13-independent-load02-dfb3/server
dotnet restore FantasyCard.Server.slnx -p:NuGetAudit=false --source /workspace/relicround-env/nuget
dotnet build FantasyCard.Server.slnx -c Release --no-restore
dotnet test tests/FantasyCard.Server.Tests/FantasyCard.Server.Tests.csproj -c Release --no-build --logger 'trx;LogFileName=server.trx' --results-directory ../independent-results
cd ..
python3 -m unittest discover -s tools/tests -v
```

C-SERVER 必须不带 filter，预期 302/0/0；C-PY 122/0/0。可先用 `FullyQualifiedName~Real_LOAD02_timeout_STOP_preserves_original_business_truth` 定向三个窗口，但它不能替代完整 C-SERVER。首次 C-PY 因部分源码没有 .git 而出现 10 个 git rev-parse 异常，原日志与 Git 元数据修复收据保留；相同源码补足真实固定 HEAD 后才通过，不称业务修复。

T01：真实 preparation 三次无响应，原 10s 单次/30s 逻辑预算耗尽并产生原 failed check 后才 STOP；原客户端 exit1，failed1/cancelled0，原错误不消失。第三次单次时长受剩余逻辑预算限制，未调低预算。
T02：真实 ACK 提交前等待时 STOP；原错误为零，最终 cancelled1/completed0/failed0。
T03：相同 ACK 三次实际 backend200 后丢响应，PG已确认而客户端仍 pending；STOP 快照 pending1，放行已实际读取完整 Bootstrap 后才结束 cancelled1，无重复资产或 cycle.completed。保留 ACK 运输错误，不据此猜业务失败。

三个案例都实际核验原上下文、资产前/STOP/后、完整 Bootstrap 三个未完成字段为空、下一次真实 preparation/cancel204 可用。观察器从原 scenario/checks/finish 记录一个 cycle 的分区，原生产报告为 outcome 主证据；这里没有实现或验收 LOAD03 全路线/全程/三截止点 telemetry。

最后核验所有记录的 host/Godot 进程已退出，私有 PG 只读最终 schema/connection 状态，停止并清理仅本次 data/socket，保留日志。S0–S5 齐备后只提 Ready；S6 由 MAIN 独立重放裁决。不增加本合同未要求的 LIVE/CI/人工门槛，不外推 132 子任务、G0–G5 或全局 ledger。

最终 PR CI 另有 release `65361bcc27c51c28651c86c5dbba4f083a9b39e0` 与当前 PR13 的 numerical-client.yml 合并冲突，见 NEW_RELEASE_CI_CONFLICT；属于父任务 controller/CI 协调边界，本批没有合并/编辑该文件、启动中间 CI 或改变账户额度。
