# 游戏语言表

每种语言的唯一运行时文案源是本目录的 `<语言代码>.json`。中文、英文和新增语言使用同一加载入口；不要再在 GDScript 中写固定界面文案。

- `strings`：界面标签、提示、错误、动态说明模板。脚本使用 `P.localized("稳定键")`；格式参数的名称、数量和类型需要与英文表一致。
- `card_names`：按卡牌 ID 保存名称。短名称仍应保留原意；详细效果由语言模板和实际卡牌数值组合。
- `card_face_names`：可选的小卡面短名；完整名称仍由 `card_names` 提供给详情和提示。短名须通过图鉴和商店两种卡面宽度的真实控件检查。
- `equipment_compare`、`numerical`、`monster_pool`：装备对比、数值说明和怪物卡池文案。
- `card_descriptions`：中英既有完整说明。新增语言使用本地化动态效果模板，避免升级数值落后于说明。
- `../localization_registry.json`：语言名称、字体、方向和发布状态。草稿通过独立复验后才能标记发布。
- `../localization_legacy.json`：旧来源别名和兼容数据。用于识别历史来源，不作为新增界面文案的写入入口。

变更后运行 `tools/audit_ui_text.py` 和 `tools/localization_audit.py`。后者检查所有键、格式参数、卡名、装备和数值说明是否完整。`tools/validate_ui_hidden.py` 在隔离桌面生成实际游戏控件的截图，逐档检查 960、1280、1920 分辨率；`client/tests/localization_pack_probe.gd` 检查全量卡牌控件、字体字形及现有中英回归。

缓存到客户端状态的动态文案使用 `P.message(key, arguments)` 保留键和参数。需要随语言切换的固定标签参数显式使用 `{translation_key: key}`；版本、昵称和管理员自由文本保持原样。自由文本在展示控件中关闭二次本地化。

`localization_literal_exceptions.json` 只允许逐条说明的协议格式、音频总线标识和编解码诊断。新增用户可见文本不能通过扩大例外范围跳过扫描。

语言人口覆盖使用 `config/localization_rollout.json` 中记录的数据口径。草稿覆盖和已发布覆盖分别记录，多语言人口不直接相加；覆盖估算不能替代 UI 验收。
