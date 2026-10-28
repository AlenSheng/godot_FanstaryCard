> 2026-10-28 同步说明：当前分支已适配 release 的二进制 HTTP／WSS，Google 登录与注销请求使用 application/protobuf。旧 auth/ws-ticket、ws_ticket 名称兼容当前单次、会话绑定票据，按 30 秒有效期；原 SQL 迁移保留。先读 [分支合并验证报告](reports/release-branch-sync-20261028-r1/README.md)。本轮仅完成本机集成与多语言／分辨率验证，真实账号、插件、签名和商店发行仍按下文准备，不声明已执行。

# Google Play 发布执行顺序

本清单按 `GOOGLE_PLAY_RELEASE_REFERENCE.md` 的章节顺序组织。每项都必须有证据后才能勾选；仓库无法代替 Play Console、真实 Android 设备、签名服务和生产监控平台。

## P0：仓库侧已实现或已准备

- [x] Android Production 预设：AAB、包名、target SDK 36、arm64、签名必选。
- [x] 服务端 Google ID token 校验与内部 UserId 绑定接口。
- [x] 正式客户端隐藏本地登录和任意服务器入口；生产服务端禁止 managed local auth。
- [x] 隐私政策、服务条款、删除账号、支持、公开状态页面。
- [x] 账号删除请求、7 天冷静期、取消和后台完成删除。
- [ ] Web Client ID、Android OAuth Client ID、Google Play Games/Google Sign-In 原生插件和 SHA-256 指纹由发布环境配置。
- [ ] release keystore、Play App Signing、真实签名 AAB 和版本号由发布环境配置。
- [x] WebSocket 一次性短票据；生产环境拒绝 URL 中的长期访问令牌。
- [ ] 生产日志/指标/链路后端、告警和客户端 Crash/ANR SDK 仍需接入并完成实测。
- [ ] 加密异地备份、RPO/RTO、恢复演练和操作审计仍需在生产基础设施执行。

本地或临时环境可用 `powershell -ExecutionPolicy Bypass -File .\\server\\restore-drill.ps1 -DumpPath <dump>` 做一次可重复恢复演练；生产演练必须使用隔离数据库、记录耗时和结果，不能覆盖在线数据库。

## P1：外部验证

- [ ] Android 真机启动、登录、旋转/切后台/网络切换/进程被杀后的恢复。
- [ ] 不同屏幕比例、安全区、触控、权限和低内存场景。
- [ ] 内部测试上传、审核账号、商店截图/视频/内容分级/隐私链接。
- [ ] 12 名测试人员连续 14 天的封闭测试证据（如 Play Console 当前要求适用）。
- [ ] 并发、长连接、数据库连接池、限流和故障恢复压测。

## P2：真实货币商品（当前未启用）

- [ ] 明确是否销售真实货币商品；当前仓库只有游戏内金币。
- [ ] 如启用，接入 Google Play Billing、服务端 purchase token 验证、幂等、acknowledge/consume、退款/RTDN、对账和概率披露。

## 证据目录约定

将 AAB 校验、设备矩阵、崩溃/ANR、压测、备份恢复、Play Console 截图和审核账号记录放入不提交 Git 的发布证据目录。不要把密钥、OAuth 私密值、付款令牌或完整个人信息放入仓库。
