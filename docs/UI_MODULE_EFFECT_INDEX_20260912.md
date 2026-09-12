# 新版功能模块效果图索引

更新：2026-09-12。依据 `docs/UI_ASSET_MASTER_CHECKLIST.md` 的 UI-01 至 UI-24，效果图统一按 1920×1080 评审画布登记。下表中的图片是当前工作区已有的 Godot 运行证据图，不把组件 PNG 当作整屏效果图。

## 统一标准

- 效果图：1920×1080；关键阅读区左右各留 80 px、上下各留 48 px。
- 复核尺寸：1280×720；图鉴额外复核 960×540。
- 运行时组件尺寸沿用资源清单：按钮 256×64、输入框 320×64、列表行 384×96、中小面板 384×192 / 512×256、卡牌 218×376、地图格 192×192、标题条 768×160。
- 风格：深青 `#172d35`、暖纸色 `#efe3c7`、低饱和黄铜 `#d3ae68`；品质、元素、本命色和套装语义分层；动态名称、数量、价格、生命、倒计时和百分比不烘焙进图片。

## 全部模块

| 编号 | 功能模块 | 1920×1080 效果图 | 1280×720 复核图 | 资源/验收备注 |
|---|---|---|---|---|
| UI-01 | 登录与连接 | [00_login.png](../client/evidence/live/00_login.png) | 同图 | 登录、连接状态与错误提示；正式环境不烘焙服务器地址。 |
| UI-02 | 大厅与职业选择 | [hall_1920.png](../client/evidence/art/hall_1920.png) | [hall_1280.png](../client/evidence/art/hall_1280.png) | 三职业、入口、钱包与门户；本命色专武框仍需最终验收。 |
| UI-03 | 图鉴与检索 | [collection.png](../client/evidence/audio-fonts/codex-final/collection.png) | [collection_960.png](../client/evidence/audio-fonts/codex-final/collection_960.png) | 当前证据图为 1886×1061，960 图为额外复核；需重新导出 1920×1080 版后再做最终验收。 |
| UI-04 | 卡组编成 | [deck.png](../client/evidence/audio-fonts/codex-final/deck.png) | 同图 | 当前证据图为 1886×1061；20 张编组与限制提示需在 1920×1080 版复核，动态规则由运行时绘制。 |
| UI-05 | 卡牌详情、解锁与升级 | [card_upgrade_1920.png](../client/evidence/audio-fonts/gameplay-final/card_upgrade_1920.png) | [card_upgrade_1280.png](../client/evidence/audio-fonts/gameplay-final/card_upgrade_1280.png) | 详情、材料、费用和升级状态；主体图与状态覆盖层分层。 |
| UI-06 | 普通/职业/怪物卡面模板 | [cards_1920.png](../client/evidence/art/cards_1920.png) | [cards_1280.png](../client/evidence/art/cards_1280.png) | 五品质、职业框、怪物暗红框与统一信息层。 |
| UI-07 | 装备穿戴与仓库 | [gear_1920.png](../client/evidence/art/gear_1920.png) | [gear_1280.png](../client/evidence/art/gear_1280.png) | 五部位与专武槽；完整防具主体映射需继续验收。 |
| UI-08 | 装备详情与同部位对比 | [inventory_details_bottom_1920.png](../client/evidence/audio-fonts/gameplay-final/inventory_details_bottom_1920.png) | [inventory_details_bottom_1280.png](../client/evidence/audio-fonts/gameplay-final/inventory_details_bottom_1280.png) | 对比区、差值箭头和绑定状态；装备主体图需保持同源。 |
| UI-09 | 防具与专武强化 | [enhancement_quote_1920.png](../client/evidence/audio-fonts/gameplay-final/enhancement_quote_1920.png) | [enhancement_quote_1280.png](../client/evidence/audio-fonts/gameplay-final/enhancement_quote_1280.png) | 强化节点、报价与材料流程；专武本命框待修正。 |
| UI-10 | 探索准备 | [prep_1920.png](../client/evidence/art/prep_1920.png) | [prep_1280.png](../client/evidence/art/prep_1280.png) | 三职业、五防具槽、专武槽、背包档位和准备操作。 |
| UI-11 | 匹配、准备就绪与等待 | [03_matching.png](../client/evidence/live/03_matching.png) | 同图 | 队列、确认、倒计时与取消；状态图标采用 Matchmaking 资源。 |
| UI-12 | 小地图与移动 | [map_1920.png](../client/evidence/art/map_1920.png) | [map_1280.png](../client/evidence/art/map_1280.png) | 可移动、不可移动、当前位置、Boss/泉水图例。 |
| UI-13 | PVE 战斗 | [battle_1920.png](../client/evidence/art/battle_1920.png) | [battle_1280.png](../client/evidence/art/battle_1280.png) | 怪物、意图、手牌、元素反馈和战斗转场。 |
| UI-14 | PVP 战斗 | [pvp_1920.png](../client/evidence/art/pvp_1920.png) | [pvp_1280.png](../client/evidence/art/pvp_1280.png) | 双方状态、VS、先手保护、断线与结束状态。 |
| UI-15 | 三选一与包满替换 | [choose_1920.png](../client/evidence/art/choose_1920.png) | [choose_1280.png](../client/evidence/art/choose_1280.png) | 装备/碎片/即时回血三栏；替换双图与动态费用不烘焙。 |
| UI-16 | 清怪后行动区 | [action_1920.png](../client/evidence/art/action_1920.png) | [action_1280.png](../client/evidence/art/action_1280.png) | 泉水、药剂、撤离、遗物、邻格入口及读条。 |
| UI-17 | 探索背包与局内换装 | [inventory_36_1920.png](../client/evidence/audio-fonts/gameplay-final/inventory_36_1920.png) | [inventory_36_1280.png](../client/evidence/audio-fonts/gameplay-final/inventory_36_1280.png) | 36 格、安全格、拖动、穿戴和详情；容量状态覆盖层独立。 |
| UI-18 | 遗物检索与拾取 | [relics_multiple_1920.png](../client/evidence/audio-fonts/gameplay-final/relics_multiple_1920.png) | [relics_multiple_1280.png](../client/evidence/audio-fonts/gameplay-final/relics_multiple_1280.png) | 多遗物、归属、拾取、替换和失效状态。 |
| UI-19 | 金币商店 | [shop_1920.png](../client/evidence/art/shop_1920.png) | [shop_1280.png](../client/evidence/art/shop_1280.png) | 卡包、碎片包、背包商品与购买状态；商品种类由服务端决定。 |
| UI-20 | 金币市场 | [market_1920.png](../client/evidence/art/market_1920.png) | [market_1280.png](../client/evidence/art/market_1280.png) | 上架、价格、手续费、购买和冲突状态。 |
| UI-21 | 中层风险提示 | [midlayer_1920.png](../client/evidence/art/midlayer_1920.png) | [midlayer_1280.png](../client/evidence/art/midlayer_1280.png) | 风险遮罩、目标格、确认/取消与恢复操作。 |
| UI-22 | 撤离与死亡结算 | [settlement_1920.png](../client/evidence/art/settlement_1920.png) | [settlement_1280.png](../client/evidence/art/settlement_1280.png) | 成功/死亡、带回/遗失清单和结算状态。 |
| UI-23 | 战斗属性与套装详情 | [battle_status_1920.png](../client/evidence/audio-fonts/gameplay-final/battle_status_1920.png) | [battle_status_1280.png](../client/evidence/audio-fonts/gameplay-final/battle_status_1280.png) | 本命、破击/载壁/生息、元素属性与长内容滚动。 |
| UI-24 | 音效设置与全局反馈 | [sound_settings_1920.png](../client/evidence/audio-fonts/sound_settings_1920.png) | [sound_settings_1280.png](../client/evidence/audio-fonts/sound_settings_1280.png) | 音量、静音、试听、F10 提示与统一反馈材质。 |

## 交付边界

清单第 11 节提到的旧 `ui_mockups_v058` 15 张 PNG/PSD 当前不在工作区；本索引引用的是现有新版 Godot 运行证据图，不能替代旧源文件归档。若要恢复旧稿，应另行找回 `ui_map`、`ui_pve`、`ui_pvp`、`ui_choose`、`ui_action`、`ui_prep`、`ui_hall`、`ui_midlayer`、`ui_remnant`、`ui_shop`、`ui_market`、`ui_codex`、`ui_gear`、`ui_enhance`、`ui_cards` 及对应 PSD。
