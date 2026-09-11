# UI 素材持续生成队列

更新：2026-09-11

本文件是 [`UI_ASSET_MASTER_CHECKLIST.md`](UI_ASSET_MASTER_CHECKLIST.md) 的执行记录。记录可独立交付的透明 PNG 主体、面板、按钮和状态素材；文字、数值、品质框、元素标记和动态状态数据继续由运行时驱动。

## 队列

| 批次 | 范围 | 数量 | 状态 |
|---|---|---:|---|
| BAG-01 | `UI/Shop/backpack_free.png`，免费探索包独立主体 | 1 | 已生成、已写入导入目录并登记 manifest；待 Godot 运行时视觉验收 |
| EQ-CURRENT | `Equipment/{quality}/{slot}_{element}.png`，White/Green/Blue/Purple/Orange × Head/Chest/Hands/Legs/Feet × Fire/Wood/Water/Metal/Earth | 0 未完成 / 125 总数 | 白/绿/蓝/紫/橙品质五部位五元素已全部生成、写入并登记 manifest；红品质25项仍为预留 |
| MAIL-UI-20260911 | 邮件入口、列表卡、未读角标、领取按钮、钻石附件图标 | 5 已生成 / 5 总数 | 已写入导入目录并登记 manifest；待邮件界面接入与视觉验收 |
| UI-ART-01-20260911 | 登录/会话状态面板 | 6 已生成 / 6 个已规划组件 | 面板、提示底、连接/错误/成功图标和加载旋环已生成并登记；待接入与视觉验收 |
| UI-ART-02-20260911 | 大厅状态徽章 | 5 已生成 / 5 个已规划组件 | 锁定、暂不可用、空钱包、准备锁定、交易处理中徽章已生成并登记；待大厅接入与视觉验收 |
| UI-ART-03-20260911 | 图鉴/卡组状态覆盖层 | 6 已生成 / 6 个本批组件 | 卡牌悬停、键盘焦点、未拥有、不可编入覆盖层，空结果插图与加载旋环已生成并登记；待图鉴接入与视觉验收 |
| UI-ART-04-20260911 | 卡牌详情反馈状态 | 9 已生成 / 9 个规划组件 | 提示底、未解锁、可解锁、可升级、材料不足、满级、报价过期、成功、失败均已生成并登记；待详情界面接入与视觉验收 |
| UI-ART-05-20260911 | 装备对比与强化反馈 | 7 已生成 / 7 个规划组件 | 双栏对比底、正/负变化箭头、候选选中框、材料不可用遮罩、强化节点条、报价/结果提示底已生成并登记；待接入与视觉验收 |
| UI-ART-06-20260911 | 匹配与集结状态 | 10 已生成 / 10 个规划组件 | 集结面板、队列等待、匹配成功、确认、已确认、超时、取消、掉线、重连图标与倒计时轨道均已生成并登记；待匹配界面接入与视觉验收 |
| UI-ART-07-20260911 | 地图移动状态 | 10 已生成 / 10 个规划组件 | 5 个格子覆盖层、移动箭头、连线、Boss/泉水图例图标和风险提示底均已生成并登记；待地图界面接入与视觉验收 |
| UI-ART-08-20260911 | 战斗信息与反馈 | 7 已生成 / 7 个本批组件 | 目标圈、怪物意图底、牌槽/可出/不可出覆盖层、异常状态底和转场横幅已生成并登记；生命/护盾/蓄能条复用现有 Battle 资源 |
| UI-ART-09-20260911 | 行动入口状态 | 7 已生成 / 7 个本批组件 | 可用、悬停、不可用、已消耗、完成覆盖层，读条环与状态角标已生成并登记；遗物/泉水/撤离/药剂主体复用现有资源 |
| UI-ART-10-20260911 | 背包与拖放状态 | 7 已生成 / 7 个本批组件 | 普通、选中、安全、可放入、禁止放入、拖动源与拖动目标格覆盖层已生成并登记；数量/等级/绑定角标复用运行时与现有控件 |
| UI-ART-11-20260911 | 商店与市场状态 | 7 已生成 / 7 个本批组件 | 商品卡普通/选中/售罄/余额不足/绑定不可售/过期覆盖层与市场冲突处理中行底已生成并登记；交易确认面板留待后续批次 |
| UI-ART-11-20260911 | 商店与市场状态 | 7 已生成 / 7 个本批组件 | 交易确认面板、价格行、余额徽章、确认/取消按钮、处理中面板和失败徽章已生成并登记；待商店界面接入与视觉验收 |
| UI-ART-12-20260911 | 风险与结算状态 | 7 已生成 / 7 个本批组件 | 风险确认、结算横幅/结果面板、带回/遗失分区和成功/死亡结果图标已生成并登记；待结算界面接入与视觉验收 |
| UI-ART-13-20260911 | 套装与属性详情 | 7 已生成 / 7 个本批组件 | 破击/载壁/生息未激活与已激活徽章各 3 张及属性详情面板已生成并登记；部分激活态与控制图标留待后续批次 |
| UI-ART-13-20260911 | 套装与属性详情 | 7 已生成 / 7 个本批组件 | 破击/载壁/生息部分激活徽章、属性详情展开/收起/关闭控制图标和长文本滚动面板已生成并登记；待详情界面接入与视觉验收 |
| UI-ART-14-20260911 | 全局控件皮肤 | 7 已生成 / 7 个本批组件 | 主/次/危险按钮、输入框、复选框、开关和滑杆皮肤已生成并登记；下拉框、Tooltip、列表行、滚动条等留待后续批次 |
| UI-ART-14-20260911 | 全局控件皮肤 | 7 已生成 / 7 个本批组件 | 下拉框、Tooltip、列表行、模态遮罩、分割线、滚动条和键盘焦点皮肤已生成并登记；其余状态与拖放提示留待后续批次 |
| UI-ART-14-20260911 | 全局控件皮肤 | 7 已生成 / 7 个本批组件 | 按钮悬停/按下/禁用/选中/忙碌状态及拖放允许/禁止覆盖层已生成并登记；待全局控件接入与视觉验收 |
| UI-ART-14-20260911 | 全局控件皮肤 | 7 已生成 / 7 个本批组件 | 加载、错误、成功、警告、信息、离线和重连状态徽章已生成并登记；待全局反馈接入与视觉验收 |
| UI-ART-14-20260911 | 全局控件皮肤 | 7 已生成 / 7 个本批组件 | 空状态面板、重试按钮、刷新/关闭/返回/搜索/清空控件已生成并登记；待全局反馈接入与视觉验收 |
| UI-ART-14-20260911 | 全局控件皮肤 | 7 已生成 / 7 个本批组件 | 标签页普通/选中/禁用皮肤、分页前后翻页控件和升序/降序排序控件已生成并登记；待全局控件接入与视觉验收 |
| UI-ART-14-20260911 | 全局控件皮肤 | 7 已生成 / 7 个本批组件 | 复选框勾选/禁用、开关开/关/禁用、滑杆手柄和进度轨道资源已生成并登记；待全局控件接入与视觉验收 |
| UI-ART-14-20260911 | 全局控件皮肤 | 7 已生成 / 7 个本批组件 | 模态标题/页脚、通用面板头/尾、通知 Toast、警告 Tooltip 和状态条已生成并登记；待全局控件接入与视觉验收 |
| UI-ART-14-20260911 | 全局控件皮肤 | 7 已生成 / 7 个本批组件 | 列表行悬停/选中/禁用/拖动源/放置目标状态及输入框焦点/错误状态已生成并登记；待全局控件接入与视觉验收 |
| UI-ART-14-20260911 | 全局控件皮肤 | 7 已生成 / 7 个本批组件 | 输入框只读/禁用/成功状态、下拉框悬停/选中/禁用状态和信息 Tooltip 已生成并登记；待全局控件接入与视觉验收 |
| UI-ART-14-20260911 | 全局控件皮肤 | 7 已生成 / 7 个本批组件 | 成功/错误 Tooltip、列表行键盘焦点、滚动条普通/悬停滑块和滑杆悬停/禁用手柄已生成并登记；待全局控件接入与视觉验收 |

