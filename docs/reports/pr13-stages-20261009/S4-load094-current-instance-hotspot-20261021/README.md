# 实例热点裁决及实际回退验收通过

LOAD-09.4三个案例的九个必需profile支持完整，本轮补五个缺口，保留已有四个支持。规范依赖为LOAD-06.3、LOAD-07.4，均Accepted；此前续跑记录把LOAD093称为依赖不准确，以规范为准。本项通过表示诊断、候选限制和回退流程通过，候选本身没有收益通过或上线授权。

云端当前Server8eb／Domainc825，实际PG18.6 UTF8独立数据库经现有身份、初始化、准备、匹配、ready认领和CreateRoom产生六个真实四人匹配。SQL独立计数为24玩家／24准备／24成员／6match／6checkpoint，非随机GUID模拟。每个Actor关闭自然ticker，排队24条真实1ms Advance命令，实际最大在途执行1、顺序1–24、权威时间24ms；完整快照持久化再读一致。

三轮AB、BA、AB配对，种子763001／763101／763201，各对角色、装备、卡组、指令及状态负载相同，SQL响应和序列化字节数实际相同，六组规范化EXPLAIN计划一致。参考池min0，候选仅min4及显式预热4，最大连接数都4，没有提高并发／CPU／内存上限。每组确实持有四个不同物理后端连接，200ms后释放，实际调用当前RuntimeTiming.OpenConnectionAsync及ExecuteReaderAsync读取源代码相同的checkpoint SQL；候选预热不能绕过被占满的连接槽。

第1对 209.2290→205.9383 ms（差-3.2907）；第2对 206.3488→204.5916 ms（差-1.7572）；第3对 205.1285→205.0812 ms（差-0.0473）。六组实际DatabaseAcquire约200–204ms，远大于SQL执行阶段；当前hotspot_target_review对DB路径只给EligibleForDiagnostics，对未定位Actor路径给Blocked，未对Actor加并行。三轮改善均低于预先固定的10ms诊断收益门槛，返回NoChangeWithEvidence，保留默认min0/max4与不确定性。这不是SLO门槛、统计等效或生产热点已优化；三个受控单机配对不能推断线上容量、WAN、真实请求总体收益。没有把per-stage改善代替全部终态请求耗时。

每组候选DataSource真实Dispose后重新创建默认池，用相同数据库行读回之前快照、Restore实际BattleRoom、创建新Actor继续第25条命令，顺序1–25／最大执行1／时间25ms保持；再次真实写入读取一致，SQL最终revision与原件匹配。六组都执行这一回退，未删行、未改生产DDL，也未通过缓存跳过实际写入。DB只另设测试私有20匹配预算trigger，产品迁移源码未变。

原件包含当前Server／Npgsql Activity链路、命名DatabaseAcquire／SqlExecution跨度、实际process CPU／RSS、GC代数／分配／heap、cgroup CPU及内存前后窗口、host每核jiffies、SQL计划、序列化字节及私有Stopwatch耗时。每核数据是主机背景，不能冒作进程每核归因；序列化耗时是明确的测试测量，不冒作现有Server RuntimePhase。没有凭整机平均加资源。各组driver CPU1／内存512m、PG CPU.5／内存256m与连接上限固定。

首轮失败完整保留：仓库自己的GetAsync完整快照比较已通过，但测试手写SQL反序列化遗漏仓库实际camelCase策略，出现比对失败；该轮实际1匹配／1Actor／24命令、native139、OOMfalse、SQL行和PG转储都留存。私有观察器改为读取实际仓库SerializerOptions，并在本地用该轮真实完整快照完成同策略roundtrip校验，业务数据、JSON schema和验收要求没有改。之后新环境执行三对成功实验，native0；不称首轮失败为产品问题，不抹失败或重跑已完成三对。本轮累计7／20匹配、13／80Actor状态、174／300命令，其他历史预算保持。

本地仅无窗口低优先级私有编译／数据校验，Godot0、PG0、Socket0，不抢焦点。本轮实际PG测试都在云端网络none的新容器，driver只共享该PG私有namespace，无host端口／生产volume。源码先本地编译及验证，上传包先G SHA托管。两轮测试容器移除前保存PG dump；失败R1共873成员、成功R2共901成员含714源／配置在G全SHA／CRC核验后，按owner、sourcehash、unit PID0/inactive及容器不存在校验精确清理临时源码。云端raw、本地代码、G原件全部保留，生产ID／镜像／启动时刻／环境hash及health200保持。5%磁盘／500MB内存是功能实验底线，未作为容量15%门通过。

GDD两卷保持固定，合法80/70与基础L盾未被当异常或钳制，无玩法、UI或美术资源变更。Git提交／推送／部署均无。本项MAIN通过后88 Accepted／36 Partial／8 Ready，44项未验收、175个case/profile缺口；其他131项和全部全局门保持，整体仍未通过。

原件：G:\PR13Evidence\load094-current-instance-hotspot-20261021-originals；失败原件：G:\PR13Evidence\load094-r1-observer-JSON-failure-20261021-originals。
