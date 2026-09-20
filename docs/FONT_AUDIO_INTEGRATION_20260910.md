# 字体与音效接入记录

日期：2026-09-10。客户端已加入适合深青石材、羊皮纸和克制黄铜风格的随包字体与短音效。`FONT-CJK`、`AUDIO-SFX` 的资源交付及功能接入已完成；本记录不改写原 27 项、28 PNG、418 张位图的统计或历史验收记录。

注：本页是 2026-09-10 的历史交付记录；后续 BGM、环境循环及战斗双方动作音效见 [音频扩展交付记录](AUDIO_MUSIC_COMBAT_20260920.md)。

## 使用方式

- 标题和卡名使用思源宋体 SC 半粗，正文使用思源黑体 SC；生命、价格、数量与战斗飘字使用清晰的等宽数字角色。
- 左下“音效”可调整 0–100% 音量、静音和试听，`F10` 快捷切换静音。默认音量 65%，设置保存在本机 `user://audio_settings.cfg`。
- 按钮、选牌、抽牌、出牌、直伤/五行受击、治疗、护盾、领奖、购买、强化、穿戴、药剂、移动、撤离与死亡都有对应短提示。

## 字体与许可

`client/assets/fonts/` 包含 Adobe 官方完整地区字体原版，总计 41,230,364 字节，约 39.3 MiB：

- `SourceHanSerifSC-SemiBold.otf`：思源宋体 SC SemiBold 2.003，标题角色。
- `SourceHanSansSC-Regular.otf`：思源黑体 SC Regular 2.005，正文与数字角色。
- 两份 `LICENSE-SourceHan*.txt` 保存 SIL Open Font License 1.1 和 Adobe 版权说明；允许随游戏分发。
- `manifest.json` 保存官方来源、发布标签、上游 Git blob、SHA-256、大小及字形覆盖；`verification.json` 保存本地核验，`README.md` 说明用途和许可范围。

两字体均保留 65,535 个字形，分别映射 44,779、44,853 个 Unicode 码点；均覆盖全部基本 CJK 和扩展 A。未按当前界面文字裁字，可供后续文案和玩家名使用，但不承诺所有 Unicode 表情或历史罕见汉字。上游 Git blob 校验确认二进制原样保留。

`client/ui/palette.gd` 提供 `font("title")`、`font("body")`、`font("number")` 和 `font_for_text(value, size)`。系统字体回退已关闭；标题仅回退到随包正文。数字 0–9 原生均宽 555/1000 em，数字角色明确关闭比例宽度 `pwid`；该字体不提供 `tnum` 功能。图片中已有的烘焙文字仍属于原图片。

固定文字框按字体实际行高调整字号；卡名、等级、职业标记与怪物页脚单独调整位置，避免
新字体被旧高度裁掉。原生测试和截图检查实际可见行数、卡内边界及相邻元素不重叠。

## 音效、源文件与播放

`client/assets/audio/` 包含 22 个原创单声道 48 kHz、16-bit PCM WAV，总计 998,408 字节。每段约 0.14–1.02 秒，纸牌摩擦、石材冲击、低调金属共鸣和五行声色保持短促，避免覆盖连续操作。

`tools/generate_game_audio.py` 是可编辑的制作源文件，以固定种子、噪声和数学振荡器合成全部波形，无外部录音或第三方采样。资源与音效设计说明以 CC0 1.0 Universal 提供，许可保存在 `client/assets/audio/LICENSE.txt`；此许可不扩展到其他项目资源。`README.md` 保存制作环境和重建方法，`manifest.json` 保存事件文件映射、描述、时长、峰值/RMS、尾音、直流偏移与 SHA-256。

`Sound` 自动加载 `client/audio/sound_service.gd`，经独立音效总线播放，最多同时占用 8 个通道，超限时替换最早播放通道。总线带限幅器，每个音效另设节流时间；关闭声音会停止当前音效。混合伤害选择主要伤害类型的受击声，避免每个颜色同时叠播。