## 生成约束

- 单个文件单独生成，不生成整屏 UI 或带文字的素材总览。
- 真实透明背景，主体四周约 8% 安全边；建议 1024×1024 制作，导入时保留清晰度。
- 统一卡通奇幻手绘风、深青/纸色/黄铜基调；品质与元素必须分开表达。
- 生成成功后才可更新主清单状态、导入 manifest 和审计记录。
- 面板、按钮和状态素材按主清单的运行尺寸制作；优先九宫格和覆盖层，禁止把整屏透明图或固定文字打入包体。
- 已存在且已验收的历史补图不重复生成；红色品质 25 个预留组合不进入当前队列。

## 运行记录

- 2026-09-11：本轮成功落盘并登记 3 张：`Equipment/White/feet_fire.png`、`feet_wood.png`、`feet_water.png`。同轮后续请求因 ImageGen 返回 401 网络/IP 未授权而中止，未将未生成项计入完成；EQ-CURRENT 剩余 17 项，后续自动重试。
- 2026-09-11：本轮成功落盘并登记 6 张：`Equipment/White/feet_metal.png`、`feet_earth.png`、`Equipment/Green/feet_fire.png`、`feet_wood.png`、`feet_water.png`、`feet_metal.png`；EQ-CURRENT 剩余 11 项，后续自动重试。
- 2026-09-11：本轮成功落盘并登记 6 张：`Equipment/Green/feet_earth.png`、`Equipment/Blue/feet_fire.png`、`feet_wood.png`、`feet_water.png`、`feet_metal.png`、`feet_earth.png`；EQ-CURRENT 剩余 5 项，后续自动重试。
- 2026-09-11：本轮成功落盘并登记 5 张：`Equipment/Purple/feet_fire.png`、`feet_wood.png`、`feet_water.png`、`feet_metal.png`、`feet_earth.png`；EQ-CURRENT 当前白至橙品质 125 项已全部完成，红品质 25 项保持预留。
- 2026-09-11：首批 UI 资源成功落盘并登记 6 张：`UI/Hall/mail_icon.png`、`mail_panel.png`、`mail_unread_badge.png`、`mail_claim_button.png`、`UI/Item/mail_attachment_diamond.png`、`UI/Session/login_status_panel.png`；邮件 5 项已完成，UI-ART-01 完成登录状态面板，待接入和视觉验收。
- 2026-09-11：本轮 ImageGen 成功落盘并登记 4 张：`UI/Session/connection_icon.png`、`auth_error_icon.png`、`success_icon.png`、`loading_spinner_strip.png`；前三张规范为 64×64，加载图集规范为 512×64，均为 RGBA 且 Alpha 0–255。后续提示底请求返回 401（IP 未授权），本轮停止，失败请求未计入完成。
- 2026-09-11：补生成并登记 `UI/Session/prompt_panel.png`；运行时尺寸 384×96，RGBA，Alpha 0–255，适配九宫格提示底。UI-ART-01 的 6 个规划组件已全部落盘，后续转入 UI-ART-02 大厅状态徽章。
- 2026-09-11：生成并登记 UI-ART-02 五个大厅徽章：`UI/Hall/hall_locked_badge.png`、`hall_unavailable_badge.png`、`empty_wallet_badge.png`、`ready_locked_badge.png`、`trading_badge.png`；均为 64×64 RGBA、Alpha 0–255，后续转入 UI-ART-03。
- 2026-09-11：生成并登记 UI-ART-03 六个图鉴/卡组状态素材：`UI/Codex/card_hover_overlay.png`、`card_focus_overlay.png`、`card_unowned_overlay.png`、`card_unavailable_overlay.png`（218×376）、`codex_empty_state.png`（256×192）和 `codex_loading_spinner.png`（128×128）；均为 RGBA、Alpha 0–255，未烘焙文字，待图鉴接入与视觉验收。
- 2026-09-11：生成并登记 UI-ART-04 首批六个卡牌详情反馈素材：`UI/CardDetail/card_feedback_prompt_panel.png`（384×128，九宫格边距 24 px）、`card_locked_state.png`、`card_unlockable_state.png`、`card_upgradeable_state.png`、`card_material_insufficient_state.png`、`card_max_level_state.png`（均 64×64）；均为 RGBA、Alpha 0–255，未烘焙文字，待详情接入与视觉验收。报价过期、成功、失败三项留待后续批次。

