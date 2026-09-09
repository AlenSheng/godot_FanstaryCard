# FantasyCard Godot 客户端

当前为连接真实服务器的开发客户端，尚未完成整份 GDD 的美术与功能验收。

## 启动

在仓库根目录双击 `start-client.bat`，或运行：

```powershell
python tools/client_engine.py play
```

也可用 Godot 4.7.2 打开 `client/project.godot`，按 F6/F5 运行。
默认连接 `http://127.0.0.1:5080`，登录页可更改地址。
本地设备账号独立保存，访问 token 仅在内存中。当前只接本地开发登录。
引擎路径读取 `A3GAME_GODOT_EXECUTABLE` 或本机 `tools/engine-local` 的验证记录。
首次资源导入可运行 `python tools/client_engine.py import`。

## 已接入

- 本地登录、Bootstrap、三职业切换、金币与材料读取。
- 图鉴、20 张编组编辑与保存，品质/职业/持有数量限制。
- 五部位穿戴保存、装备和专属武器强化、材料选择。
- 金币商店购买、市场上架/购买/下架。
- 三档包、最多两瓶药剂、准备锁定/取消、30 秒匹配与 Ready。
- Protobuf 二进制会话、事件序号去重、重连及快照恢复。
- 私有 6×6 地图、可走邻格、首次深入提示、五槽手牌、目标选择。
- 三选一、包满替换、泉水/药剂/撤离命令、PVP 离开/逃脱命令。
- 结算读取与显式确认，未完成对局和准备恢复。

键位：`1–5` 选牌，`Space` 放出，`R` 同步。所有战斗结果和资产变动过服。
新增 `battle.select_target` 投影回归修复：旧目标死亡后仍可选择最后一只存活怪。

## 验证入口

```powershell
python tools/client_engine.py validate
python tools/client_engine.py test
python tools/client_engine.py integration
```

联调会创建独立测试账号，在现有开发服务器执行真实准备、匹配、战斗和结算；
不使用正常玩家的设备 ID，也不写正常客户端的会话存档。
`evidence/live/report.json` 保存检查、事件数量和最后快照；截图和录像也在该目录。
截图按 1920×1080 保存；录制帧按 960×540、2 FPS 保存。
视频编码：安装 `imageio-ffmpeg` 至 `tools/.deps` 后运行 `tools/make_client_video.py`。

### 2026-09-09 资源接入前验证记录

- Godot 4.7.2 主场景验证通过，5 项原生测试全部通过；覆盖二进制协议、
  REST 整数序列化、会话序号恢复、权威动作校验和脚本编译。
- 服务端 259 项测试通过（Domain 130、Server 129，0 跳过），使用独立测试库。
  最后存活目标选择修复已重建并更新 `fantasycard-local-server-1`。
- 资源接入前真实联调 18 项检查通过，耗时约 168 秒：13 次连放、1 次目标切换、
  1 次奖励领取、1 次移动、断线恢复、死亡结算及确认返回营地。
- 联调保留了 2 次版本冲突、3 次本地过期意图提示及 1 次房间结束拒绝；
  主流程通过不代表没有命令被拒绝。客户端要求重新选择，不猜测服务器版本。
- 联调录像共 252 帧（2 FPS），249 个不同画面；已抽帧检查手牌、血量与阶段变化。
  `evidence/live/gameplay.mp4` 和 `review_strip.png` 来自真实 Godot 窗口。
- 录像之后补充了死亡目标/空手牌/过期战斗的出牌保护及 `Dead` 中文翻译，
  经原生回归测试验证；录像反映补充前界面。撤离、PVP 和经济写入未在本轮验证。

## 仍需完成

- 用户提供的 200 张普通/职业卡插画、三职业肖像、3 种配置内怪物已接入。
  其余 9 种怪物与对应怪物卡仍显示占位；冰霜幽灵图片无对应服务器 ID，暂未绑定。
  内置 imageGen 当前不可调用，最终全套风格验收仍待完成。
- Blender 原创门户已生成并导入。源文件 `art/portal.blend`，重建脚本
  `tools/build_portal.py`；PNG/GLB 在 `client/assets`。
- 实时协议没有分类型结算段、连放预览、本命/套装详细状态、PVP 逃脱概率、
  遗物堆物品/死者名称和完整背包容量，因此相关最终界面尚不能完整绑定。
- 当前奖励只提供物品 ID/数量，缺装备属性；市场列表同样缺完整装备详情。
- 服务没有卡牌解锁/升级/升品写入口，客户端未制造本地资产养成。
- 经济写入、PVP、泉水、撤离、满包替换等分支仍需逐项联调，不能由主链路通过推定。
- Steam SDK、移动导出、音效、正式授权字体和 15 张模块效果图尚未交付。

