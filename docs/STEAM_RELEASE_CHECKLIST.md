# Relicbound Steam 发行清单

> 项目：Relicbound / 遗境行者
> 当前客户端：Godot 4.7，Windows x86_64  目标平台：Steam Windows 首发
> 用途：项目级 Steam 资源、配置、构建和发行验收清单。Steamworks 后台的账号、税务、定价和审核流程不在本文档中重复展开。

## 使用说明

- `[ ]` 未完成
- `[x]` 已确认或已具备
- `[!]` 当前阻塞发行
- `[?]` 需要根据最终产品范围决定

本文档只记录当前仓库和发行包需要准备的内容。Steamworks 后台的最终必填项以 Valve 当前页面为准。

## 1. 当前基线

- [x] Godot 客户端工程位于 `client/`
- [x] 主场景为 `client/main.tscn`
- [x] Windows Desktop 导出预设已存在
- [x] Windows 目标架构为 x86_64
- [x] 运行分辨率基线为 1920×1080
- [x] 最小窗口尺寸为 960×540
- [x] Windows 导出启用了 PCK 和目录加密
- [x] 正式导出使用自定义保护模板
- [x] 测试场景、证据、源文件和日志已配置为不进入正式导出包
- [x] 生产服务器地址已配置为 HTTPS：`https://www.relicbound.cn`
- [x] Steam 登录适配代码已经存在
- [x] 服务端 Steam 票据验证接口已经存在
- [x] 中文和英文 UI 文本已存在
- [x] 随包字体、音效和部分许可证文件已存在
- [x] 1920×1080 游戏画面证据已存在，可作为商店截图候选
- [!] `platform/steam/app_id` 当前仍为 `0`
- [!] `platform/steam/web_api_identity` 当前为空
- [!] 尚未发现 GodotSteam `.gdextension` 和 Windows 原生发行库
- [!] 尚未完成真实 Steam 客户端启动和登录验收
- [!] 当前候选包不能作为正式 Steam 发行包

## 2. Steam 平台配置——发行阻塞项

### 2.1 Steam AppID

- [ ] 在 Steamworks 创建正式产品
- [ ] 获取真实 AppID
- [ ] 将 `client/project.godot` 中的 `platform/steam/app_id=0` 替换为真实 AppID
- [ ] 确认客户端配置的 AppID 与服务端配置一致
- [ ] 确认测试 AppID 和正式 AppID 没有混用
- [ ] 为本地直启测试准备开发用 `steam_appid.txt`
- [ ] 确认开发用 `steam_appid.txt` 不被放入正式发行包，除非发行方案明确需要

配置位置：`client/project.godot` 的 `[platform]` 区域。

### 2.2 GodotSteam 原生组件

- [ ] 选定与 Godot 4.7 匹配的 GodotSteam 版本
- [ ] 添加 Steam `.gdextension` 文件
- [ ] 添加 Windows x86_64 Release 原生 DLL
- [ ] 添加插件依赖的其他 DLL
- [ ] 确认编辑器运行和正式导出都能加载 `Steam` singleton
- [ ] 确认插件提供以下接口：
  - [ ] `steamInitEx`
  - [ ] `getAuthTicketForWebApi`
  - [ ] `cancelAuthTicket`
  - [ ] `run_callbacks`
  - [ ] `getAppID`
  - [ ] `loggedOn`
  - [ ] `get_ticket_for_web_api` 回调
- [ ] 确认插件许可证可以随项目保存和发布
- [ ] 确认 Steam 原生库被包含在最终导出包中
- [ ] 确认插件不会被导出过滤器排除

### 2.3 Steam Web API 票据

- [ ] 创建正式 Web API Identity
- [ ] 将 Identity 写入客户端 `platform/steam/web_api_identity`
- [ ] 将相同 Identity 写入服务端 `Identity:Steam:Identity`
- [ ] 服务端启用 `Identity:Steam:Enabled=true`
- [ ] 服务端配置正确 AppID
- [ ] 服务端配置 Steam Publisher Key
- [ ] Publisher Key 只放在服务端 Secret Store
- [ ] Publisher Key 不进入客户端、Git、日志、截图或发行包
- [ ] 验证无效票据会被拒绝
- [ ] 验证 SteamID 由服务端验票结果决定
- [ ] 验证票据超时、取消和重复登录流程
- [ ] 验证 Steam 服务不可用时客户端有明确错误提示

