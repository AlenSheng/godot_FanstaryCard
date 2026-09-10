# 补图接入与验证（2026-09-09）

> 本文为 P1 历史记录，文中的剩余补图项已在后续 P2 接入。当前状态以 2026-09-10 [美术及配套资源清单](UI_MISSING_ASSETS.md) 为准；[P2 接入报告](UI_P2_INTEGRATION_20260909.md) 保留后续批次证据。本文的原生补边结论不代替当前卡框复核。

本轮把直接放入 `client/assets/imported/UI` 的 12 张新 PNG 接入 Godot。当前 400 张图片全部登记，200 张图鉴卡和 12 张本局怪物卡均有插画，12 个物种使用与卡面一致的主体图。

## 实现

- 导入器支持当前原地资源目录及单独指定源目录，保留图片原件、历史来源哈希与九宫格边距；资源不完整时不会覆盖现有清单。
- 新怪物暗红框接入统一卡牌控件，文字、选中状态和卡牌效果由 Godot 绘制。源图被抠除的顶边由原生暗红边框补齐，选中卡底文字提亮。
- 土元素使用新岩石图标，双火蝠/双浊螅按实例别名复用同物种图片；怪物击败后隐藏过时意图，行动前摇按服务器剩余毫秒显示。
- `RoomMonster.boss_phase` 使用 Protobuf 新增字段 11，经服务器快照、编码/解码和 Godot schema 到达界面。湮核二阶段只在服务器已完成转阶段时切图，旧消息缺字段时使用一阶段。战斗规则保持原实现。
- 浊螅、锈刃鼠界面名称与 GDD 对齐。匣灵已有卡牌/图片映射，当前遭遇工厂未生成该物种；冰霜幽灵仍未绑定未定义的物种 ID。
- 已重建本地 Docker 服务，现有 PostgreSQL 数据卷继续使用；就绪检查返回 `Healthy`。

## 验证证据

- 导入器 4 项回归测试通过，覆盖原地重复执行、来源记录保留、外部图片规范化和不完整输入拒绝。
- Godot 6 项测试通过，覆盖全部卡图与物种、实例别名、阶段回退、五系图标、Protobuf 字段、界面编译和既有交互状态。
- 服务端路由/Protobuf 27 项测试通过，包含同样半血下等待转阶段与完成转阶段、两阶段编解码以及旧消息兼容。
- 最终原生预览生成 44 张截图，1920×1080 与 1280×720 均无自动布局检测错误。人工重点检查 12 个物种与怪物卡、土图标、两阶段 Boss、卡框及选中状态。
- 最新联网测试 18 项通过，实际完成 6 次连放、一次领奖、断线恢复和撤离结算回城，约 107 秒。此次自然遭遇为砂蜥；Boss 转阶段由服务端状态测试及原生预览验证。
- 联网录制 97 帧，以 2 fps 编成 `client/evidence/live/gameplay.mp4`；抽样帧见 `outputs/current_live_review.jpg`。本次录像为真实原生视口。

报告位置：`client/evidence/art/report.json`、`client/evidence/live/report.json`、`outputs/current_asset_audit.json`。新截图与本轮录像均已刷新；旧截图目录可能仍保留历史图片，应以本轮报告计数为准。

## 剩余内容

完整补图文件名、尺寸、透明要求和中文提示词见 [UI_MISSING_ASSETS.md](UI_MISSING_ASSETS.md)，机器清单见 [ui_missing_assets.json](ui_missing_assets.json)。

- 7 张新图：3 个职业本命徽记、4 个商城商品插画。
- 6 项透明修复：火蝠、锈刃鼠、石甲卫，以及遗物堆、泉水、撤离门图标；三只旧怪物原图尚未被替换，背景问题在实景中仍可见。
- 2 项可选角色外观统一，另有冰霜幽灵身份待确认；现有两张 Blender 场景不缺。
- 遗物完整详情、按元素伤害段/连放预览、PVP 对手详情、市场装备详情仍有接口缺口，详见素材清单末尾。这些内容不能靠补图解决。
- 本次联网测试收到 10 次命令拒绝、共 16 条通知，涉及房间版本冲突、状态已变和撤离后房间失效；最终流程通过，但不表示并发操作体验已无缺陷。

## 复查与启动

```powershell
python tools/import_client_art.py
python tools/client_engine.py import
# 等 client/import.log 出现导入完成后，再运行测试或客户端。
python tools/audit_client_art.py
python tools/client_engine.py test
python tools/client_engine.py art-preview
```

通过根目录 `start-client.bat` 启动当前客户端。
