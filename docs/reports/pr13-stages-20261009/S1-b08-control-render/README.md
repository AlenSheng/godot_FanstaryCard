# S1 实际输入与显示缺口

B08.1 原生 54000 行/486000 次事件已通过，12 个原始/元数据文件全部本地备份。当前登记表 S6-after-b08-control 的三条检查仅缺 RENDER；不能用原生计时或离线预测补齐实际绘制。

main.gd._set_battle_status_label 当前直接拼接“眩晕、禁抽、抽速、充能”，未使用已启用语言。MonsterStatus/PlayerStatus/OpponentStatus 为当前真实界面字段，原始权威怪物 StunRemaining、PVP 对手状态和返回的 PVE 怪物状态均可映射现有快照字段，无需新增协议或界面别名。

各显示状态按原 RoomStateSha256 从保存的 JSON 原文恢复，保留 battle、target、职业、等级和事件标签。三个 case 的原生窗口和冻结断言仍保持原始来源；本轮只证明该状态在当前客户端显示正确且不产生额外控制或收益。
