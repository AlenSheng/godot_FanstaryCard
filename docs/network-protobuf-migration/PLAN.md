# FanstaryCard 网络协议迁移：评估与 Codex 执行任务

## 0. 基线与交付状态

评估日期：2026-09-28。仓库：AlenSheng/godot_FanstaryCard。
审阅基线：release / 80148675dfbb974a4b0bdc79a9234c67a75bba49。
用户本地路径：`F:\GitHubFiles\godot\_FanstaryCard`；本次未访问该目录，不能确认未提交变更或当前本地分支。

本提交仅交付评估、六个自定义子代理角色和执行入口。**没有启动子代理，没有完成业务迁移，没有运行项目构建、Godot 或 .NET 测试。** `execution-state.json` 中的代理 ID 必须在真实调用成功后才填写。

## 1. 架构决定

HTTPS 是安全传输，Protobuf 是序列化格式，二者不互斥。建议保持现有传输拓扑，只统一游戏 API 的消息契约。

| 边界 | 目标 | 迁移原则 |
|---|---|---|
| 公告、官网、管理后台、登录前的版本/维护状态 | HTTPS + JSON/静态内容 | 保留外围生态与现有管理隔离 |
| 游戏客户端登录、档案、Bootstrap、卡组、养成、市场、邮件、匹配及结算查询/领取 | HTTPS + 二进制 Protobuf | 保留 HTTP 方法、鉴权、幂等和错误语义 |
| 房间、战斗指令、实时推送、会话恢复 | WSS + Protobuf | 复用现有 v1，不重写 RoomActor |
| Steam 等平台验票、第三方通知回调 | 平台要求的格式 | 仅第一方客户端边界统一 proto，不篡改外部平台协议 |
| 资源、图片、视频、配置包下载 | HTTPS + 对应文件格式 | 不把资源塞入战斗消息；已有配置 proto 无需退回 JSON |

不采用“登录之后全部挤进一个 WebSocket”作为首轮目标；不引入裸 TCP、自定义加密或全量 gRPC。登录请求本身也可以是 HTTPS + Protobuf，不要求先建立匿名长连接。客户端 UI、领域对象、内部信号无需全部改成 protobuf 类型。

## 2. 已确认的源码事实

以下是对基线源码的静态检查，不是线上抓包或完整运行时审计。

- `client/network/gateway.gd::request` 使用 application/json、JSON.stringify 和 JSON 解析；同一逻辑请求的重试保留同一 Idempotency-Key，并有 session_generation 防止旧会话回调污染。
- `server/src/FantasyCard.Server/Realtime/RealtimeEndpoints.cs` 已只接受二进制 Protobuf；`gateway.gd::send/_receive` 已编码/解码 protobuf。`server/README.md` 的 JSON WebSocket 示例已落后。
- `protocol/realtime/v1/realtime.proto`、客户端 `realtime_schema.json` 和 C# `RealtimeProtobufCodec.cs` 不是可靠的单一生成链：已读 C# 编码段写入 BattleComboResolvedEvent 的 24/25/26 字段（ResonanceMultiplier、ConflictPairCount、ConflictCancellation），而 .proto 只声明至 23；C# 和 gateway 还使用 MapPlayerCountEvent，但该 .proto 未声明它。先依据实际线上兼容线格式核对，不能直接拿旧 .proto 覆盖生成物。
- `client/network/protobuf.gd` 是自写字典式编解码器，已支持的数值标量仅 int32/int64/uint32/bool；已知数值字段要求 wire type 0，不能解码 packed repeated 数值字段的 wire type 2。现有 `.proto` 的 repeated int32 safe_slot_indexes 在标准 proto3 中默认可使用 packed 编码。
- 服务端单条上行消息限制 16 KiB；客户端 protobuf 解码也限制 16 KiB、嵌套深度 24，虽 WebSocket 入站缓冲是 64 KiB。大背包/大厅全量响应不能直接复用同一硬上限。
- WebSocket 当前把 access_token 放入 URL 查询参数。存在代理/访问日志记录凭据的风险，但本次未发现或验证实际泄漏。
- `server/Caddyfile` 已提供域名 TLS，公共站点阻断管理路径，独立管理入口在 20000 端口。配置注释要求云侧限制管理员 IP；本次未验证云安全组的实际状态。

