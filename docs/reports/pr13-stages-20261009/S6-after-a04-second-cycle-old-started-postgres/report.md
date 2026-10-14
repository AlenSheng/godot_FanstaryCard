核查第一局真实进入、合法放弃、确认 ACK 完成及第二局同一玩家进入不同房间，投递第一局原始 started 二进制包两次后，当前 room/match、ready、提示、尝试/成功/发送次数和周期计数不变。原装备按死亡规则落入 RelicPile，只有一次锁定及一次死亡流水，未补造装备或修复账。补齐 PR13-A04.2-T03 的 POSTGRES 层。

A04.2 的三个 POSTGRES 层已齐，三个 LIVE 层仍缺，整项仍为 Partial。数据库缺失项 84→83，总缺失验收项 387→386；正常 ready 基线不另算新增用例，第二局 STOP 清理也不算完整正常周期。14 Accepted、28 ReadyForAcceptance、88 Partial、2 Failed 和各 gate 不变。用户的真人除外、容量/失败暂缓及千级采样十倍减量决定继续有效。未授予整项或整体验收。
