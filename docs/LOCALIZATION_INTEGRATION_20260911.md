# 多语言接入记录

更新：2026-09-11

客户端现在通过 `I18n` 统一读取语言。语言偏好保存到 `user://settings.cfg`，默认简体中文，当前提供简体中文和 English；切换后重新渲染当前界面。

文本来源如下：

- `config/FantasyCard_Config.xlsx`：由 `tools/export_client_catalog.py` 导出运行时卡牌、装备和经济配置到 `client/data/catalog.json`。
- `config/card_descriptions.json`：导出到 `client/data/card_descriptions.json`，卡牌完整描述按 `zh` / `en` 读取。
- `config/ui_text.json`：界面固定文案表，导出到 `client/data/ui_text.json`，由 `client/ui/i18n.gd` 加载。

主界面、图鉴/编卡和设置面板的文本入口已经接入 `I18n.t()`；卡牌描述已按当前语言选择。设置入口位于主界面右上角，提供语言切换、音量、静音和退出登录。设置面板复用现有卡牌 Codex 蓝/橙按钮资源，没有新增待生成 PNG。

剩余迁移工作：配置表中的卡牌名称、装备名称和部分服务端错误消息当前仍为单语言值；其它旧界面中直接赋值的动态长句需要继续补充到 `config/ui_text.json` 后才能覆盖完整英文显示。
