# 通用物品格规范

## 资源

- **资源路径**：`client/assets/imported/UI/Prep/exploration_prep_backpack_cell_empty_normal.png`
- **资源键**：`UI/Prep/exploration_prep_backpack_cell_empty_normal.png`
- **原图尺寸**：144 × 144 px（正方形）
- **九宫格**：不切九宫格。该资源是完整方形边框，必须保持等比缩放，避免横向或纵向拉伸边角。
- **推荐显示尺寸**：96 × 96 px
- **格子间距**：8 px（横向、纵向）
- **代码常量**：`Art.COMMON_CELL_KEY`、`Art.COMMON_CELL_SOURCE_SIZE`、`Art.COMMON_CELL_DISPLAY_SIZE`

## 使用范围

通用物品格用于背包、探索准备背包、邮件附件和探索中的物品/遗物格。所有新建的物品格应复用 `Art.COMMON_CELL_KEY`，并使用 `Art.COMMON_CELL_DISPLAY_SIZE` 设置最小尺寸。

品质装备槽继续使用 `exploration_prep_equipment_slot_frame_{quality}.png`，卡牌图鉴使用卡牌自身的卡框，不替换为通用物品格。

## 状态约定

- 空格中心保持透明/深色内容区，物品图标居中显示。
- 安全格、选中态等状态通过叠加图标或颜色边框表达，不修改原图文件。
- 数量、序号和名称应限制在格子内部，文本过长时使用自动换行或省略。

品质装备槽的品质底色必须使用不透明填充，并按品质框原图的内沿缩放铺满边框内部；渲染时先绘制品质框，再以内缩色块覆盖其黑色中心，最后绘制图标与文字。

## 已接入界面

- `client/ui/main.gd`：探索准备背包格
- `client/ui/inventory_view.gd`：探索背包格（96 × 96）
- `client/ui/reference_ui.gd`：邮件详情附件格（96 × 96，三列排列）
- `client/ui/exploration_view.gd`：探索场景中的通用格引用
- `client/ui/item_visual.gd`：装备对比等详情界面的可复用分层装备图。固定顺序为通用格底板、动态品质底色、装备主体、品质外框；名称、等级、元素、词缀和状态全部为独立文本/徽记层。

## 装备对比分层

- 弹窗大底复用 `UI/CardCodex/card_codex_dialog_panel_normal.png`，标题条、关闭按钮和确认/取消按钮分别复用 CardCodex 对应无字资源。
- 装备图统一调用 `ItemVisual.equipment()`，不在任何装备图片中烘焙品质、元素、强化等级或词缀文字。
- 异元素装备分别显示各自元素增伤与抗性，禁止把火增伤与水增伤等不同键相减；同名通用属性才允许显示数值变化。
- 破击、载壁、生息徽记复用 Prep 的独立属性图标；套装件数、激活门槛、当前值和穿戴后值全部由装备数据动态计算。
- `UI/Prep/exploration_prep_set_effect_panel_normal.png` 含固定中文，不用于新弹窗。缺少的无字状态卡见 `UI-EQUIPMENT-COMPARE-SET-PANEL-CLEAN`，交付前继续使用代码面板。
