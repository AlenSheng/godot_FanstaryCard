# 外围 JSON 与非游戏消息例外（2026-09-28）

以下逐项例外不经过游戏 Protobuf 内容协商，不能按 `/api/*` 通配迁移。第一方游戏端点仍以 `protocol/http/v1/endpoints.json` 的实际注册表为准。

| 方法 | 路径 | 格式/边界 |
| --- | --- | --- |
| GET | `/api/v1/client-info` | 公告、登录前能力、配置版本，JSON；公开读取 |
| GET Upgrade | `/ws/v1/client-info` | 公告更新，只读 WebSocket **文本 JSON**；不是游戏 session 通道 |
| GET | `/admin` | 管理页 HTML，仅独立管理入口 |
| GET | `/api/admin/players` | JSON；管理员密钥、HTTPS、限流 |
| GET | `/api/admin/players/{playerId:guid}/equipment` | JSON；同上 |
| POST | `/api/admin/mail` | JSON；同上，既有审计与数据库事务 |
| POST | `/api/admin/message` | JSON；同上 |
| POST | `/api/admin/revoke` | JSON；同上 |
| POST | `/api/admin/ban` | JSON；同上 |
| POST | `/api/admin/unban` | JSON；同上 |
| POST | `/api/admin/players/unlock-all-cards` | JSON；同上 |
| POST | `/api/admin/players/max-all-cards` | JSON；同上 |
| POST | `/api/admin/players/grant-all-equipment` | JSON；同上 |
| POST | `/api/admin/players/max-existing-equipment` | JSON；同上 |
| GET | `/api/admin/client-settings` | JSON；同上 |
| PUT | `/api/admin/client-settings` | JSON；公告发布/管理设置，既有版本冲突检查 |
| GET | `/health/live` | 框架健康检查文本，非玩法消息 |
| GET | `/health/ready` | 框架健康检查文本，非玩法消息 |
| GET/HEAD | 官网根路径与静态资源 | HTML/图片/脚本等原生文件格式，Caddy 提供 |

外部 Steam 验票遵守第三方协议；客户端向本服务提交 Steam 登录请求仍属于游戏 Protobuf。资源/配置包下载按文件格式，不塞入实时消息。应用根 GET `/` 当前返回 404，公网 `/` 由 Caddy 静态官网提供。

公共域名阻断 `/admin`、`/admin/*`、`/api/admin`、`/api/admin/*`。独立管理域名端口只代理上述管理路径，其他路径 404；原 IP 入口统一 404。生产 HTTPS/WSS、证书、云 IP 白名单要求不变。
