# D04 难度、销毁与装备归档事件

2026-11-06。现有持久来源的三个事件子链路通过，整体仍30/35，D04继续进行中。本批只新增只读投影和私有导出，不改业务事务、规则、配置或数据库结构。

## 原始来源与边界

`difficulty_cleared`来自season_difficulty_completions，稳定ID使用原settlement_id和事件名。原行含赛季、实际难度和三版本；职业来自原结算详情，真人/机器人来自原match_players，不能读今天的账号职业或最高开放难度。该事件为成功撤离的RunSummary，EliteCleared/BossCleared保留原布尔证明；不是每个战斗清格事件。死亡不生成该源行，重复结算不增加一次完成；未知构筑/成长继续为NULL。

`item_destroyed`来自inventory_movements的明确终态转换。只把Inventory→Recycled的equipment.discard、Inventory→EnhanceMaterialConsumed的equipment.enhance，和MatchReward/房间背包/穿戴/RelicPile→Recycled的reward.recycle识别为销毁。未知理由、非法转换或缺物品身份单列UnclassifiedRows，不凭目标位置猜成已知事件。强化目标升级不销毁目标，只计真实材料；重铸不在此清单。大厅原流水D0是占位，导出难度明确NULL，不伪装实际参战D0。

`season_asset_archived`本阶段仅覆盖season_archive_items中的逐件装备归档。稳定ID为原job_id、item_id和事件名；版本来自不可变的原发布赛季定义，身份和品质来自保留的装备记录。原项目没有运行时改变同一装备品质的路径，品质不是从当前账号职业/穿戴推导。生成难度不冒充归档动作难度。已回收/已消耗物品归档可能Recycled→Recycled，仍只计Archive域移动，不再算一次销毁或新造。

三个来源按自己的原发生时间过滤，不能将大厅流水的系统UTC时间、原结算时间和归档时钟混为一个伪窗口。历史季域、规则、版本和品质缺失明确计覆盖缺口，不从当前季补造。BuildType/GrowthStage及无实际match的人群继续未知，另列EventsWithUnknownCombatDimensions；SourcesComplete只表示所选三来源窗口，不表示全部维度、11事件或经济健康完整。

## 有界私有导出

新增GET /api/admin/telemetry/lifecycle-events，继承现有HTTPS、管理密钥、速率限制和private/no-store。七日左闭右开UTC窗口、五秒总截止/SQL超时、RepeatableRead只读事务；每源最多1000行，截断明确返回。事件中ID仅供受鉴权结构化分析，不进入Prometheus标签。

三个来源都使用已有唯一业务身份，不因重复查询新造事件。PhysicalFlows按季、品质、配置及Destroy/Archive分组；没有把成功难度事件当物品，也没有把同件物品的域移动和销毁相加为系统净投放。本阶段不覆盖系统铸造、玩家转移和托管完整实物账，不能称完整实物守恒。

## 实际验证与保留失败

首轮测试夹具用with赋值只读ConfigVersion，CS0200编译失败、0用例执行；改用新SeasonDefinition构造冲突定义。原源码/日志保留。第二轮完整服务端及测试程序集编译零警告/零错误。隔离PG与实际HTTP四项通过：

- 实际丢弃同键并发、真实+4材料消耗和原键新Repository重放只产生两个销毁事件，目标仍在；大厅D0占位不作为实战难度。另声明旧NULL域及未知理由夹具，分别保留缺口且不判整体来源完整。
- 实际两页归档并重建Repository/重放，两个稳定装备身份各归档一次，原季版本正确；此前已丢弃物品仍保留Recycled，统计中没有第二次销毁。发布同季不同版本被原不可变约束拒绝。
- 明确的终态检查点夹具经原SettlementCoordinator/Repository产生原难度完成收据；一次撤离、一次死亡和撤离重放最终只一个D0/Mage/Human完成。窗口右端事件排除。0施法、0完整游戏遭遇，不计新增B05/D03/D02场次，也不冒充重跑正常结算矩阵。
- 一个完整Program实际验证新增路由401/403/200、私有禁止缓存及非法窗口400；不是公网TLS握手或容量测试。

所有查询前后原资金/物品/移动/结算/难度/归档指纹一致。四个自有schema、测试容器、私有env、输入和上传tmpfs均已清理，共享自有PG保留；本机2GiB连续保留加原1GiB启动/三点准入、云端500MiB RAM与3GiB/5%保护不变。原可选Kerberos库诊断保留，未在云端安装SDK。详见[结果](evidence/D04-lifecycle-events-r1/result.json)、[独立核对](evidence/D04-lifecycle-events-r1/d04-lifecycle-independent-audit-r1.derived.json)和源码/输入清单，大型原输入和传输流仍在G盘证据根。

## 接续

本批无新的资产写入路径、迁移、客户端或UI变更。公共维度类型只放宽历史缺失字段的C#可空注解，已验打造观测的序列化字段和运行时签名不变。正式配置17、工作簿、九条D03资金银行及历史失败保持；D03仍284/300余16、职业1.15不放宽，B05仍330/330不追加。没有100人或旧全量UI补测，没有部署或重启生产。

D04仍需战斗完成及掉落生成/选择/带出/丢失的五类原始事件、完整维度、钱包/配方等归档及铸造/转移/托管全实物流、抽牌/控制/溢出明细和人群/市场/活动诊断。E02当前证据依赖已另核对，未据此提前验收；D03/D04/E02/F01/F03继续，完整目标未完成。