服务端配置参考：`server/docs/CLIENT_INTEGRATION.md` 和 `server/docs/OPERATIONS_RUNBOOK.md`。

## 3. 正式客户端配置

### 3.1 项目设置

- [ ] 设置正式产品名称和显示名称
- [ ] 设置正式项目图标
- [ ] 设置 Windows EXE 图标
- [ ] 设置正式版本号
- [ ] 设置正式构建标识
- [ ] 确认 `run/main_scene` 指向正式主场景
- [ ] 确认发布构建不启用本地开发登录
- [ ] 确认发布构建不会显示服务器地址编辑入口，除非产品明确需要
- [ ] 确认发布构建不会显示测试按钮、调试面板或验证入口
- [ ] 确认发布构建只连接正式 HTTPS 服务
- [ ] 确认正式构建不包含测试服务器地址
- [ ] 确认正式构建不包含服务器密钥、Publisher Key 或管理密钥

当前相关配置：`client/project.godot`。

### 3.2 导出预设

- [x] Windows Desktop 预设存在
- [x] 架构为 x86_64
- [x] 使用 Release 自定义模板
- [x] PCK 加密已启用
- [x] 脚本以压缩二进制模式导出
- [x] 测试、证据和源文件已排除
- [ ] 补充 Steam 原生库后重新验证导出过滤器
- [ ] 将正式版本号更新到发行版本
- [ ] 确认输出文件名和 Steam 启动程序名称一致
- [ ] 确认正式包中只有必要的 EXE、PCK、DLL 和许可证文件
- [ ] 确认正式包中没有 `.pdb`、`.md`、`.py`、`.blend`、`.key`、日志和测试证据
- [ ] 确认加密 PCK 可以由正式自定义模板启动
- [ ] 确认普通 Godot 编辑器不能打开正式加密 PCK
- [ ] 确认正式包启动时没有脚本错误和资源加载错误

导出配置：`client/export_presets.cfg`。
导出检查脚本：`client/platform/export_windows.py`。

### 3.3 Windows 签名

- [ ] 准备 Windows Authenticode 代码签名证书
- [ ] 配置签名工具和时间戳服务
- [ ] 签名 EXE
- [ ] 签名 Steam 原生 DLL
- [ ] 验证签名证书有效且未过期
- [ ] 验证 Windows SmartScreen 提示情况
- [ ] 确认签名私钥不进入仓库和发行包

当前状态：`codesign/enable=false`。签名不是 Steam 上传的绝对硬性要求，但正式发行建议完成。

## 4. 游戏运行资源

### 4.1 核心资源

- [x] 中文字体
- [x] 英文字体
- [x] UI 音效
- [x] 战斗音效
- [x] 环境音
- [x] BGM 文件
- [x] 卡牌插画
- [x] 怪物和角色资源
- [x] UI 图标和面板资源
- [x] 本地化文本
- [ ] 对所有运行时资源做一次正式包缺失检查
- [ ] 对所有资源路径做大小写检查
- [ ] 确认 Windows 干净环境可以加载全部资源
- [ ] 确认加密导出后字体、音频、纹理仍能正常加载

### 4.2 音频和视频授权

- [x] 字体许可证已保存
- [x] 部分音频许可证已保存
- [ ] 为 `art/BGM/` 中的外部音乐保存商业使用授权
- [ ] 确认 BGM 授权覆盖 Steam 全球发行
- [ ] 确认授权允许剪辑、循环、压缩和重新编码
- [ ] 确认登录视频或宣传视频中的音乐、素材和字体均有授权
- [ ] 为每个外部资源建立来源、作者、许可证和授权范围记录
- [ ] 将最终许可证文件复制到发行包 `licenses/` 目录

## 5. Steam 商店资源

当前仓库未发现完整的 Steam 专用素材包，需要单独制作并归档。

### 5.1 Logo 和胶囊图

