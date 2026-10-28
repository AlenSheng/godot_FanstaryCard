# Steam 昵称分配 2026-10-28

仅更新 release_steam；基线 93bcbebb。Steam SDK 读取 getPersonaName，客户端发送原始昵称及票据；服务端校验票据取得 SteamID 后，在首次创建账号时分配游戏昵称。账号识别仍只依赖校验后的 SteamID，客户端昵称不充当身份。

## 分配规则

例如 Steam 昵称 Unity，先尝试 Unity#1193。服务端使用密码学随机数生成 1000–9999，最多 10 次尝试（含首次）；每次由 INSERT ... ON CONFLICT(display_name_key) DO NOTHING 原子检查并占用名称。该 key 沿用现有 PostgreSQL NFKC／大小写归一化规则，覆盖所有玩家，不以单独查询结果冒充并发安全。

10 次仍冲突后改为 Unity#Unix毫秒时间戳；同毫秒／时钟回退采用单调递增后缀，再经同一个唯一索引检查。极端情况下时间戳占用仍存在时，最多再尝试 64 次，全部冲突则返回可重试的 409 并回滚，不强行写入重名。

现有昵称上限仍为 20 个 Unicode 字符；Steam 名前缀按后缀所需空间截短，后缀完整保留，不截断 emoji 的 UTF-16 代理对。控制字符移除、NFKC 归一化；空昵称被拒绝。已有 Steam 账号重登保留原昵称和 UserId，不因 Steam 改名或每次登录重新随机。

## 验证

19 项服务端检查通过，0 Failed／0 Skipped：固定 Unity#1193、Unicode／长度、时间戳、跨大小写／全角重名、10 次随机耗尽、时间戳碰撞、8 个同名 Steam 账号并发、同一身份并发重登、已有名字／本地账号安全及真实本机二进制 Steam HTTP 请求。

13 项原生无窗口检查通过；实际入口与 Store 方法验证 SDK persona Unity 原样提交，不再由 UI 选游戏随机名。原有票据清理、旧登录上下文、HTTPS 和本地认证禁止检查保留。验证使用受控 Steam SDK／上游替身，没有执行真实 Steam 账号登录，也没有启动容量局。数据库为自有新建本机临时集群，schema 清理且进程停机原件保留。

没有修改协议字段号、数据库结构、GDD／战斗规则、main／release／Google 分支或线上配置。真实 AppID／原生组件／云端启用状态仍按先前准备范围保留；云端部署新服务端后才会使用新分配规则。原始证据位于 G:/PR13Evidence/steam-naming-20261028-r1。
