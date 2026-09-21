# Relicbound Google Play 发布参考文档

> 项目：Relicbound（遗境行者）  
> 工程：Godot Android 客户端 + ASP.NET Core/.NET 10 服务端 + PostgreSQL  ；  
> 文档基线：2026-09-21（Google Play 政策和技术要求可能变化，提交前应再次核对官方页面）

## 1. 发布结论

当前项目的服务端、数据库和在线运行时骨架已经比较完整，但还不能直接提交 Google Play Production。

主要阻塞项：

1. Android 当前导出为未签名 APK，不是正式 AAB。
2. 当前登录主要是本地开发登录和 Steam 登录，缺少 Android 正式身份方案。
3. 尚未形成完整的隐私政策、Data Safety、账号删除和网页删除入口。
4. 如果销售虚拟商品，还需要 Google Play Billing 和服务端订单校验。
5. 需要完成 Android 真机、崩溃/ANR、备份恢复、负载和封闭测试证据。

## 2. 目标架构

```text
Godot Android Client
        |
        | HTTPS REST / WSS
        v
Caddy / TLS / WAF / Rate Limit
        |
        v
ASP.NET Core Game Server
        |---- Google / Android Login
        |---- Google Play Billing Verification
        |---- Play Integrity Verification
        |---- Admin API
        |
        v
PostgreSQL Authority Database
        |
        +---- Encrypted Backup / PITR
        +---- Logs / Metrics / Traces / Alerts

Public Website: Privacy Policy / Terms / Account Deletion / Support
```

客户端只负责显示和发送操作请求；金币、库存、战斗、掉落、购买发货和结算必须由服务端决定。

## 3. 当前项目盘点

### 已有基础

- ASP.NET Core/.NET 10 模块化单体。
- PostgreSQL 权威存储、版本化迁移、checksum 和迁移锁。
- REST + WebSocket，包含重连、sequence、resume、房间快照和结算恢复。
- JSON 结构化日志、请求追踪 ID、OpenTelemetry traces/metrics 接口。
- 登录、市场、经济写入和 WebSocket 命令限流。
- 生产环境关闭本地认证的设计。
- Docker 容器限制、HTTPS 反向代理、数据库备份和发布 Runbook。

参考文件：

- [server/README.md](../server/README.md)
- [server/docs/SECURITY_HARDENING.md](../server/docs/SECURITY_HARDENING.md)
- [server/docs/OPERATIONS_RUNBOOK.md](../server/docs/OPERATIONS_RUNBOOK.md)
- [server/compose.cloud.yaml](../server/compose.cloud.yaml)
- [server/Caddyfile](../server/Caddyfile)

### 当前明确缺口

Android 导出配置当前包含：

- 输出路径为 `Relicbound.apk`；
- `gradle_build/use_gradle_build=false`；
- `package/signed=false`；
- 没有在导出预设中明确配置 target API；
- 仅启用 `arm64-v8a`。

参考：[client/export_presets.cfg](../client/export_presets.cfg)。

当前 WebSocket 连接把 access token 放在 URL 查询参数中：

```text
/ws/v1/session?access_token=...
```

建议改为一次性短时 WebSocket ticket，避免长期凭证进入代理或访问日志。

## 4. Google Play 必备发布条件

### 4.1 Android 构建和签名

- 使用 Android Release 模板和 Gradle 构建。
- 上传 `.aab`，不要把 APK 作为唯一生产包。
- 使用稳定包名，例如 `com.relicbound.game`；发布后不要随意更改。
- 配置 upload key，并启用 Google Play App Signing。
- 每次发布递增 `versionCode`，同步维护 `versionName`。
- 生产包中不能包含调试接口、本地伪造登录、服务器密钥、Steam Publisher Key 或管理密钥。
- 以 arm64 为主，同时根据目标设备决定是否保留其他 ABI。
- 控制包体积，检查纹理、音频和视频资源。

截至本文件基线日期，新的应用和应用更新需要 target Android 16 / API 36 或更高；不应依赖延期提交。

官方资料：