- [ ] 游戏主 Logo 透明 PNG
- [ ] 游戏 Logo 矢量源文件
- [ ] Header Capsule
- [ ] Small Capsule
- [ ] Main Capsule
- [ ] Vertical Capsule
- [ ] Steam Library Capsule
- [ ] Steam Library Hero
- [ ] Steam Library Logo
- [ ] Steam Shortcut Icon
- [ ] Steam App Icon
- [ ] 所有图片包含清晰可读的游戏名称或 Logo
- [ ] 普通胶囊图不放评测分数、媒体奖项或虚假宣传语
- [ ] 图片内容与正式版实际内容一致

### 5.2 Gameplay 截图

- [ ] 至少 5 张正式截图
- [ ] 推荐分辨率 1920×1080 或更高
- [ ] 截图只展示真实游戏画面
- [ ] 展示大厅、卡组、装备、探索、战斗、奖励等主要内容
- [ ] 不使用纯概念图作为主要截图
- [ ] 不在截图中加入媒体评分、奖项或大段营销文案
- [ ] 删除明显的测试账号、服务器地址和调试信息
- [ ] 从 `client/evidence/` 和 `outputs/` 中筛选最终版本，不直接提交全部验证截图

### 5.3 宣传片

- [ ] 制作至少一支 Gameplay 宣传片
- [ ] 前 5–10 秒展示核心玩法
- [ ] 无声音时也能理解主要玩法
- [ ] 包含卡牌、探索、战斗、撤离或 PvP 等核心卖点
- [ ] 删除测试 UI、调试文字和开发中内容
- [ ] 准备 16:9、1920×1080、MP4/H.264/AAC 版本
- [ ] 准备宣传片缩略图
- [ ] 如支持多语言，准备字幕或多语言宣传片

## 6. 游戏内平台功能

以下功能不是基本上架的全部必需项，但商店页面宣传了就必须实际可用。

### 6.1 输入和手柄

- [ ] 明确商店页是否声明手柄支持
- [ ] 如果声明支持，完成 Xbox 手柄测试
- [ ] 如果声明支持，完成 PlayStation 手柄测试
- [ ] 配置 Steam Input 默认布局
- [ ] 所有主要功能都能通过手柄操作
- [ ] 输入提示图标与实际控制器一致
- [ ] 文本输入时支持 Steam/系统屏幕键盘，如目标包含 Steam Deck

### 6.2 云存档

- [?] 判断游戏进度是否完全由服务端保存
- [?] 如果存在本地存档，配置 Steam Cloud
- [ ] 确认音量和本地设置是否需要同步
- [ ] 测试新电脑下载后存档恢复
- [ ] 测试云存档冲突处理

### 6.3 成就和统计

- [?] 确定是否首发支持 Steam Achievements
- [ ] 成就 ID
- [ ] 成就中英文名称
- [ ] 成就中英文描述
- [ ] 成就图标
- [ ] 隐藏成就标记
- [ ] 解锁条件和重复解锁保护
- [ ] Steam 后台统计配置

### 6.4 其他功能

- [?] Steam Overlay
- [?] 排行榜
- [?] Steam 创意工坊
- [?] DLC
- [?] Demo
- [?] Remote Play
- [?] Trading Cards
- [?] 反作弊
- [?] Steam Deck 兼容性

## 7. 运行和安装验收

- [ ] 从 Steam 客户端安装
- [ ] 从 Steam 客户端启动
- [ ] 第一次启动成功
- [ ] 退出后再次启动成功
- [ ] 不安装 Godot 也能运行
- [ ] 不安装开发环境也能运行
- [ ] 无管理员权限可以运行
- [ ] Windows 10/11 目标环境测试
- [ ] 1920×1080 测试
- [ ] 1280×720 测试
- [ ] 窗口模式测试
- [ ] 无边框模式测试
- [ ] 全屏模式测试
- [ ] 多显示器测试
- [ ] 高 DPI 测试
- [ ] 键盘鼠标测试
- [ ] Steam Overlay 测试
- [ ] 断网启动行为符合产品设计
- [ ] 断线重连和会话恢复测试
- [ ] 新账号首次登录测试
- [ ] 老账号重复登录测试
- [ ] Steam 账号切换测试
- [ ] 存档、设置和退出流程测试
- [ ] 更新旧构建到新构建
- [ ] 卸载后重新安装
- [ ] 正式服务器不可用时显示明确提示
- [ ] 日志中不输出票据、密钥和敏感信息

