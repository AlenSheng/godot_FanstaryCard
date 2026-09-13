# UI 素材持续生成队列

更新：2026-09-10

本文件是 [`UI_ASSET_MASTER_CHECKLIST.md`](UI_ASSET_MASTER_CHECKLIST.md) 的执行记录。仅记录可独立交付的透明 PNG 主体；面板、按钮、文字、数值、品质框、元素标记和动态状态继续由现有资源或 Godot 绘制。

## 队列

| 批次 | 范围 | 数量 | 状态 |
|---|---|---:|---|
| HALL-ENTRY-LAYERED | `UI/Hall/portal_background_clean.png`、`entry_background.png`、`entry_frame.png`、`entry_icon_market.png`；门户及七入口的无字分层资源 | 4 | 已导出、已登记 manifest、已接入大厅分层渲染；旧门户和 7 张合成入口图已移除，待 Godot 视觉验收 |
| HALL-CLASS-SPRITES | `UI/Hall/class_card_frame_{off,on}.png`、`class_card_portrait_{priest,mage,guardian}.png`、`class_card_heart.png`；职业选择卡分层卡体、头像与完整红心 | 6 | 已导出、已登记 manifest、已接入大厅分层渲染；旧合成职业卡和右侧职业图标已移除，待 Godot 视觉验收 |
| BAG-01 | `UI/Shop/backpack_free.png`，免费探索包独立主体 | 1 | 已生成、已写入导入目录并登记 manifest；待 Godot 运行时视觉验收 |
| EQ-CURRENT | `Equipment/{quality}/{slot}_{element}.png`，White/Green/Blue/Purple/Orange × Head/Chest/Hands/Legs/Feet × Fire/Wood/Water/Metal/Earth | 0 未完成 / 125 总数 | 白/绿/蓝/紫/橙品质五部位五元素已全部生成、写入并登记 manifest；红品质25项仍为预留 |

## 生成约束

- 单个文件单独生成，不生成整屏 UI 或带文字的素材总览。
- 真实透明背景，主体四周约 8% 安全边；建议 1024×1024 制作，导入时保留清晰度。
- 统一卡通奇幻手绘风、深青/纸色/黄铜基调；品质与元素必须分开表达。
- 生成成功后才可更新主清单状态、导入 manifest 和审计记录。
- 已存在且已验收的历史补图不重复生成；红色品质 25 个预留组合不进入当前队列。

## 运行记录

- 2026-09-11：本轮成功落盘并登记 3 张：`Equipment/White/feet_fire.png`、`feet_wood.png`、`feet_water.png`。同轮后续请求因 ImageGen 返回 401 网络/IP 未授权而中止，未将未生成项计入完成；EQ-CURRENT 剩余 17 项，后续自动重试。
- 2026-09-11：本轮成功落盘并登记 6 张：`Equipment/White/feet_metal.png`、`feet_earth.png`、`Equipment/Green/feet_fire.png`、`feet_wood.png`、`feet_water.png`、`feet_metal.png`；EQ-CURRENT 剩余 11 项，后续自动重试。
- 2026-09-11：本轮成功落盘并登记 6 张：`Equipment/Green/feet_earth.png`、`Equipment/Blue/feet_fire.png`、`feet_wood.png`、`feet_water.png`、`feet_metal.png`、`feet_earth.png`；EQ-CURRENT 剩余 5 项，后续自动重试。
- 2026-09-11：本轮成功落盘并登记 5 张：`Equipment/Purple/feet_fire.png`、`feet_wood.png`、`feet_water.png`、`feet_metal.png`、`feet_earth.png`；EQ-CURRENT 当前白至橙品质 125 项已全部完成，红品质 25 项保持预留。
