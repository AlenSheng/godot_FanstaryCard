# 固定 0d4ec7f2 relay 验证

执行源 `0d4ec7f23df806da7a86f9d954033a718349de7e`，上游 `419961a86b2bbcaacf96eaafa5e21ded3b722a79`；两种配置使用相同固定源码和源目录内部新编译 Release。准确 argv/cwd/env/工具版本在 [minimal-replay.json](minimal-replay.json)、[report.json](report.json)。PG 必须是复验者自己的隔离本地集群；原测试数据库已停止删除，不访问外部数据库。

源码目录内构建：

```bash
source /workspace/relicround-env/activate.sh
cd <fixed-source>/server
dotnet build FantasyCard.Server.slnx -c Release --nologo
```

对同一隔离 PG 分别设置 Unix socket 路径和 `127.0.0.1` 的 `FANTASYCARD_TEST_POSTGRES`；设置 `FANTASYCARD_PROCESS_SERVER_DLL` 为上述源码内部 Release DLL，`FANTASYCARD_PROCESS_SOURCE_SHA` 为完整0d4e，`FANTASYCARD_PROCESS_EVIDENCE` 为新的证据目录。保留原连接池和测试预算：

```bash
dotnet test tests/FantasyCard.Server.Tests/FantasyCard.Server.Tests.csproj \
  -c Release --no-build \
  --filter FullyQualifiedName~A05_actual_settlement_transaction_fault_recovers_without_duplicate_assets \
  --logger 'trx;LogFileName=relay.trx' --results-directory <new-evidence-directory>
```

Unix和TCP各期望2Passed/0Failed/0Skipped；需同时核实际relay transport、提交前0receipt/可重试、提交后1receipt/真实OS重启、3次相同ACK、23gold/2potions及原owner/装备/ledger/movement exactly once、最终只读审计和owned进程/PG清理。不能只用 TRX 代替真实事务/客户端断言。

前失败来自419的两个实际CI job，各300/2/0，构造函数在注入前拒绝127.0.0.1。[red-ci-provenance.json](red-ci-provenance.json)保持来源；没有另造本地RED运行。固定0d4e的后CI日志/ZIP/TRX已核，[CI_TERMINAL.json](CI_TERMINAL.json)记录4成功/1失败，不能宣称整套通过。

新增失败为LOAD02 observer最终文件尚未写完便被C#读取：Gameplay首次读空，归档最终1877字节合法JSON；完整acceptance同源该例通过。原子发布是未应用的最小后续设计。旧MarkRunning Running/Launching根因也未动态确认；此relay回归不代签A05.1或关闭其它132任务。
