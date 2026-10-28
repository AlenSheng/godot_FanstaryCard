# LOAD-05.3-T02：实际 ACK 在途取消

当前真实网络的两个场景通过：ACK 请求已到达本地透明代理、尚未转发后台时收到 STOP；后台已真实提交并返回 200、原响应尚未送达客户端时收到 STOP。两个场景都执行原完整 `_run`、真实准备／排队／READY／合法放弃／结算／ACK／收尾，STOP 文件由原 `_process` 读取，没有赋值 Game 世界、恢复标识或 stop 标记。

STOP 当时，原客户端均 busy、待确认结算 ID 非空、尚未得到 HTTP 结果、周期完成数为 0。因此客户端当时的操作结果仍需等待权威返回；“unknown”是对真实观测的推论，不冒充协议枚举。独立 PostgreSQL 快照分别证明提交前 ACK 为 0、提交后 ACK 为 1；最终均为 1。实际线上请求键、玩家、对局和结算 ID 与持久 ACK 逐项一致，后台原始 200 响应哈希与实际交付客户端响应哈希一致。

每个自有账户明确置入一个初始 White Feet 0 级装备，再通过实际 Bootstrap、准备快照和房间资格进入。实际合法死亡使装备成为 RelicPile；Equipped→PreparationLocked→InMatchEquipped→RelicPile 共三次真实移动。STOP 时与最终的装备、移动记录完全相同，没有 ACK 导致的重复资产移动。这个夹具不宣称自然游戏完成或战斗平衡。

实际进程 73228、45672 均 exit 0，原报告 outcome=cancelled、ok=false、cycles_completed=0，全部原始检查通过、cleanup=Passed、审计无丢失。ACK 确认后内部 scenario_finished=true 合法，但外层见 STOP 后没有生成 cycle.completed，不能计为完成对局。两场实际对局、保守八次玩家入房；LOAD-05.3 累计 2/8 场，用户单项 300 场上限不变。

R4 保留失败：驱动错误导入旧通用代理，新的 arm 控制端点返回 unknown_control，进程 118564 exit 1，未进入准备／排队或对局，初始装备仍 Equipped。R5 仅修正 Python 驱动导入及模块检查；2127 个游戏输入与三个原生探针字节和 R4 完全一致。本地两个实际 HTTP 控制端点先通过，再运行唯一实际 R5。首次 R5 本地准备断言、首次独立审查把无请求键的 PG 事件过滤掉的观察器错误，也均保留；修正精确关联后没有重跑游戏或放宽条件。

独立审查与复制校验 251 项通过，206 个原件成员已在 G 盘逐项复核哈希。R4/R5 自有容器、网络、私有环境全部清理，生产身份及健康保持一致。5% 安全余量满足；磁盘仍约 14.2%，原 15% 容量门仍未通过。本次无游戏源码上传、服务器重建、部署或新源码提交。

报告仅为 S4 补充，register、MAIN 和 gates 未改变，55 Accepted／67 Partial／10 ReadyForAcceptance，77 项仍未验收。LOAD-05.3 仍 Partial，T03 的真实 Pending holds、恢复标识和其他等待点范围还需完成。原件：`G:\PR13Evidence\load053-ACK-inflight-cancel-LIVE-PG-20261017-originals-r2`。前一份入房前取消报告与本份一起使用，不能以两次 ACK 成功推断整项通过。