## 8. 正式服务器依赖

- [ ] `https://www.relicbound.cn` 使用有效 TLS 证书
- [ ] Steam 验票接口可从生产服务器访问
- [ ] 服务端 Steam Publisher Key 使用 Secret Store
- [ ] 服务端生产数据库可用
- [ ] 登录、匹配、战斗、结算和重连均使用生产配置
- [ ] 生产环境关闭本地开发登录
- [ ] 生产环境关闭测试账号和测试接口
- [ ] 生产环境启用错误监控
- [ ] 生产环境启用健康检查
- [ ] 生产环境准备数据库备份和回滚方案
- [ ] 生产环境准备客户端版本兼容策略
- [ ] 服务器更新不会破坏已经发行的客户端
- [ ] Steam 登录失败、验票失败、服务器异常都有可读提示

## 9. 项目文档和版本一致性

- [ ] 更新 `GDD.md` 中过时的 Unity/C# 技术栈描述
- [ ] 统一项目技术栈为 Godot 4.7/GDScript
- [ ] 更新客户端发行说明
- [ ] 更新服务器部署说明
- [ ] 记录正式构建版本号
- [ ] 记录 AppID 和 Depot 对应关系
- [ ] 记录插件版本和原生库 SHA-256
- [ ] 记录正式导出命令
- [ ] 记录正式包文件清单
- [ ] 记录第三方资源许可证
- [ ] 记录已知问题和首发限制
- [ ] 记录紧急回滚和热修复方式

## 10. 发布包最终验收

- [ ] 使用真实 AppID 导出
- [ ] 使用正式 GodotSteam 插件导出
- [ ] 使用正式 HTTPS 服务导出
- [ ] 使用正式服务器 Steam 验票配置
- [ ] Steam 客户端启动成功
- [ ] Steam 登录成功
- [ ] 服务端验票成功
- [ ] 可以进入大厅
- [ ] 可以完成一次匹配
- [ ] 可以完成一次战斗
- [ ] 可以完成一次结算
- [ ] 断线后可以恢复或安全退出
- [ ] 正式包不包含调试文件
- [ ] 正式包不包含密钥
- [ ] 正式包不包含测试证据
- [ ] 正式包不包含未授权资源
- [ ] 正式包中包含必要许可证
- [ ] EXE 和 DLL 已签名或已确认签名策略
- [ ] 商店截图与正式版本一致
- [ ] 宣传片与正式版本一致
- [ ] 版本号、构建号和公告一致
- [ ] 生成最终 SHA-256 清单
- [ ] 归档最终发行包和验收报告

## 当前最优先处理顺序

1. [ ] 获取真实 Steam AppID
2. [ ] 接入兼容 Godot 4.7 的 GodotSteam 发行组件
3. [ ] 配置 Web API Identity
4. [ ] 配置服务端 Steam Publisher Key 和生产验票
5. [ ] 完成 Steam 客户端启动、登录和服务器验票联调
6. [ ] 补齐正式项目图标和 EXE 图标
7. [ ] 制作 Steam 商店胶囊图、截图和宣传片
8. [ ] 完成音乐、视频、插件和模型授权归档
9. [ ] 完成 Windows 签名和干净环境安装测试
10. [ ] 生成可提交 Steam 的最终 Windows 包

## 相关文件

- [客户端项目配置](../client/project.godot)
- [Windows 导出预设](../client/export_presets.cfg)
- [Steam 平台接入说明](../client/platform/README.md)
- [Steam 平台适配代码](../client/platform/platform_service.gd)
- [Windows 导出预检脚本](../client/platform/export_windows.py)
- [客户端说明](../client/README.md)
- [Steam 登录服务端接口说明](../server/docs/CLIENT_INTEGRATION.md)
- [服务端部署说明](../server/docs/OPERATIONS_RUNBOOK.md)
- [发布保护说明](RELEASE_PROTECTION.md)
- [字体和音频接入记录](FONT_AUDIO_INTEGRATION_20260910.md)
