# D04 打造与配方具名事件

2026-11-06。三个具名事件子链路通过，整体仍30/35，D04未整体完成。

## 持久事实与幂等

craft_completed、recipe_learned、pity_triggered的原始观测保存在已有season_equipment_actions业务收据的可空telemetry_json。V054只追加观测列及对象类型约束；不另建经济账本或依赖内存日志。观测与扣款、物品、心愿和动作收据在同一原事务提交；原player/action/request唯一约束及原请求哈希继续控制重放。结构化导出事件ID为原action_id加事件名，查询及重放不会生成新事件。

标记打造记录实际原品质、印记支出、此前/之后失败数及当次Guaranteed。仅Guaranteed为true时输出pity_triggered，后续心愿改变不会重写历史。不能把偶然抽中心愿当作触发保底，也不能拿当前失败计数倒推旧事件。相关事件共享SourceActionId及同一动作事实；支付和实物数量须按源动作去重计算，不能把craft_completed与pity_triggered中的重复上下文相加。

重铸仍沿用原件ID，craft_completed的PhysicalFlow明确Mutation，不记新造或销毁。学习配方的PhysicalFlow为RetainedSample，保留本体；同模板已知请求保存空事件集合，不重复增加recipe_learned。三类动作均保留原业务响应及金额。

观测固定原季、规则、配置和属性版本。大厅操作没有实际对局难度/职业/构筑/成长和match参与者，相关维度明确NULL或Unknown，CellType为Lobby；可开放难度单独作为AvailabilityDifficultyId，绝不把realm.Context的D0或当前配装伪装成当次对局事实。统一维度仍有未覆盖项，不能据此称完整D04通过。

## 私有导出与未知历史

GET /api/admin/telemetry/crafting-events复用现有HTTPS、密钥、限流和private/no-store，不增加公开玩法JSON。只读RepeatableRead、五秒总截止/语句超时、七日UTC左闭右开窗口；按创建时间/action_id排序，最多1000条源动作、每条最多两个事件。超出明确SourceTruncated；单个观测超过64KiB或不可解析时计InvalidObservations，不任意导出巨大对象。

迁移前行继续NULL，不回填、不从当前心愿、装备或配装补造事实。NULL计MissingHistoricalActions；坏对象/版本/事件名或来源不一致计InvalidObservations，已有配方的合法空集合另计ObservedNoEventActions。CraftingSourceComplete仅指这三个打造事件的源窗口，不表示11事件、全部经济或维度完整。player/item/action ID只出现在受鉴权的结构化分析结果，meter继续只有固定查询结果标签。

## 实际验证

本机完整服务端及测试程序集编译通过，零警告/零错误；不是声称本机执行了PG。隔离PG与实际管理HTTP四项通过：

- 三次实际打造及每次同键并发重放只产生三个动作、四个稳定事件，其中一次保底精确2失败→0；原键新Repository重放、后来心愿变化后导出逐字一致。声明的旧NULL夹具仍未知且降低覆盖，不增加猜测事件。
- 两件同模板学习只有一次学习事件，已知样本未消耗资格；重铸实际沿用原ID、只扣原碎片，查询前后全资金/物品/心愿/动作/移动指纹不变。声明坏观测夹具单列缺口，不崩溃。
- 在自有schema动作INSERT触发点注入观测失败，实际印记扣款、装备、心愿、账本、移动和收据整体回滚；移除自有触发器后原键只成功一次。
- 一个完整Program实际检查缺密钥401、不安全转发403、合法200、禁止缓存和非法窗口400；不声称公网TLS握手或容量测试。启动实际应用全部迁移，含V054。

四个自有schema、测试容器、私有env及输入/上传tmpfs均已核实清理，共享自有PG保留。本机2GiB连续保留与1GiB启动预算、云端500MiB RAM和3GiB/5%磁盘保护不变，完整SFTP验SHA后同一worker执行；未启动云端SDK。原源代码、输入清单、TRX、HTTP/PG收据和资源记录见[结果](evidence/D04-crafting-events-r1/result.json)及[独立审计](evidence/D04-crafting-events-r1/d04-crafting-independent-audit-r1.derived.json)，大型原输入/传输流仍在G盘。

F02受影响的原交易/幂等/回滚范围已定向验证，不重跑旧全量正常结算。正式配置17、工作簿、UI及生产未变；九D03银行SHA不变，D03仍284/300余16、职业1.15不放宽；B05仍330/330不追加。没有新完整遭遇或100人测试。

D04其余八事件、战斗抽牌/控制/溢出、实物流转与人群/构筑/成长及市场活动诊断继续；D03/D04/E02/F01/F03未完成，完整目标保持进行中，未部署或重启生产。