## DECK-UI-01 / DECK-UI-02（2026-09-11）

已生成并登记到 `client/assets/imported/`，待实际界面视觉验收：
- UI/Codex/deck_row_common_orange.png
- UI/Codex/deck_row_class_orange.png
- UI/Codex/deck_row_selected.png
- UI/Codex/deck_empty_state.png
- UI/Codex/deck_capacity_badge.png

要求：透明背景；技能行、空状态与容量装饰采用九宫格友好边角；文字、数量和状态由运行时渲染。

交付核验：9 张文件均为 RGBA PNG，Alpha 范围为 0–254/255；manifest 已更新，未烘焙文字、数量或按钮文案。

## SEASON-UI（2026-09-11）

已生成并登记到 `client/assets/imported/UI/Season/`，待实际界面视觉验收：
- UI/Season/season_settlement_panel.png
- UI/Season/expedition_reward_panel.png
- UI/Season/season_retain_data_panel.png
- UI/Season/expedition_reset_warning_panel.png

所有面板要求透明背景、九宫格友好边角；标题、说明、奖励数量、清空字段和按钮文字由运行时多语言文本渲染。

- 2026-09-11：补齐 UI-ART-04 三个卡牌详情结果状态素材：`UI/CardDetail/card_quote_expired_state.png`、`card_success_state.png`、`card_failure_state.png`（均 64×64）；均为 RGBA、Alpha 0–255，未烘焙文字，合计约 0.022 MiB，低于 8 MiB 包体预算。UI-ART-04 的 9 个规划组件已全部落盘并登记，待详情界面接入与视觉验收。
- 2026-09-11：生成并登记 UI-ART-05 本批 6 项：`UI/Equipment/equipment_compare_panel.png`（512×256，九宫格友好）、`stat_increase_arrow.png`、`stat_decrease_arrow.png`（48×48）、`enhance_candidate_selected.png`、`enhance_material_unavailable.png`（128×128）和 `enhance_progress_nodes.png`（384×64）；均为 RGBA、Alpha 0–255，未烘焙文字，合计约 0.233 MiB。报价/结果提示底作为下一批保留，待装备界面接入与视觉验收。
- 2026-09-11：补齐 UI-ART-05 报价/结果提示底 `UI/Equipment/equipment_quote_result_panel.png`（384×128，九宫格友好），并生成 UI-ART-06 首批集结面板与四个状态图标：`UI/Matchmaking/match_gathering_panel.png`（512×256）、`queue_waiting_icon.png`、`match_found_icon.png`、`match_confirm_icon.png`、`match_ready_icon.png`（均 64×64）；均为 RGBA、Alpha 0–255，未烘焙文字，合计约 0.233 MiB，低于 8 MiB 包体预算。
- 2026-09-11：完成 UI-ART-06 剩余 5 项：`UI/Matchmaking/match_timeout_icon.png`、`match_cancel_icon.png`、`match_disconnected_icon.png`、`match_reconnect_icon.png`（均 64×64）和 `match_countdown_track.png`（384×64）；均为 RGBA、Alpha 0–255，未烘焙文字，合计约 0.035 MiB，低于 8 MiB 包体预算。UI-ART-06 的 10 个规划组件已全部落盘并登记，待匹配界面接入与视觉验收。
- 2026-09-11：完成 UI-ART-07 10 项地图移动资源：5 个 192×192 格子覆盖层、`map_move_arrow.png`（64×64）、`map_path_link.png`（192×192）、`map_boss_legend_icon.png` 与 `map_spring_legend_icon.png`（64×64）以及 `map_risk_warning_panel.png`（512×192）；均为 RGBA、Alpha 0–255，未烘焙文字，合计约 0.309 MiB，低于 8 MiB 包体预算。
- 2026-09-11：完成 UI-ART-08 本批 7 项：`battle_target_ring.png`（256×256）、`battle_monster_intent_panel.png`（256×96）、牌槽/可出/不可出覆盖层（218×376）、`battle_status_effect_panel.png`（256×64）和 `battle_transition_banner.png`（768×160）；均为 RGBA、Alpha 0–255，未烘焙文字，合计约 0.329 MiB，低于 8 MiB 包体预算。生命/护盾/蓄能条沿用现有 Battle 资源。
- 2026-09-11：完成 UI-ART-09 本批 7 项：可用/悬停/不可用/已消耗/完成覆盖层（256×256）、`action_progress_ring.png`（128×128）和 `action_status_badge.png`（64×64）；均为 RGBA、Alpha 0–255，未烘焙文字，合计约 0.326 MiB，低于 8 MiB 包体预算。遗物、泉水、撤离和药剂主体沿用现有资源。
- 2026-09-11：完成 UI-ART-10 本批 7 项：背包普通/选中/安全/可放入/禁止放入/拖动源/拖动目标覆盖层（均 128×128）；均为 RGBA、Alpha 0–255，未烘焙文字，合计约 0.113 MiB，低于 8 MiB 包体预算。数量、等级、绑定等角标保持运行时绘制或复用现有控件。
- 2026-09-11：完成 UI-ART-11 本批 7 项：商品卡普通/选中/售罄/余额不足/绑定不可售/过期覆盖层（均 256×320）和 `market_row_conflict_processing_overlay.png`（384×96）；均为 RGBA、Alpha 0–255，未烘焙文字，合计约 0.409 MiB，低于 8 MiB 包体预算。交易确认面板留待后续批次。
- 2026-09-11：完成 UI-ART-11 本批 7 项：交易确认面板/处理中面板（384×192）、价格行（384×64）、余额/失败徽章（64×64）和确认/取消按钮（256×64）；均为 RGBA、Alpha 0–255，未烘焙文字，合计约 0.192 MiB，低于 8 MiB 包体预算。
- 2026-09-11：完成 UI-ART-12 本批 7 项：风险确认底（512×192）、结算横幅（768×160）、结果面板（512×320）、带回/遗失分区底（384×192）和成功/死亡图标（96×96）；均为 RGBA、Alpha 0–255，未烘焙文字，合计约 0.427 MiB，低于 8 MiB 包体预算。
- 2026-09-11：完成 UI-ART-13 本批 7 项：破击/载壁/生息未激活与已激活徽章（均 96×96）及 `attribute_detail_panel.png`（384×256）；均为 RGBA、Alpha 0–255，未烘焙文字，合计约 0.144 MiB，低于 8 MiB 包体预算。部分激活态与展开/收起/关闭控制图标留待后续批次。
- 2026-09-11：完成 UI-ART-13 本批 7 项：破击/载壁/生息部分激活徽章（96×96）、属性详情展开/收起/关闭图标（48×48）和长文本滚动面板（384×256）；均为 RGBA、Alpha 0–255，未烘焙文字，合计约 0.168 MiB，低于 8 MiB 包体预算。
- 2026-09-11：完成 UI-ART-14 本批 7 项：主/次/危险按钮（256×64）、输入框（320×64）、复选框/开关（64×64）和滑杆（256×64）；均为 RGBA、Alpha 0–255，未烘焙文字，合计约 0.049 MiB，低于 8 MiB 包体预算。下拉框、Tooltip、列表行、滚动条、遮罩与焦点控件留待后续批次。
- 2026-09-11：完成 UI-ART-14 本批 7 项：下拉框（320×64）、Tooltip（256×128）、列表行（384×96）、模态遮罩（256×256）、分割线（256×32）、滚动条切片（32×128）和键盘焦点（256×64）；均为 RGBA、Alpha 0–255，未烘焙文字，合计约 0.135 MiB，低于 8 MiB 包体预算。其余状态与拖放提示留待后续批次。
- 2026-09-11：完成 UI-ART-14 本批 7 项：按钮悬停/按下/禁用/选中/忙碌状态（均 256×64）及拖放允许/禁止覆盖层（均 256×256）；均为 RGBA、Alpha 0–255，未烘焙文字，合计约 0.239 MiB，低于 8 MiB 包体预算。
- 2026-09-11：完成 UI-ART-14 本批 7 项：加载、错误、成功、警告、信息、离线和重连状态徽章（均 64×64）；均为 RGBA、Alpha 0–255，未烘焙文字，合计约 0.053 MiB，低于 8 MiB 包体预算。
- 2026-09-11：完成 UI-ART-14 本批 7 项：空状态面板（384×192）、重试按钮（256×64）和刷新/关闭/返回/搜索/清空控件（均 64×64）；均为 RGBA、Alpha 0–255，未烘焙文字，合计约 0.127 MiB，低于 8 MiB 包体预算。
- 2026-09-11：完成 UI-ART-14 本批 7 项：标签页普通/选中/禁用皮肤（均 192×56）、分页前后翻页控件和升序/降序排序控件（均 64×64）；均为 RGBA、Alpha 0–255，未烘焙文字，合计约 0.057 MiB，低于 8 MiB 包体预算。
- 2026-09-11：完成 UI-ART-14 本批 7 项：复选框勾选/禁用（64×64）、开关开/关/禁用（128×64）、滑杆手柄（64×64）和进度轨道（256×32）；均为 RGBA、Alpha 0–255，未烘焙文字，合计约 0.047 MiB，低于 8 MiB 包体预算。
- 2026-09-11：完成 UI-ART-14 本批 7 项：模态标题/页脚（384×64）、通用面板头（512×64）/尾（512×48）、通知 Toast（384×96）、警告 Tooltip（256×128）和状态条（384×48）；均为 RGBA、Alpha 0–255，未烘焙文字，合计约 0.094 MiB，低于 8 MiB 包体预算。
- 2026-09-11：完成 UI-ART-14 本批 7 项：列表行悬停/选中/禁用/拖动源/放置目标状态（均 384×96）及输入框焦点/错误状态（均 320×64）；均为 RGBA、Alpha 0–255，未烘焙文字，合计约 0.134 MiB，低于 8 MiB 包体预算。
- 2026-09-11：完成 UI-ART-14 本批 7 项：输入框只读/禁用/成功状态、下拉框悬停/选中/禁用状态（均 320×64）和信息 Tooltip（256×128）；均为 RGBA、Alpha 0–255，未烘焙文字，合计约 0.070 MiB，低于 8 MiB 包体预算。
- 2026-09-11：完成 UI-ART-14 本批 7 项：成功/错误 Tooltip（均 256×128）、列表行键盘焦点（384×96）、滚动条普通/悬停滑块（均 32×64）和滑杆悬停/禁用手柄（均 64×64）；均为 RGBA、Alpha 0–255，未烘焙文字，合计约 0.099 MiB，低于 8 MiB 包体预算。

