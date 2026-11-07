# D04 实物创建、归属、托管与归档

2026-11-06。本子链路通过，整体仍30/35，D04继续进行中。数量账聚焦装备唯一实例；币、魂、碎片、印记及活动章沿已有独立钱包／账本，不把装备件数混作货币或卡副本数量。

## 原始事实与数量

新增私有physical-equipment报表。每个equipments唯一instance_id及不可变创建时刻计一次Mint，原创建放置流水和红周配额收据定位原接收者/渠道；不读可能已交易的当前owner或已重铸改变的source_kind反推初铸者。缺创建渠道/接收者时保持Unknown，不能按当前owner补造。

后续inventory_movements按原reason/from/to严格识别放置、跨玩家转移、上架/返还托管、准备锁定/入场、遗物与撤离托管、穿戴、重铸、销毁和归档。初始放置不再加一次Mint；MatchReward直接Recycled可以同时对应一次原创建及一次销毁，净件数为0。重铸沿用原件，学习保留本体，均不新造/销毁。满仓退回MarketReturnPending是托管迁移，不是释放或销毁；已回收物归档仍是域移动，不重复销毁。

V055仅追加可空from_owner_id/to_owner_id，原各事务在已知原owner处写入前后两方；市场购买保存seller→buyer，准备/入场/穿戴/归档保留self→self，创建为NULL→接收者。没有更改价格、付款、状态转换、锁顺序或幂等键，旧行继续NULL。旧市场可由不可变交易/原listing验证双方；其它缺失不按当前owner猜对手。实物转移只计一次，不复制买卖两份件数。

已知生命周期集合按原创建时间和首次明确不可逆销毁时刻计算Opening＋Created−Destroyed＝Closing。重复销毁声明单列，数量取首次；没有销毁时间的旧终态和状态/时间不一致单列，不凭当前位置补历史时间。KnownSubsetBalanced只说明该已知集合可对账，不证明来源覆盖完整或经济健康。CurrentStocks为查询时原季/域/品质/位置库存，不冒充历史期初余额，转移和托管不改变系统总件数。

## 原hold与归档域

reward.recycle只通过原request_id的hold UUID连接已Committed的Equipment hold，同时核对item/player/季域/难度/三版本，再取原settlement收据的职业、构筑和成长。错误item或上下文不能借用某个真实hold的档案，不读取当前账号配装补值。

season_asset_archived新增原wallet.archived_at及原状态域下Recipe/CraftingWish、实际引用本季装备的SavedLoadout标记。原季版本和引用保留，装备仍由逐件归档记录负责。钱包标记不含归档金额快照；查询时余额可因合法旧季晚到账改变，不能把这个新值倒填到旧归档时刻。配方/心愿仅在学习/更新不晚于原归档时刻时定位该域标记，空配装不虚构归档记录。非实物标记不混入装备件数。

## 有界只读与验证

所有报表沿用管理HTTPS/密钥/限流及private/no-store，RepeatableRead只读、5秒截止/语句超时、7日UTC左闭右开窗口及每源/组1000上限；截断、未知渠道/流水/双方和生命周期缺口显式返回。IDs只用于结构化管理员分析，未新增高基数指标标签或公开玩法字段。

26项服务端分类/通用投影检查通过。首轮仅CA1869测试选项分配分析器编译失败、0执行，改为复用静态JsonSerializerOptions；原日志/源码保留。归档夹具按实际契约保存一套引用本季装备的配装，不要求三套空配装产生标记。Domain源码和旧Domain证据逐SHA保持，未重复运行已通过Domain或旧战斗矩阵。

六项真实隔离PG/管理HTTP通过：真实打造→学习→同件重铸→两次上架/取消/购买→丢弃/重放仅1铸造/1销毁/1转移、2进/2出托管，初铸者仍是原卖家而非当前买家，原渠道仍是craft而非TemplateReforge；原Committed hold按完整身份关联构筑，别件不能借用；缺终态时间和重复销毁保持缺口而不增加供给；钱包/配方/心愿/实际配装归档标记不因晚到账7金改变；真实准备取消释放及匹配入场写出self所有权腿；完整Program验证新增私有入口401/403/200和禁止缓存。查询前后资金、实物、移动、holds、收据及配方指纹保持。

这些是声明的资产/事务边界夹具，不是新的完整B05路线、原生容量或真人体验；无成功玩家施法及游戏平衡新增场次。六个自有schema、测试容器、私有env、输入/上传tmpfs均已清理，原共享PG及约11MiB只读第三方缓存保留。122依赖物化前后验SHA，任务程序集全新；本机2GiB连续保留＋原1GiB启动/三点准入、云端500MiB RAM和3GiB/5%磁盘保护不变，未启动云端SDK。

证据见[结果](evidence/D04-physical-flow-r1/result.json)、[独立核对](evidence/D04-physical-flow-r1/d04-physical-independent-audit-r1.derived.json)与[source manifest](evidence/D04-physical-flow-r1/source-manifest.json)；原可选Kerberos诊断、失败和G盘大型输入/程序集/传输流继续保留。

正式配置17、工作簿、UI、九条D03资金银行与全部原失败保持。B05仍330/330不追加，D03仍284/300余16、职业1.15不放宽；不补100人、已验全量UI或旧正常结算矩阵，未部署重启生产。

D04仍需分人群、市场深度/48小时成交、零余额、商店挤占、活动峰值和红全程履历诊断及当前版本综合遥测要求核查。当前不提前通过D04；剩D03/D04/E02/F01/F03，完整目标继续。
