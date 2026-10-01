# A05.1 固定源独立重放

运行源固定 `62772be2a1bc28affffc3d057f259c8c5ded8e37`；生产 guard 为 `7231c7499b7220b85c27be48ebbd127d7c0b7038`，唯一生产路径 `client/state/game_store.gd`。本目录是去敏派生产物，原私有 2173 文件逐字节校验见 PRIVATE_ARTIFACT_MANIFEST、PRIVATE_ARTIFACT_SEAL 与 EXPORT_PROVENANCE。原始报告、账号、PB 和日志留在授权云本地，未上传新目的地。GUID 值用稳定 SHA256 别名保留前后归属关联；接口路径中的 GUID 也去敏，artifact 文件名保持原样。

先从可访问的仓库固定提交物化源码：

```bash
source /workspace/relicround-env/activate.sh
python3 docs/reports/pr13-takeover-20260930/a05-guard-62772be2/prepare_fixed_source.py --repo /workspace/godot_FanstaryCard --source 62772be2a1bc28affffc3d057f259c8c5ded8e37 --output /workspace/pr13-independent-a05-62772
```

按 minimal-replay.json 建立全新的私有 Unix PG（listen_addresses 为空、独立 data/socket/端口，禁止既有或远程 DB），设置其环境字段后，在上述新 source 的 server 目录实际执行：

```bash
dotnet restore FantasyCard.Server.slnx -p:NuGetAudit=false --source /workspace/relicround-env/nuget
dotnet build FantasyCard.Server.slnx -c Release --no-restore
dotnet test tests/FantasyCard.Server.Tests/FantasyCard.Server.Tests.csproj -c Release --no-build --logger 'trx;LogFileName=server.trx' --results-directory ../independent-results
```

要求 FANTASYCARD_PROCESS_SERVER_DLL 指向新 source 内 Release DLL，FANTASYCARD_PROCESS_SOURCE_SHA 精确为上述62772，FANTASYCARD_PROCESS_EVIDENCE 指向新的证据目录；同时设置真实 Godot 和私有 FANTASYCARD_TEST_POSTGRES。不得用 filter 替代完整 C-SERVER。预期299/0/0、canonical3Passed、原 causal 两个stale均false、ordinary/ACK丢响应权威核实/newN/资产与下一准备取消全部通过。C-AUDIT 在套件内实际执行 READ ONLY/ROLLBACK，SQL副本已留存。最后核验 own schema/connection 及子进程终态后只停止清理本次 PG，保留日志；退出 zombie 条目与活跃服务区别记录，不碰 PID1。

原2dda恢复M旧poll反例与76d relay204夹具失败均保留。后者真实backend204被空body写入触发Kestrel异常导致三次取消响应中断，62772仅修夹具转发，未去掉取消/资产断言。两类失败不可归于环境或用最终299覆盖。原始前失败在 RED_RECEIPT 和 GREEN1_FIXTURE_FAILURE 中分别定位。S0–S5完成，S6只由MAIN独立重放裁决；没有LIVE、CI或人工新增门槛，不代表全132或G0–G5通过。