`client/state/game_store.gd` 从当前有效事件发出声音请求；首次快照、重连回放、连放预览、重复序号和旧战斗反馈保持静音。普通按钮自动绑定一次，卡牌选择与确认成功事件使用各自提示；`client/ui/audio_settings.gd` 提供设置入口。字体/音效许可和说明已列入 Windows 导出包含规则。

## 验证与证据

- Godot 原生脚本测试 14/14 通过，错误输出为空；其中 `test_bundled_fonts.gd` 包含 6 项字体加载、中文/符号覆盖、角色和等宽数字检查，`test_audio_events.gd` 覆盖预览、重连、重复、旧战斗和有效事件的声音过滤。证据：`artifacts/audio-font-validation/native-tests.json`。
- 字体静态核验覆盖当前 UI、目录与会话代码中的 796 个可打印字符，两字体均零缺字。证据：`client/assets/fonts/verification.json`。
- 22 段声音的格式、电平、削波、静音、尾音和直流偏移检查通过；相同制作环境重复生成，22 份 WAV、清单及试听串均逐字节一致。证据：`artifacts/audio-font-validation/sound_validation.json`、`sound_reproducibility.json`。
- 混音服务 16 项、设置界面 15 项、失效会话操作 9 项，共 **40/40** 检查通过；设置覆盖 1920×1080、1280×720、960×540，含弹窗内真实 F10 输入、音量/静音持久化和播放，保存 **6 张截图**。报告：`client/evidence/audio-fonts/report.json`。
- 新字体下的背包、升级、强化、PVP 与战斗功能预览 **78/78** 检查通过，保存 **34 张截图**；完整美术预览 **66 张截图** 的布局与文字可见性检查通过。分别见 `client/evidence/audio-fonts/gameplay-final/` 和 `client/evidence/audio-fonts/full-art-final/`。这些为离线测试数据，抽查卡牌、生命数字、强化收益和音效设置，并非逐张人工终审。
- 图鉴在 1920×1080、960×540 的最终离线预览通过，保存 **7 张截图**，包含文字实际可见行和选中卡牌检查；报告：`client/evidence/audio-fonts/codex-final/report.json`，运行日志 `artifacts/audio-font-validation/codex-final.log` 无错误。
- 隔离 HTTP 会话检查 **9/9** 通过；另对真实界面方法模拟卡牌升级、编组保存和购买的过期响应，以及编组保存后刷新时切换会话，验证不继续请求、不补播旧成功或错误声。证据：`artifacts/audio-font-validation/http-session.log` 与上述 40 项报告。
- 连续试听文件：`artifacts/audio-font-validation/sound_preview.wav`；`sound_preview_index.json` 标出每段起点和用途。

最终整套视觉一致性、实际发布包及不同设备的听感仍属于后续验收。本地加载和离线预览不等同于 Steam 正式发布验证。

## 复现

在仓库根目录导入资源并运行原生测试：

```powershell
python -X utf8 tools/client_engine.py import
python -X utf8 tools/client_engine.py test
```

使用 Godot 4.7.2 打开 `client/project.godot`，运行 `client/tests/audio_font_preview.tscn`，可复查音效设置及混音行为；该场景自动检查 1920×1080、1280×720、960×540 并写出报告。正常体验使用 `start-client.bat` 或 `python tools/client_engine.py play`。

需要重建音效时，按资源 README 的 Python/NumPy/SciPy 版本运行以下命令，将比较用副本写入验证目录：

```powershell
python -X utf8 tools/generate_game_audio.py --output artifacts/audio-font-validation/rebuilt --evidence artifacts/audio-font-validation/rebuilt-preview
```

字体使用原文件而非重制；更新时从 `client/assets/fonts/manifest.json` 所列官方版本取回，并核对哈希与许可。其他图片和效果图源文件待办继续以 [美术及配套资源清单](UI_MISSING_ASSETS.md) 为准。
