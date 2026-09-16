# 蓝金法师主角模型制作规范

## 目标

- 用于大厅展示、角色卡片和后续战斗扩展。
- 风格：项目现有蓝金法师设计语言 + 偏写实的游戏角色表现。
- 目标复杂度：角色本体约 50,000 三角面，法杖作为独立道具计入同一资产预算；允许因导出和法线处理产生小幅浮动。
- 交付格式：Blender `.blend` 源文件、带骨骼与动作的 `.glb`、正交四面图和预览图。

## 视觉与材质

- 深皇家蓝 / 藏蓝布料，暖金色金属包边，深棕皮革，炭黑裤装，浅青色水晶。
- 保留胸口、腰带、护腕、靴部的菱形水晶，以及长款分片披风和水晶法杖。
- 写实重点放在材质区分、服装层次、缝线/皮革接缝、金属边缘磨损和披风厚度；不堆叠电影级微表面细节。
- 面部为成年男性、短层次深棕发、自然比例；避免 Q 版、玩具感和过度夸张的肌肉。
- 人体、眼球、眉毛和短发使用 MakeHuman/MPFB 拓扑作为写实基础；铠甲、披风、法杖与蓝金装饰由项目生成脚本制作。

## 建模与绑定

- 按正面、左侧、背面、顶视四面图校准比例，所有视图保持同一基准线。
- 使用中立待机姿势，双臂略离身体，披风分片保持可读的实体厚度。
- 骨骼至少包含 root、pelvis、spine、chest、neck、head、双臂、双腿、双手和 cape.L/cape.R；法杖跟随持握手骨。
- 金属、布料、皮革、皮肤、水晶分材质；水晶只保留克制的发光效果。

## 动画规范

- 必须包含 `Idle_Breathe`、`Idle_LookAround`、`Idle_StaffFocus` 三个循环待机动作。
- 大厅端每次进入角色视图时随机选择一个待机动作，并在动作完成后随机切换；切换需有约 0.35 秒混合，避免突然跳帧。
- 待机动作幅度保持小：呼吸、视线巡视、轻微注视法杖；不改变脚底接触和角色站位。
- 帧率 24fps；动作时长建议 3–5 秒。

## 生产入口

- Blender：5.2 LTS。
- 依赖：已启用 MPFB 2.x 扩展。
- MakeHuman 基础资产位于 `third_party/makehuman_system_assets`，按随附 `LICENSE.ASSETS.md` 使用。

```text
blender --background --python tools/generate_blue_gold_mage.py
```

脚本会写出：

- `art/characters/blue_gold_mage/blue_gold_mage.blend`
- `art/characters/blue_gold_mage/blue_gold_mage.glb`
- `art/characters/blue_gold_mage/blue_gold_mage_preview.png`

## 验收

- 检查三角面数接近 50k，动作列表完整，GLB 可在 Godot 中加载。
- 当前自动生成基准约为 49,958 三角面；正式更新允许在 48k–52k 内浮动。
- 检查正/侧/背/顶四视图的披风、肩甲、腰带、水晶和法杖位置一致。
- 在大厅以 3D 模型展示，随机待机动作可循环，GLB 不可用时回退到 Mage 2D 立绘。
