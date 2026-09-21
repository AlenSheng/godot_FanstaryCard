# 音频扩展交付记录

日期：2026-09-20。

本次在既有“羊皮纸、深青石、克制黄铜、五行材质”的短音效基础上，接入了
外部生成的模块 BGM、登录视频、房间环境底床，以及战斗双方的动作与受击层。

## 资源

`tools/generate_game_audio.py` 负责短音效与环境音的固定种子 PCM16 WAV 生成；模块 BGM 与登录视频来自 `art/BGM`：

- 33 个短音效：模块打开/切换/确认/取消，战斗开始/选目标，我方出招/受击，怪物攻击/受击，战斗胜利，以及既有卡牌、五行、经济、探索、结算提示。
- `Crown_of_Blackened_Glass.mp3`：大厅 BGM。
- `Throne_of_Obsidian.mp3`：普通战斗 BGM。
- `Throne_of_the_Sentinel.mp3`：Boss 战斗 BGM。
- `The_Gilded_Hourglass.mp3`：商店 BGM。
- `Legendary_Gambit.mp3`：战斗胜利 BGM。
- `Ink_and_Parchment.mp3`：战斗失败 BGM。
- `Cinematic_fantasy_login_screen.mp4`：登录页视频，包含视频音轨；Godot 运行资源转换为 OGV。
- `ambience_hall.wav`：24 秒营地空气与远处石材动静。
- `ambience_battle.wav`：24 秒低混合战斗洞窟风与石材共鸣。

短音效与环境音写入 `client/assets/audio/manifest.json`，并由生成器执行格式、峰值、RMS、削波、直流偏移和循环资源检查。外部 BGM / 视频的授权信息以资源提供方为准；本项目不将它们声明为 `LICENSE.txt` 中的 CC0 资源。

## 运行时接入

`client/audio/sound_service.gd` 现在维护三条总线：SFX、Music、Ambience。SFX 使用 10 个有界通道；BGM 和环境音各使用双播放器交叉淡入淡出。根据当前 UI 模块与 `Game.room.player.phase` 自动选择：

- 登录页：使用登录视频自带音轨，不额外叠加 BGM。
- 大厅使用 `Crown_of_Blackened_Glass`；商店/市场使用 `The_Gilded_Hourglass`。
- 普通 `Pve` / `Pvp` 使用 `Throne_of_Obsidian`，检测到 Boss 使用 `Throne_of_the_Sentinel`，并继续叠加战斗环境音。
- 战斗胜利切换 `Legendary_Gambit`，战斗失败切换 `Ink_and_Parchment`。
- 认证失效：停止三类播放。

设置面板保存三路音量，`F10` 仍为全局静音。既有 `user://audio_settings.cfg` 字段保持兼容，新增 `music_volume` 和 `ambience_volume`。

## 战斗事件映射

服务端确认的 `battle.combo_resolved` / `combat.hit` 继续经过当前房间、序号、重连和预览过滤，然后按 `attacker_id` 与 `target_id` 分层：

- 我方攻击：`player_attack`，目标受击：`monster_hit`，再播放最大伤害段对应的五行/直伤音。
- 怪物或对手攻击：`monster_attack`，我方受击：`player_hit`，再播放最大伤害段对应的五行/直伤音。
- 进入新 `Pve` / `Pvp` 战斗：`battle_start`。
- 目标选择成功：`battle_target`。

因此预览、重复事件、旧战斗、重连回放和失效请求不会补播动作音；已有的卡牌、治疗、护盾、奖励、撤离和死亡提示保持原有规则。

## 验证

```powershell
python -X utf8 tools/generate_game_audio.py
python tools/client_engine.py validate
python tools/client_engine.py test
```

音频单元检查覆盖资源数量、循环上下文、三路总线、10 通道上限、静音/音量持久化，以及我方/怪物战斗事件路由。