## 3. 收益、代价与约束

主要收益是消息结构集中维护、跨端字段对齐、整数语义更明确，以及减少重复字段名带来的潜在带宽收益。不是“换成 proto 就自动更快”：GDScript 逐字段解释、Dictionary 分配、HTTPRequest 生命周期和数据库耗时都可能主导延迟。Protobuf 也不等于压缩、加密、防作弊或可靠投递。

主要成本是协议生成与版本治理、二进制排错工具、跨语言一致性测试、灰度期双格式维护。全改 WSS 还会新增请求关联、超时、断线结果查询、背压、匿名连接限流及经济写入去重等工作。本方案通过保留 HTTP 单次调用和现有实时通道控制迁移面。

实施硬约束：

1. 生产全程 HTTPS/WSS，校验证书，不降级明文，不把二进制不可读当成安全措施。
2. 网络边界使用真正的类型化 protobuf 消息，不能将 JSON 字符串塞入 bytes 伪装迁移。HTTP 使用 application/protobuf，正确处理 Content-Type/Accept、nosniff、空响应及代理的非 protobuf 错误。协议版本放应用契约或显式版本路由，不冒用 MIME 保留 version 参数。
3. 保留 v1 字段号、类型与 presence 语义；删除字段 reserved。新增金额/数量/版本字段明确范围，金额不改成浮点；现有 decimal 字符串不做破坏性批量转换。
4. 同一经济操作跨重试、JSON/PB 灰度与断线只能提交一次。请求 ID、幂等键、服务端事务/唯一约束缺一不可；去重内容按规范化领域操作计算，不依赖 protobuf 原始字节相等。
5. JSON 兼容仅按已知旧客户端、独立入口或显式协商启用。禁止“解析失败就自动回退并重发写请求”。建立每个 HTTP 方法+路径模板对应 Request/Response 的清单；有意例外逐条列出。
6. 16 KiB 实时预算不盲目放开。HTTP 大列表分页；分别约束整包、字符串、集合长度、嵌套、接收超时及发送队列。必须先量测真实房间快照，再设定有界预算。
7. 鉴权、限流、玩家隔离、封禁/过期/踢下线、sequence/revision、回放去重与房间恢复不得退化。长连接消息仍检查有效会话及操作权限。
8. 新方案优先采用鉴权后的 HTTPS 短期、单次 WebSocket ticket，原子消费并绑定玩家/会话；ticket 也须脱敏。原生端支持时可评估 Authorization 头。不要把登录凭据写入事件重放或遥测。

## 4. 主代理执行指令

你是本迁移主代理。用户已要求开始改造，不要停在重复计划；但只有真实创建的子代理才能标记已启动。

### 4.1 执行前检查

记录 git 根目录、HEAD、分支、工作区状态，确认 origin 指向上述仓库但不要输出带认证信息的远端 URL。不得 reset --hard、clean、自动 stash/drop、覆盖未提交文件、强推、清库、部署云端或合并 release。当前任务只能在独立 codex/protobuf-migration-* 分支执行。若本机工作区不同于审阅基线，先核对实际代码差异并更新评估；不能把远端快照冒充本机最新状态。

先读所有适用 AGENTS.md、GDD 网络章节、docs/SERVER_SPEC.md、docs/SERVER_0_TO_1_GUIDE.md 和服务端联调文档。旧 `.agents/skills/server_create/SKILL.md` 引用如果确实缺失，记录缺失即可；这不豁免其他有效规则。规则冲突只阻塞相关任务，继续无冲突任务，不自行改玩法规则、数值、数据迁移历史或保护配置。

检查 Codex 版本与可用子代理工具。`.codex/agents/*.toml` 定义了以下六个角色。真实创建后将工具返回的 agent/thread ID 记入 execution-state.json，并记录开始时间、作用域、状态、测试证据。若当前运行时不能创建子代理，明确记录 blocked，不得用六段自说自话冒充并行执行；可以继续主代理独立检查，但必须标明执行者。

本任务最多同时开放四个子代理线程。模型沿用当前可用配置，不擅自切换高价模型或绕过审批/沙箱。执行前创建路径归属清单；共享文件仅主代理整合。每个子代理只写自己的路径并向主代理报告必要的跨界改动。

### 4.2 调度顺序