- [Target API level requirements](https://support.google.com/googleplay/android-developer/answer/11926878?hl=en)
- [Android App Bundle](https://developer.android.com/guide/app-bundle)
- [Play App Signing FAQ](https://developer.android.com/guide/app-bundle/faq)

### 4.2 Play Console 资料

- 开发者账号身份、邮箱和电话验证。
- 应用名称、图标、短描述、完整描述。
- 截图、宣传图和可选视频。
- IARC 内容分级。
- 目标年龄段和内容声明。
- 是否包含广告的声明。
- Data Safety 数据安全表。
- 隐私政策 URL。
- 审核员登录账号和完整操作说明。
- 支持邮箱、网站和客服入口。
- 发行国家/地区和设备兼容范围。

如果是 2023-11-13 以后创建的个人开发者账号，生产发布前通常需要至少 12 名测试者连续参加封闭测试 14 天，然后申请 Production access。

官方资料：

- [Prepare your app for review](https://support.google.com/googleplay/android-developer/answer/9859455?hl=en)
- [App testing requirements for new personal developer accounts](https://support.google.com/googleplay/android-developer/answer/14151465?hl=en)
- [Contact information requirements](https://support.google.com/googleplay/android-developer/answer/10840893?hl=en)

## 5. Android 客户端待办

### P0：必须完成

- 新建 Android Production 导出预设。
- 改为 AAB、Release、签名和 target API 36。
- 生产环境禁止本地登录和服务器地址自由输入。
- 接入 Android 正式登录：Google Play Games Services、Google Sign-In，或游客账号升级方案。
- 支持账号与 Steam 身份绑定到同一个内部 `UserId`。
- 支持 Android 返回键、应用切后台、进程被杀、网络切换和 WebSocket 恢复。
- 检查 16:9、20:9、平板、刘海/圆角安全区和横屏触控热区。
- 增加启动失败、登录失败、维护中、版本过期和服务器不可用界面。
- 接入 Android 崩溃和 ANR 收集。

### P1：强烈建议

- 接入 Play Integrity，在登录、匹配、购买和高价值经济操作上做风险分级。
- 保存 refresh token 时使用 Android Keystore；不把长期 token 写入普通配置文件。
- 使用短时 WebSocket ticket，避免把 access token 放入 URL。
- 通过远程配置控制维护、最低客户端版本和灰度比例。
- 支持从 Play Store 打开的应用版本检查和更新提示。

Play Integrity 的 token 应发送到服务端验证，不能在客户端保存解密密钥或自行信任结果。

官方资料：[Play Integrity API](https://developer.android.com/google/play/integrity/overview)

## 6. 登录、账号和隐私

### 6.1 账号模型

推荐保持现有内部身份隔离：

```text
Internal UserId
  ├── Google / Play Games identity
  ├── Steam identity
  ├── device identity
  └── future platform identities
```

外部平台 ID 不能直接作为业务表主键。

### 6.2 必须提供的隐私内容

隐私政策应说明：

- 收集哪些账号、设备、网络、日志和游戏数据。
- 收集目的和处理依据。
- 是否与 Google、Steam、崩溃分析、云服务商共享。
- 数据存储地区和保留时间。
- 未成年人和年龄段处理方式。
- 用户访问、更正、注销和删除方式。
- 客服联系方式和安全事件联系方式。

### 6.3 账号删除

如果游戏允许创建账号，必须同时提供：

- 游戏内“删除账号”入口；
- 网站上的账号删除申请页面；
- 删除状态和冷静期提示；
- 删除完成通知；
- 备份、账本和法定留存数据的处理说明。

官方资料：[Google Play account deletion requirements](https://support.google.com/googleplay/android-developer/answer/13327111?hl=en)

## 7. 后端待办

### 7.1 生产安全

- 所有客户端请求只走 HTTPS/WSS。
- 数据库不暴露公网端口。
- 管理端口限制管理员 IP，并要求独立管理员密钥。
- 密钥通过 Secret Store 或环境变量注入，不进入仓库、镜像和日志。
- 生产关闭 local auth。
- 依赖、容器镜像和基础镜像定期扫描。
- 管理接口使用角色权限、二次确认和审计日志。
- 对登录、匹配、经济、购买和 WebSocket 命令分别限流。
- 对请求体、WebSocket 消息、名称和昵称长度设置上限。

### 7.2 服务可靠性

- API 版本化，保留客户端兼容窗口。
- 所有资产变更使用幂等键和唯一业务流水号。
- 结算、购买发货和退款可重试但不能重复发放。
- WebSocket 支持断线恢复和快照补偿。
- 房间恢复、结算恢复和数据库恢复纳入 readiness。
- 发布采用 drain、canary、逐步放量和可回滚镜像。
- 数据库迁移只允许向前兼容；不直接回滚已经执行的 schema migration。

## 8. 数据库和备份

PostgreSQL 可以继续作为生产主库，但上线前必须明确：

- Staging 和 Production 使用不同数据库、账号和密钥。
- 连接池上限、超时和慢查询阈值。
- 余额、库存、订单、结算和经济流水的唯一约束。
- Google purchase token 的唯一性和重复提交处理。
- 玩家删除和匿名化的级联规则。
- 加密备份、异地存储和访问权限。
- RPO：最多允许丢失多少时间的数据。
- RTO：故障后需要多久恢复服务。
- 至少每月一次隔离环境恢复演练。
- 恢复后验证玩家资产、Running 房间、Pending settlement、市场挂单和经济流水。

备份不应提交到 Git；备份文件和校验文件应与镜像 digest、迁移版本和 configVersion 关联保存。

## 9. 支付和商业化

### 9.1 不销售真钱商品

如果首发只使用游戏内赚取的金币，不销售真钱购买的虚拟商品，可以暂时不接 Google Play Billing，但仍需完成隐私、账号删除和数据安全声明。

### 9.2 销售真钱数字商品

以下内容一般需要 Google Play Billing：

- 虚拟货币。
- 卡包、角色、装备、额外关卡。
- 付费背包或功能解锁。
- 去广告和订阅服务。

服务端需要：

1. 配置 Play Product ID。
2. 客户端发起购买。
3. 将 purchase token 发送到后端。
4. 后端调用 Google 接口验证订单。
5. 通过唯一流水号幂等发货。
6. 处理 acknowledge、consume、退款、撤销和订阅续费。
7. 接收 Real-time Developer Notifications。
8. 定期对账订单、玩家资产和经济账本。

如果付费随机礼包包含随机虚拟物品，购买前必须清晰展示概率。

官方资料：

- [Google Play Payments policy](https://support.google.com/googleplay/android-developer/answer/10281818?hl=en)
- [Payments policy details](https://support.google.com/googleplay/android-developer/answer/9858738?hl=en)
- [Google Play Billing](https://developer.android.com/google/play/billing)

## 10. 日志、监控和告警

### 服务端日志

建议使用结构化 JSON，并至少包含：

- timestamp
- environment
- service/version
- traceId
- requestId
- userId（必要时脱敏或哈希）
- operation
- outcome
- errorCode
- durationMs

不得记录：

- Access Token、Refresh Token。
- Steam Publisher Key。
- Google 服务账号密钥。
- 完整支付 Token。
- 不必要的完整 IP、邮箱和设备号。

### 必须建立的监控

- 客户端崩溃率和 ANR。
- 登录成功率、失败原因和过期 Token。
- REST P95/P99 延迟和 5xx。
- WebSocket 连接数、断线率和恢复失败。
- 匹配等待时间、房间数量和房间异常关闭。
- RoomActor 队列长度和 tick 延迟。
- 结算失败、Pending hold、重复提交和资产对账异常。
- 购买、退款、撤销和发货差异。
- PostgreSQL 连接池、慢查询、锁等待和磁盘空间。
- CPU、内存、容器重启和证书过期。
- 备份年龄和最近恢复演练结果。

当前项目已经有结构化日志和 OpenTelemetry 接口，但还需要连接实际的日志平台、指标平台、Trace 后端和告警规则。

## 11. 网站和管理前端

不需要额外做 Web 游戏客户端，但至少需要公开网站页面：

- `/privacy`
- `/terms`
- `/delete-account`
- `/support`
- `/status` 或维护公告

现有 `server/site` 和 Caddy 可以承载这些页面。

建议增加内部管理后台，用于：

- 玩家查询。
- 封禁和解封。
- 结算失败处理。
- 订单和退款对账。
- 配置版本管理。
- 服务器健康状态。
- 审计日志查询。

后台修改必须经过带权限和审计的 API，不能让管理员直接改生产数据库。

## 12. 发布前测试矩阵

### 客户端

- API 35 和 API 36 真机。
- 低端 Android 设备。
- 不同屏幕比例和平板。
- 首次启动、升级安装和卸载重装。
- 冷启动、后台恢复和进程被杀。
- 弱网、断网、切换 Wi-Fi/移动网络。
- WebSocket 断开、恢复和重复操作。
- 登录过期、踢下线和账号切换。
- 触摸、返回键、系统弹窗和权限行为。
- 崩溃、ANR、内存和包体积。

### 服务端

- 生产配置禁止 local auth。
- 迁移、重复启动和 checksum 校验。
- 并发登录和账号绑定。
- 并发购买、重复支付和退款。
- 重复结算和断点恢复。
- 房间恢复和进程重启。
- 限流、超大消息和异常输入。
- 数据库备份恢复。
- 负载测试和故障演练。

### 支付（如果启用）

- 测试商品购买。
- 购买中断和重复回调。
- 消费型商品重复消费。
- 退款、撤销和订阅过期。
- Google Play 服务不可用。
- 后端不可用后重试发货。
- 订单与库存、经济账本对账。

## 13. 推荐实施顺序

### P0：不完成不能提交

1. Android AAB、Release 签名、Play App Signing、target API 36。
2. Android 正式登录和内部 UserId 绑定。
3. 生产禁用 local auth，移除测试服务器入口。
4. 隐私政策、服务条款、Data Safety、账号删除入口。
5. WebSocket access token 改为短时 ticket 或安全 Header。
6. 崩溃/ANR、日志平台、指标、Trace 和告警。
7. 生产数据库备份和真实恢复演练。

### P1：首发前完成

1. 真机和低端设备兼容性测试。
2. 封闭测试 12 人 × 连续 14 天（适用于相关个人开发者账号）。
3. 负载测试、断线恢复和进程重启演练。
4. Google Play 审核账号和操作说明。
5. 发布截图、视频、内容分级和目标年龄声明。

### P2：有商业化时完成

1. Google Play Billing。
2. 订单后端验证和幂等发货。
3. 退款、撤销和实时通知。
4. 购买商品概率展示和商业化合规审核。
5. 订单、资产和经济账本自动对账。

## 14. 最终提交检查表

- [ ] Play Console 开发者身份已验证。
- [ ] 包名已确定且与签名配置一致。
- [ ] AAB 上传成功。
- [ ] Release 签名和 Play App Signing 已配置。
- [ ] `versionCode` 正确递增。
- [ ] target API 36 或更高。
- [ ] 生产包没有 local auth、测试地址和秘密。
- [ ] Android 登录可用。
- [ ] 隐私政策 URL 可公开访问。
- [ ] 游戏内账号删除可用。
- [ ] 网页账号删除入口可用。
- [ ] Data Safety 表单与实际代码一致。
- [ ] 内容分级、目标年龄和广告声明完成。
- [ ] 审核账号和测试步骤有效。
- [ ] 崩溃、ANR 和服务器告警可用。
- [ ] 数据库备份已验证可恢复。
- [ ] 如果收费，Billing、订单校验和退款处理已通过测试。
- [ ] 封闭测试要求已完成。
- [ ] 生产发布、回滚和事故 Runbook 已演练。

## 15. 官方参考链接

- [Target API level requirements](https://support.google.com/googleplay/android-developer/answer/11926878?hl=en)
- [Prepare your app for review](https://support.google.com/googleplay/android-developer/answer/9859455?hl=en)
- [Personal developer account testing requirements](https://support.google.com/googleplay/android-developer/answer/14151465?hl=en)
- [Account deletion requirements](https://support.google.com/googleplay/android-developer/answer/13327111?hl=en)
- [Payments policy](https://support.google.com/googleplay/android-developer/answer/10281818?hl=en)
- [Android App Bundle](https://developer.android.com/guide/app-bundle)
- [Play App Signing](https://developer.android.com/guide/app-bundle/faq)
- [Play Integrity API](https://developer.android.com/google/play/integrity/overview)
- [Google Play Billing](https://developer.android.com/google/play/billing)

