# Bootstrap 偶发超时定位与查询合并

## 结论

已复现并修复一个导致 Bootstrap 并发超时的确定性资源生命周期缺陷：`MailRepository.GetAsync` 对同一个 Npgsql reader 提前释放一次、离开 `await using` 作用域再释放一次。首次释放将隐式连接归还池；Npgsql 10.0.3 会复用该连接上的 reader 对象，旧引用的第二次释放因此可能关闭另一个请求正在使用的 reader。

这个竞态会造成数据库协议响应错位、HTTP 500 或等待超时。复现现场数据库连接为 idle，无锁阻塞；服务日志出现 `NpgsqlOperationInProgressException`、`Received backend message ... while expecting ...`。不是仅根据“连接池小”推断，也没有靠延长超时或增大连接池掩盖问题。

这证明了本次复现的超时原因。此前仅有失败堆栈而没有同步诊断的 60/100 秒历史事件，不能逐例断言一定同因。

## 证据链

真实本地 Caddy TLS → ASP.NET → PostgreSQL，同一账号，8 并发、40 次 Bootstrap：

| 实验 | HTTP 200 | HTTP 500 | 10 秒超时 |
| --- | ---: | ---: | ---: |
| 修复前普通 Debug | 31 | 2 | 7 |
| 修复前普通 Release | 29 | 4 | 7 |
| 修复前混淆 Release | 25 | 8 | 7 |
| 仅修邮件 reader 生命周期，普通 Release | 40 | 0 | 0 |
| 再合并 6 个纯读查询，普通 Release | 40 | 0 | 0 |

随后合并版本 8 并发 **200/200 成功**。日志分别在 `work/timeout-investigation/{ordinary-before,release-before,concurrent-1,mail-only-after,batch-after,batch-stress-200}`。各次独立冷启动、独立 schema，失败证据没有覆盖。不同构建/负载下的单轮耗时不作为性能提升比例。

另外新增真实 PG 确定性测试：连接池上限 1，明确断言旧 reader 与下一次借用的 reader 为同一实例，第二次释放旧引用会使新 reader 的读取抛 `ObjectDisposedException`。修复后的邮件读取在同样单连接池、8 并发共 80 次调用全部通过。这独立验证了资源复用机制，不依赖压测碰巧触发竞态。

官方源码依据（锁定实际依赖 v10.0.3）：

- [NpgsqlCommand：获取 connector.DataReader 并重新 Init](https://github.com/npgsql/npgsql/blob/v10.0.3/src/Npgsql/NpgsqlCommand.cs)
- [NpgsqlDataReader：Init 重置状态，DisposeAsync/Close 处理当前 reader 状态](https://github.com/npgsql/npgsql/blob/v10.0.3/src/Npgsql/NpgsqlDataReader.cs)
- [Npgsql 批量查询说明](https://www.npgsql.org/doc/basic-usage.html#batching)

## 修复与合并方式

1. 邮件首条查询的 command/reader 放进独立词法作用域；完全结束后才读取未读计数。reader 只由 `await using` 释放一次。
2. 审核另外 9 处手动 reader 释放：均持有显式连接至外层作用域结束，未发现相同的跨请求归池窗口，没有扩大修改范围。
3. Bootstrap 的钱包、材料、职业武器、配装、未完成对局、未完成结算 **6 个查询改为一个 NpgsqlBatch、一个连接、6 个结果集**。保留原 SQL 条件、排序、空值、玩家隔离和错误语义。没有将一对多表大 JOIN 造成行数相乘。
4. 顶层并行任务从 **13 路降为 8 路**；被合并部分由 6 次借连接/数据库往返改为一次批量发送。SQL 仍是 6 条，不宣称变成一条 SQL 或整个 Bootstrap 只用一条连接。
5. 商店每日初始化有写入及行锁，保留其事务边界。卡组、卡牌、背包、市场、邮件和准备状态维持现有仓储接口；本轮不强行重写所有模块。
6. TLS 验证工具增加 `--bootstrap-concurrency` 和 `--bootstrap-requests`，保存每次状态/时长，遇到任何失败返回失败。唯一输出目录防止覆盖证据。

## 回归验证

- Reader 生命周期真实 PG 测试：2/2，零跳过。
- 新增批量查询映射/过滤/取消测试：3/3；最终全套再次覆盖显式 `Pooling=true` 的两连接池恢复验证。
- 实际 Godot → .NET → PG：20/20，包含二进制登录、Bootstrap、客户端操作及 WSS；完整客户端导入成功。
- 普通全解决方案：**466/466，零失败、零跳过**（Domain 222、Server 244）。TRX 位于 `server/.artifacts/timeout-final/results`。
- 重新生成的混淆包 `builds/server-protected/server-lgiop4qw`：**466/466，零失败、零跳过**；测试依赖与最终包的三个生产程序集 SHA-256 一致。Server 测试 3 分 36 秒。证据在任务工作区 `work/remediation-tools/server-validation-4g0y7kbs`。
- 该最终混淆包的真实 TLS/WSS 边界检查 **21/21**，其中新增并发验证包含 **200/200 成功**的 Bootstrap 请求；证据 `work/timeout-investigation/protected-stress-200`。
- 生成检查仍为 70 realtime +61 HTTP 消息、46 路由；未产生协议漂移。

实际命令（路径参数指向任务专用工具、私有本地连接文件；日志不输出密码）：

```text
dotnet test FantasyCard.Server.slnx --artifacts-path .artifacts/timeout-final --results-directory .artifacts/timeout-final/results --logger trx;LogFilePrefix=timeout-final
python tools/verify_local_tls_proxy.py --dotnet <dotnet> --server-dll <tested-dll> --psql <psql> --connection-file <private-local-file> --caddy <caddy> --work-dir <unique-output> --bootstrap-concurrency 8 --bootstrap-requests 200
python client/tests/run_migration_real_server.py --godot <godot> --dotnet <dotnet> --psql <psql> --connection-file <private-local-file> --work-dir work/timeout-investigation/godot-final --skip-scheduling
python tools/generate_network_protocol.py --check
```

混淆验证复用 `export_protected_server.export_server()` 与 `validate_protected_server.validate()`，PRIVATE 重定向到忽略的任务工具目录，实际执行 Release build/publish、Obfuscar、全新本地 PG 上的完整 `dotnet vstest`。原始日志 `work/timeout-investigation/{solution-final,protected-final}.log`。独立测试首轮仅因缺少 namespace 导入编译失败，补齐后通过；未放宽任何业务断言。所有测试进程及专用 PG 在结束后停止，临时 schema 清理，原始证据保留。

本次未改协议 schema、战斗规则、生产超时阈值或连接池大小。未推送、部署、合并 release/main。原用户工作区保留，全部验证使用本地专用数据库和临时 schema。
