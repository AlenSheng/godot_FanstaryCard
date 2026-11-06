# Steam 分支接入准备

2026-10-28，`release_steam` 从 `main@1fd466a9e6b61171a422863ee6e9cc97ff4fbe4b` 创建，包含已验收的 release 基线。Steam 界面政策独立于 Google 分支。

## 当前行为

登录页保留标题、背景、公告、设置、版本信息和一个“进入／Enter”按钮。没有账号输入、随机名按钮、本地登录、Google 登录或登录方式选择。客户端本地认证开关为 false。

点击进入后从 Steam SDK 取得 Web API 票据，再向 `https://www.relicbound.cn/api/v1/auth/steam` 提交 Protobuf 请求。客户端读取 Steam persona，首次注册由服务端分配“Steam名#四位随机数”；最多 10 次随机尝试，冲突耗尽后使用 Unix 毫秒时间戳。名称在数据库唯一索引处原子占用；长 Steam 名按现有 20 字符上限截短前缀，后缀保留。昵称不决定 Steam 账号，账号仍由服务器校验后的 SteamID 映射；已有角色不会被本次昵称覆盖。详见 [昵称分配验证](reports/steam-naming-20261028-r1/README.md)。

客户端等待 `get_ticket_for_web_api` 回调，不把 SDK 返回的句柄当作票据；只发送有效范围内的票据字节的十六进制表示。失败回调、HTTP 登录结束、超时及被替换的登录上下文会取消票据。会话仍通过原有服务端鉴权、内存 token 和单次 WebSocket 票据链路建立，不回退到本地认证。

接口与票据语义依据 [Steam GetAuthTicketForWebApi](https://partner.steamgames.com/doc/api/ISteamUser#GetAuthTicketForWebApi) 和 [AuthenticateUserTicket](https://partner.steamgames.com/doc/webapi/ISteamUserAuth#AuthenticateUserTicket)。PublisherKey 仅用于可信服务器调用 Valve，不进入客户端、聊天、URL 日志或 Git。

## 配置准备

用户选择“先做准备”，所以 AppID 保留 0，Web API identity 保留未配置；没有使用测试 AppID 作为正式游戏身份，也没有启用占位票据。当前公开云端检查只返回 `identity.local`，尚未公布 `identity.steam`。本轮没有修改或重启云服务。

实际联调前需要：

1. 安装适配当前 Godot 4.7.2 的 GodotSteam 原生组件，检查 `Steam` singleton 的初始化、Web API 票据回调、取消及 callback pump 接口。
2. 在客户端 `platform/steam/app_id` 填写真实 AppID，`platform/steam/web_api_identity` 填写约定的服务标识，`platform/server_url` 保持目标 HTTPS 云服务。
3. 从 `server/.env.steam.example` 私下复制为 `server/.env.steam`；填写真实 AppID、相同 identity 和 PublisherKey。此私有文件已忽略，不提交。
4. 云端发布时在原有基础配置上显式叠加 `server/compose.steam.yaml`。保留基础私有环境，再加载 Steam 私有环境；先执行 Compose config 校验。该覆盖文件默认 `STEAM_AUTH_ENABLED=false`，没有自动部署或修改基础数据库／管理密钥。
5. 在自有发布流程中启用真实 Steam 认证，确认 client-info 包含 `identity.steam` 后，从 Steam 游戏库验证新账号、重登、失效票据、退出与重连。密钥和完整票据不进入普通日志。

现有加密模板、Windows Steam 导出和包体保护继续使用 [平台与导出说明](../client/platform/README.md)，准备状态不代表已经生成签名包或获 Steam 审核通过。验收范围和原件见 [本轮报告](reports/steam-preparation-20261028-r1/README.md)。
