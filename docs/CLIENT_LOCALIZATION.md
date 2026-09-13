# Client Localization

客户端界面文案统一由两张 JSON 表维护：

| 文件 | 用途 | 维护范围 |
| --- | --- | --- |
| `client/data/localization_config.json` | 基础 UI 文案 | 标题、登录、设置、邮件、道具、品质、五行、部位、悬浮提示 |
| `client/data/localization_modules.json` | 模块 UI 文案 | 大厅、图鉴、穿戴、背包、探索、战斗、奖励、商店、集市、网络错误 |

两张表都必须同时包含 `zh-CN` 和 `en`，同一层级的键集合必须一致。当前模块表包含 298 个中英文键。

## 调用约定

- 普通固定文案使用 `P.localized_text("中文源文案")`，旧模块传入中文也会自动映射到配置键。
- 已知配置键使用 `P.localized("key")`。
- 道具、品质、五行、职业、部位使用 `P.word(value)` 或 `P.localized_word(value)`。
- 带数量、百分比或状态的组合文本先保留 `%s` 占位，再交给 `P.localized_text()`。
- `ReferenceUI.text()`、`ReferenceUI.button()`、`Main._label()`、`Main._button()` 已统一执行本地化；新增界面优先使用这些封装。
- 多语言不会改变既有布局矩形或容器尺寸。文本控件会按实际宽高自动缩小字号，并对按钮启用省略保护，避免英文长文案导致 UI 偏移或重叠。

## 校验

切换语言后需要重新渲染当前界面。修改表格后执行：

```powershell
Get-Content client/data/localization_config.json -Raw | ConvertFrom-Json | Out-Null
Get-Content client/data/localization_modules.json -Raw | ConvertFrom-Json | Out-Null
```

并用 Godot 无头模式启动一个客户端场景，确认没有脚本解析错误。