第一批：A 协议契约 + F 只读基线审计（F 此时不编辑共享文件，测试使用隔离输出/工作区）。A 先修复契约漂移并交付 wire 兼容对照和冻结的端点/消息映射。

第二批：A 完成后，B 服务端 API、C 客户端、D 实时会话、E 外围四组并行。A 的 schema/生成物继续只有 A 一个写入者；需要新增字段由主代理协调 A，不能由其他组私自手填。

第三批：主代理整合 Program.cs、构建依赖、配置开关和变更清单，然后 F 实施集成测试与性能对照。发现失败按原所有者回修，跑通后才允许提交完成状态。

不要同时让多个工作线程执行全仓库 git add/commit、重生成全部协议或修改同一 gateway.gd。主代理最终统一提交，使用显式文件清单，不自动 push/merge/deploy。

## 5. 六组任务及验收

### A — fc_protocol：契约与生成链

所有权：protocol/**、协议生成脚本、client/data/realtime_schema.json、server/src/FantasyCard.Contracts/**；其余生成路径由主代理登记后纳入同一所有者。

核对 .proto/C# codec/GDScript schema 三者，补齐 24–26 字段与 MapPlayerCountEvent 的实际线格式；检查其他漂移，不限于上述样本。建立 `.proto` 单一来源、可重现生成与检查命令，新增第一方 auth/game HTTP 消息和注册表。C# 优先评估官方生成器；Godot 保持当前 GDScript 客户端，不为了 proto 强行换语言。保留生成消息与领域 DTO 的适配边界。

验收：旧合法 v1 数据仍能读取；标准参考实现与两端的 golden vectors 互通，比较解码语义而非要求二进制顺序相同。packed/unpacked、未知字段、optional 与零值、负数和 int64 边界、嵌套重复消息、畸形/超限数据均覆盖。新 schema 不引入客户端不支持的类型；生成后无未解释差异。输出 protocol-compatibility.md 与端点注册表。

### B — fc_server_api：登录与非实时游戏 API

所有权：server/src/FantasyCard.Server 的 Identity、Bootstrap、Players、Progression、Mail、Matchmaking、Settlement 中 HTTP 适配文件，以及本任务新建的 Protobuf HTTP 边界目录；不改 A 的 Contracts、不改 D 的 Realtime、不擅改领域服务。

按端点清单接入二进制请求/响应、typed errors 与服务端验证，复用现有应用服务、权限、事务及去重。先完成 login -> bootstrap -> player/deck 的纵向闭环，再补齐装备/养成/市场/邮件/匹配/结算。第三方平台验票保持平台接口协议。保留 Development-only 本地登录边界。

验收：所有第一方内部端点均有 protobuf 方案或明确待办，不允许只改 login 就宣称完成。401/403/409/429、Retry-After、取消与大列表限制正确；同一次经济写入跨格式重试不重复扣费或发奖；旧 JSON 只受显式兼容控制。

### C — fc_client：Godot 网络边界

所有权：client/network/**、必须调整的 client/state/** 与 client/platform/** 网络调用边界；UI 调用点只做必要适配并先登记，不动界面布局、玩法表现及 A 的生成物。

使用 Godot 二进制 HTTP 请求接口，分离 perimeter JSON 与 game Protobuf 的显式调用。根据端点注册表进行 Request/Response 类型映射；不能用通配“所有 /api/ 都是 proto”误伤公告。修复/替换自写 codec 的标准兼容缺口，维护 UI 字典/信号适配层。

保留 session_generation、内存 token、固定幂等键、过期退出与错误展示。与 D 协调 ticket 接入但 gateway 由 C 单独编辑。禁止网络解析失败后静默发起第二次业务写入。

验收：登录到大厅再进房间的正常与断线流程可运行；查找 JSON 请求及所有 request 调用点生成覆盖报告；保留的外围 JSON 有明确清单；大 int64 不经 JSON 浮点往返；旧会话回调不污染新会话。

### D — fc_realtime：会话与实时通道

所有权：server/src/FantasyCard.Server/Realtime/** 及该目录新建 ticket 服务；客户端修改提交给 C，消息契约提交给 A，Program.cs 注册交给主代理。

保留 WSS v1 与现有 RoomActor 路由，补齐鉴权 ticket、服务端有效会话校验、接收/发送资源预算与明确关闭原因。检验分片累计大小、畸形包、防重放与连接替换。不要为了 HTTP proto 迁移重写全部战斗实现，也不把大列表放入实时队列。

验收：ticket 过期/重复使用被拒绝，日志无凭据；旧客户端兼容开关可回滚；session.resume、事件重放、快照恢复、同账号接管、seq gap、封禁/过期均有测试；慢连接不会导致无界发送队列。

### E — fc_perimeter：公告、后台与边界配置

所有权：server/Caddyfile、server/site/**、server/src/FantasyCard.Server/Admin/** 和外围接口说明。公告真实所属模块先查明，若与 B 重叠则由主代理划分具体文件，不并发编辑。

保留 HTTPS/JSON；将公告、版本及管理端点加入外围例外清单。检查反向代理对二进制内容类型、缓存、大小与超时的行为；不得缓存私人响应或记录 token/ticket。保持公共管理路由阻断与管理端隔离，不扩大公网暴露，不更换生产证书或操作云防火墙。

验收：外围页面正常，公告仍可获取，公众入口无法访问管理 API；管理员权限/审计不退化；配置变更仅生成待审核文件与本地测试证据，不执行生产部署。

### F — fc_qa：独立验证与性能对照

所有权：server/tests 下新增迁移测试文件、client/tests 下新增迁移测试文件、tools 下新建本任务基准脚本；A 的参考向量/生成物不直接改。第一批只审阅并记录基线，第三批写测试。共用测试工程引用由主代理整合。

覆盖：第一方登录方式、Bootstrap/档案/卡组、装备和养成、市场买卖、邮件领取、匹配取消/确认、进房间出牌/拾取/撤离、结算、重连恢复、重复请求、权限隔离与旧客户端兼容。新增源码静态覆盖检查防止内部端点漏迁，但不能替代运行时测试。

测试命令须从现有项目发现。服务端在 server 目录执行 `dotnet test FantasyCard.Server.slnx` 以使用项目 SDK；Godot 用已存在的测试入口和目标平台。只用临时本地测试数据，不连接生产库。

用相同真实样本比较 JSON 与 PB：编码后字节数、编码/解码耗时、分配量、客户端主线程耗时、端到端 p50/p95/p99；压缩开关分别记录。报告机器、运行时、样本与次数，不编造提升比例。输出完成/失败/未执行命令、日志、缺陷、回滚步骤；未执行不算通过。

## 6. 完成门与回滚

按小批次提交：契约修复 -> 登录/大厅闭环 -> 剩余非实时模块 -> 实时/外围加固 -> 集成测试。服务端先具备显式双格式兼容，再灰度客户端；保留可回退的旧入口与版本范围。未达成契约、经济幂等、跨端互通与本地回归门禁前，禁止删除旧协议或声称全量完成。

主代理交付实际 agent IDs、文件清单、每组状态、构建/测试证据、模块覆盖、性能结果、遗留项。并行线程数不是完成证据。

## 7. 启动与官方参考

先在独立工作树打开此分支，再运行 `tools/start-protobuf-migration.ps1`，或在支持子代理的 Codex 桌面项目中发送：

> 读取 docs/network-protobuf-migration/PLAN.md，按第 4 节真实创建六个指定角色的子代理，按依赖分批开始实现，不止输出计划。遵守文件归属和审批，记录真实 agent IDs；无法启动的角色标明 blocked，不模拟子代理结果。不得部署或合并 release。

角色 TOML 仅定义分工，不会自行启动代理。当前配置来自 2026-09-28 核对的官方子代理文档；本机较旧版本可能不兼容，应以本机版本与可用工具为准，不能静默宣称运行成功。

- Protobuf overview: https://protobuf.dev/overview/
- Proto3 fields/compatibility: https://protobuf.dev/programming-guides/proto3/
- Wire encoding/packed fields: https://protobuf.dev/programming-guides/encoding/
- MIME types: https://protobuf.dev/reference/protobuf/mime-types/
- Godot HTTPRequest: https://docs.godotengine.org/en/stable/classes/class_httprequest.html
- OWASP WebSocket security: https://cheatsheetseries.owasp.org/cheatsheets/WebSocket_Security_Cheat_Sheet.html
- Codex subagents: https://developers.openai.com/codex/subagents
- Codex CLI: https://developers.openai.com/codex/cli/reference
