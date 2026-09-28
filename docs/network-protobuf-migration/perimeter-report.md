# fc_perimeter 执行报告（2026-09-28）

执行者：真实子代理 `/root/fc_perimeter`；任务 E，独立 worktree `F:\GitHubFiles\godot_FanstaryCard-protobuf`。未提交、推送、部署或修改云安全组/证书。

已阅读 PLAN、角色 TOML、server/AGENTS.md、GDD 网络相关章节、SERVER_SPEC、SERVER_0_TO_1_GUIDE 与 CLIENT_INTEGRATION。仓库引用 `.agents/skills/server_create/SKILL.md` 不存在，已按 PLAN 记录。

## 实际改动

- `server/Caddyfile`：保留三个入口与管理阻断顺序；游戏 HTTP 请求上限 2097152 字节，管理入口 65536 字节；read_header 10s、read_body 30s、upstream dial 5s、response_header 30s。未设 WebSocket 总寿命或 write timeout，未把实时 16KiB 限制提升为 HTTP 预算。
- 代理响应 `private, no-store`，既有 nosniff 保留；不重写 Content-Type、不转换二进制、不缓存响应。
- 默认 Caddy runtime JSON 日志删除 request.uri 和 request.headers，避免反代 502 错误也记录 ticket/token/Admin-Key。未开启 access log。今后若单独启用 access logger，必须为新 logger 同样配置过滤器，不能假定自动继承。
- `server/src/FantasyCard.Server/Admin/AdminEndpoints.cs`：所有进入页面/授权过滤器的响应（含 401/403/503）都设置 private no-store/nosniff；既有常时密钥比较、HTTPS 判定、审计、权限、限流、事务未改。
- `server/tests/FantasyCard.Server.Tests/Deploy/ProtobufPerimeterTests.cs`：6 个运行时用例验证管理页成功/拒绝以及 API HTTPS/错误密钥/正确密钥与安全头。
- `perimeter-exceptions.md`：逐方法/路径记录公开公告、只读公告 WS、全部管理接口、健康检查与静态内容例外。公告仍归 Admin/ClientSettingsEndpoints，未改 JSON 语义或页面内容。

## 实际执行的验证

Windows；.NET SDK 为任务本地 10.0.400；官方下载 Caddy `v2.11.4 h1:XKxkMTgNSizEvKG6QHue6cAsFOteU2qA61w2tKkCWi0=`。以下命令在 server 目录，工具在 `.artifacts/perimeter/`，DOTNET_ROOT/PATH 指向任务本地 SDK。

```text
dotnet test tests/FantasyCard.Server.Tests/FantasyCard.Server.Tests.csproj --artifacts-path .artifacts/perimeter/dotnet --filter "FullyQualifiedName~Deploy|FullyQualifiedName~Admin" --logger "trx;LogFileName=perimeter.trx" --results-directory .artifacts/perimeter/results
```

最终结果：20 passed / 0 failed / 0 skipped（含已有管理、本地化公告及 Caddy 结构测试）；TRX `.artifacts/perimeter/results/perimeter.trx`。新增 6 个用例实际执行，不只是静态断言。先前未添加新测试的运行 14 passed、中间运行 17 passed，均不替代最终结果。第一次创建测试文件误用相对路径导致写入失败，随后在正确目录创建并重跑成功；无项目文件被错误覆盖。

```text
.artifacts/perimeter/caddy.exe adapt --config Caddyfile --adapter caddyfile --pretty
python .artifacts/perimeter/probe.py
```

原 Caddyfile adapt 成功。probe 派生本地 HTTP 配置：仅将三个监听改为 127.0.0.1:58081/58082/58083、上游改 127.0.0.1:58080、关闭自动 HTTPS/admin API、删除生产 IP 证书引用、静态目录改本地；不写原生产地址、不接触真实证书。派生配置 `caddy validate` 成功，实际启动 Caddy + Python 假上游，14 个检查通过：

1. 公告 JSON 类型与正文保留。
2. 响应 private no-store/nosniff。
3. 1,536,000 字节 Protobuf request/response 逐字节相同、Content-Type 保留（特意大于错误的 1MB 代理上限）。
4–7. 公共 `/admin`、`/admin/`、`/api/admin`、`/api/admin/players` 均 404。
8–10. 管理路径代理成功、管理入口游戏 API 404、原 IP 路由 404。
11. 静态官网返回 200。
12. 2,097,153 字节请求被拒绝 413。
13–14. 关闭假上游后 session URL 返回 502；实际错误日志没有测试 ticket、access_token、Authorization 或 X-Admin-Key 秘密值，request URI/headers 已删除。

证据：`.artifacts/perimeter/caddy-adapted.json`、`Caddyfile.local`、`probe.py`、`probe-output.log`、`runtime-results.json`、`caddy-runtime.log`。探针超限 POST 使假上游打印预期的连接中止异常，客户端实际收到 413，所有断言通过。测试进程已终止，所有监听仅本机。探针文件是本地测试证据，不属于生产构建。

## 尚未验证与后续

- 没有运行生产证书环境的完整 Caddy validate、真实 HTTPS/WSS 握手、云安全组、真实管理员浏览器操作或容器构建；本地 HTTP 路由证据不能替代这些项目。
- 公告数据库读取/广播、完整管理审计的集成回归由第三批 QA 执行；此处已有公告内容 JSON 序列化测试通过。
- 新 Caddy read_body 30s 约束慢速 HTTP 上传；正式发布前应检查最低支持网络条件。未对实时 WSS 消息设置新的代理总时限。
- 本地验证版本 2.11.4；部署 compose 原 `caddy:2-alpine` 浮动标签未改，实际部署版本仍需发布时核对。
- 日志过滤有意减少故障日志的路径与请求头信息；仍保留方法、主机、状态、耗时及 err_id。应用日志与 OpenTelemetry 的 session 查询脱敏由主代理负责整合。

回滚：只审核撤回本报告列出的 Caddy/Admin 改动和新增测试；保留公共管理阻断及 HTTPS，不能以回滚为由开放管理入口或记录凭据。

官方语法参考：https://caddyserver.com/docs/caddyfile/directives/request_body 、https://caddyserver.com/docs/caddyfile/directives/reverse_proxy 、https://caddyserver.com/docs/caddyfile/options 。配置语法以本机 Caddy 实际 adapt/validate 为证据。
