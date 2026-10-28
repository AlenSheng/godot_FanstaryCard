# 当前终局故障矩阵：坏主JSON、exit7与所属进程hang

LOAD-07.4完成当前三项LIVE及全部相关OFFLINE范围MAIN复核。上游LOAD-07.2/07.3已Accepted，当前53项独立不变量通过；原代码曾漏判主JSON的实际失败保留。MAIN本项Accepted，51→52Accepted，69Partial/11Ready，80项待验收。全部全局门保持，故障运行不变成容量通过。

由于新增有界分段、audit_storage和收尾磁盘暂存会改变当前终局路径，本次没有只引用旧已通过LIVE；用完整2126当前客户端、明示2份继承覆盖、真实当前Python协调器、完整Program缓存/新私有PG，实际再跑3个新合成客户端及1个无网络外部哨兵。每轮最多1客户端/24秒，原35秒收尾宽限保持，3/4含诊断上限及goal300未改。三轮协调器均exit3，正常完成周期0、房间/成员/结算/ACK0。

T01：实际STOP与业务清理后，原负载驱动_finish/_write_status已写完整当前审计与合法主/状态，继承覆盖保留before-fault原字节，再仅把主终局改成7字节“{broken”。真实最终status仍合法且含当前audit_storage，50条完整审计没有丢失。当前协调器独立读取主文件得到JSONDecodeError/native_final_read_failed，evidence=Failed、exit3，原生正常退出0、cleanup=Passed。合法状态无法修复损坏主文件，原生before-fault又由当前读者单独验证合法，不能把对原副本的验证说成接受坏主报告。

T02：实际STOP、清理、完整当前主/状态/50条审计之后，原生真实退出7，未模拟returncode。协调器before_stop=None、after_stop=7，post_stop_failure，execution/cleanup=Failed、exit3，未强退；证据本身合法，所以evidence=Passed。业务清理Passed与进程清理Failed分别保留，不能以数据库无占用抹掉真实exit7。

T03：相同实际STOP/清理/写完当前主与status/50条审计后，只有登记的原生PID99456主线程阻塞。原stop_all在真实35.219秒后执行唯一taskkill /PID 99456 /T /F，强退列表也仅该PID，进程清理Failed、exit3。PID78032哨兵未登记到协调器、无网络，当时实际仍活；随后只通过自己的STOP文件正常退出0。没有按进程名/窗口/全部Godot杀进程，没有触及其他PID，也没有放宽原35秒安全时限。

**所有原失败维度原样保留。** 三轮容量运行都未通过；T02/T03的cleanupFailed不是测试基础设施清理成功就可改成Passed。用户资产层面由独立只读PG确认：3个实际新owner UUID各一份Cancelled准备/票据，活动准备/成员0、holds0、装备锁0、成员/结算/ACK0。原始坏JSON、before-fault、正常最终status和单进程命令/哨兵存活/退出原件全部保存。原R1实际漏判坏JSON（evidence错误Passed、整体因时长不足exit1）仍是Failed，不因本轮正确检测变成Passed；旧142份原件逐SHA复核并保留。

OFFLINE先前当前159项通过；整体补看停止/监控套件时，11项中四个旧方法只模拟read_text、并未创建文件，新8MiB前置stat因此先取FileNotFound分支，产生5个失败（含坏编码子例）。原日志与源保留。修正只让四个夹具在唯一TemporaryDirectory真实创建小状态文件，仍保留原PermissionError重试3次/一次睡眠、坏JSON/坏UTF8不重试、外来归属拒绝、缓存接收时刻和旧心跳不续命等全部原断言；产品源码未改。最终完整170项实际通过，包含状态缺口、监控失败保持unknown不补0、真实所属子进程回收、主报告边界、暂存故障及全部先前159项。不是删除/禁用失败测试，也不把旧失败改写；11套单元数据为离线受控输入，不声称真实网络或负载。

本轮3份主/状态由当前独立读者再核对，before-fault全部合法；T01实际主文件单独拒绝。当前分段读者重读3×50条原生事件，归属/全序号/水位/字节对齐，audit_storage与状态一致、loss0和尾部缓冲0；Root默认新archive依赖也进入实际provenance SHA。加载/session/玩法/HP/接口/GUI/美术均无生产改动，合法80/70仍保留。只改了4个旧OFFLINE夹具的实际文件前提，控制场景只注入此进程的终局文件/退出/阻塞；60FPS为明示headless测试参数，不作硬件渲染结论。

资源监控是同一物理云机真实HOST CPU/内存/磁盘，私有应用队列/人数保持缺失，没有借生产应用数值。原15%磁盘检查全轮保留，实际约14.16%仍不通过，24秒短运行没有声称达到原容量门；本项没有新阈值/时长/宽限/正确性放宽。私有服务/PG仍按goal5%资源余量保护，512/384MiB、PG临时256MiB/max_connections25、Auth/写/读100/200/500仅测试余量，OTel仅私有关闭，无主机端口。完整328当前源及21实际运行库前后SHA冻结，使用原完整Program，不重建、不stub，游戏源码上传0。

执行前已披露共享云环境模板仍带旧任务未消费的计划估计5账号/1四人match；实际生效的是task_plan和本地冻结计划3账号/最多4、三个规范故障，runner按实际3个UUID核验，未在调度后修改已冻结云输入。不能把旧模板估计当本次实际发生量。最终3个原生/3协调器/外部哨兵/桥接/解析与回归进程均已结束，所属两个容器、网络、私密env被删并再次只读核对；生产容器ID/镜像/启动时间/环境摘要及健康200未变。token、私密env和userdata不复制。

G盘保存全部当前和旧失败、170回归、坏JSON及副本、实际命令与时间、22云原件/SQL/清理、当前源码和完整2126基础ZIP/当前覆盖ZIP；原328+21运行原字节独立保留。逐SHA与ZIP CRC核验，硬链接只避免同卷重复存储，不改原件。没有新增自然、容量、性能、真人或RENDER结论。后续转向其他未验收任务，132任务/396规范案例范围保持。