## 数据与边界

`tools/generate_client_schema.py` 从 `.proto` 重建字段定义。
`tools/export_client_catalog.py` 只导出服务器发布包中 Both/Client 范围的配置列，
没有直接编辑 Excel 或把服务器专属字段发布到客户端。
容器服务信息版本字符串与导出包版本尚不统一，发布前应统一配置握手。
`server/AGENTS.md` 引用的 `.agents/skills/server_create/SKILL.md` 在本仓库与本机
技能目录均不存在；本次小范围修复遵循现有 GDD、SERVER_SPEC 与服务端测试约定。

## 用户资源导入

`Cards/Art` 和 `UI` 为原始资源；导入脚本保留原图和 Unity `.meta`，
将 388 张图片复制到 `client/assets/imported`，卡牌插画归一化为 512×768。
`manifest.json` 记录来源哈希、服务器卡 ID 映射和原始九宫格边距。
运行时由 `ui/art.gd` 缓存纹理，`ui/card_view.gd` 统一绘制图鉴和手牌，
品质框维持 218×376；长描述可通过悬停查看，选中态不遮挡说明或截获点击。

```powershell
python tools/import_client_art.py
python tools/client_engine.py import
python tools/client_engine.py test
python tools/client_engine.py art-preview
```

导入脚本需要 Pillow。原清单的 `left,bottom,right,top` 会转换为 Godot 边距。
`UI/Enhance/sprite_manifest.json` 存在 JSON 语法错误，导入报告保留诊断，
该组使用默认边距；原文件未改写。带固定数字/文字/角色的战斗卡框、血条和
合成底图不参与实时数值显示，使用干净品质框和 Encounter 背景/血条替代。
准备背包页仍按服务器规则生成格子与价格文案，不使用烤死价格的背包按钮。

原生美术预览保存至 `evidence/art`，覆盖 1920×1080 和 1280×720；
其中数据明确标为测试数据，不是联机证据。资源加载检查与既有测试共 6 项通过。

首次资源接入后真实联调 18 项检查通过，约 214 秒：15 次连放、2 次领奖、
4 次移动、断线恢复和死亡结算确认。记录了 5 次服务器拒绝（2 次版本冲突、
1 次非法移动、2 次房间结束）及过期意图提示，未绕过服务器校验。
`evidence/live` 已更新为新资源版本，录像为 285 帧；双火蝠实例的插画别名、
护盾条高度和空槽品质框在该轮之后补充，通过原生测试及双分辨率预览检查。
预览对含盾双怪场景检查手牌区无需纵向滚动。此前验证数据仅作为历史记录。

## v0.58 效果图拼接

`ui/reference_ui.gd` 按 `ui_mockups_v058` 调整营地、图鉴、准备、穿戴、强化、
商店和市场；`ui/exploration_view.gd` 负责大立绘战斗、地图、当前格行动、
三选一、中层确认与结算。登录和通用确认仍使用原流程。价格、卡牌描述、
HP、目标、格子位置和动作权限来自现有状态；不照搬效果图中的示例数值。
中层确认保存待选状态，快照刷新不会将其关闭；换格/换阶段会清理旧地图视图。

两张 1920×1080 无人场景由 Blender 原创建模渲染，源为 `art/reference_scenes.blend`，
重建脚本 `tools/build_reference_scenes.py`，PNG/GLB 在 `client/assets/scenes`。
已检查地面与站位、高清输出和 Godot 叠放；属于参考图风格重建，并非逐像素复制。
GLB保留几何/基础色，程序纹理和完整灯光以blend/PNG为准。

最新验证：6 项原生测试、主场景验证通过；28 张美术预览覆盖两种分辨率，
检查按钮边界、卡牌选择绑定与中层确认刷新保留。真实联调18项通过，约200秒，
15次连放、1次领奖、1次移动、断线恢复与死亡结算确认；9次服务器命令拒绝
及过期意图提示保留在报告，未绕过权威校验。`evidence/live` 是最新布局录像，
`evidence/art` 是标有测试数据的模块预览。

随后经原生预览回归验证：锁定准备展示冻结编组/生命/本命等级；市场失效选择
清空并禁用上架；准备锁定和市场上架装备禁用强化。地图实底、Ready倒计时和
中层取消布局也已补齐；这些最后修正以原生预览为准，未重复整轮经济写入联调。

补图文件见 `docs/UI_MISSING_ASSETS.md` 与 `docs/ui_missing_assets.json`：27项，
按优先级、模块、文件名、尺寸、透明背景和中文提示词描述；优先11项需12张PNG。
已有200张卡图不重复生成。遗物内容、PVP私有信息与分类伤害预览等协议缺口
单独列出，不属于图片生成需求。
