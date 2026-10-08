# PR13 执行与验收登记

这是运行记录；原有规范文件保持原义。尚未完成全部验收。

集成源码：`562065de8fef449b1d5927b30c3263017276f9f0`。132 子项、396 用例；逐用例已通过 363 个。

已通过的独立测试和模拟作为支持材料列出；未逐用例执行的细则仍保留待执行。ReadyForAcceptance 尚需 MAIN 检查完整判据、依赖和适用 CI。

候选数值开关仍为关闭。发布去向和授权由本次 support.delivery_policy 记录；真人体验状态由 support.human_experience_decision 记录，不从历史模板推断。

| 子项 | 状态 | 已通过用例 | 后续动作 |
| --- | --- | ---: | --- |
| LOAD-01.1 输入schema | Accepted | 3/3 | 本子项适用层已裁决；全范围门槛另行汇总。 |
| LOAD-01.2 唯一进程归属 | Accepted | 3/3 | 本子项适用层已裁决；全范围门槛另行汇总。 |
| LOAD-01.3 拆分负载人数 | Accepted | 3/3 | 本子项适用层已裁决；全范围门槛另行汇总。 |
| LOAD-01.4 真实进程反例 | Accepted | 3/3 | 本子项适用层已裁决；全范围门槛另行汇总。 |
| LOAD-02.1 多维结果模型 | Partial | 3/3 | 独立生成六维判定，保存首个和全部触发；exit0只由适用合同全满足推出 |
| LOAD-02.2 STOP前后边界 | Accepted | 3/3 | 本子项适用层已裁决；全范围门槛另行汇总。 |
| LOAD-02.3 有界清理和应急报告 | Partial | 2/3 | 排队取消/结算保留/关闭连接/回收进程分步；最终报告写失败产出独立应急摘要 |
| LOAD-02.4 退出码兼容 | Partial | 3/3 | 固定0/1/2/3/130及preparation-only语义，调用者读取六维结果而非只读0 |
| LOAD-03.1 事件水位 | Accepted | 3/3 | 本子项适用层已裁决；全范围门槛另行汇总。 |
| LOAD-03.2 生命周期阶段 | Accepted | 3/3 | 本子项适用层已裁决；全范围门槛另行汇总。 |
| LOAD-03.3 请求完整分母 | Accepted | 3/3 | 本子项适用层已裁决；全范围门槛另行汇总。 |
| LOAD-03.4 分布与错误率 | Accepted | 3/3 | 本子项适用层已裁决；全范围门槛另行汇总。 |
| LOAD-04.1 当前匹配状态机 | Partial | 3/3 | 定义Queued至RoomStarted及取消/超时终态，权威ticket校验后才确认当前match |
| LOAD-04.2 有界ready发送 | Partial | 3/3 | send=false不认成功；次数/截止双界；accepted后迟到required不回退 |
| LOAD-04.3 缺通知/started恢复 | Partial | 3/3 | 通知丢失也启动有界权威查询；分别测queue/ready/start等待，不清全局WS游标 |
| LOAD-04.4 ready全矩阵 | Partial | 3/3 | 组合重复/乱序/丢失/send失败/断连/STOP/旧局事件；记录预期终态与票据后置状态 |
| LOAD-05.1 服务端ack完成依据 | Partial | 3/3 | 返回成功/拒绝/忙/过期会话/结果未知类型，只有同match真实ack成功才计completed |
| LOAD-05.2 跨局状态隔离 | Partial | 3/3 | 成功清局部ready/ticket/选牌/pending/poll；迟到HTTP/WS核验发起epoch，失败原状态可恢复 |
| LOAD-05.3 各await取消 | Partial | 2/3 | 登录/排队/进房/战斗/结算/ack所有等待点有取消；业务回收独立于进程退出 |
| LOAD-05.4 幂等三局矩阵 | Partial | 3/3 | 测ack响应丢失/重复receipt/旧snapshot/重启/重连；对每cutoff核对cycle与资产 |
| LOAD-06.1 HTTP不可变上下文 | Partial | 3/3 | 冻结origin/session/cycle/phase/trace；记录每attempt、decode、backoff、body、总等待与pending终态 |
| LOAD-06.2 生命周期/玩法进度 | Partial | 3/3 | 分transport_progress与gameplay_progress，记录prepare至ack及命令确认、有效状态变化 |
| LOAD-06.3 服务端分段 | Partial | 3/3 | 测本机连接获取/执行/锁等待、launch各段、command排队执行发送；无法可靠测量写null |
| LOAD-06.4 时间/缺失/脱敏 | Partial | 3/3 | 冻结单位/基数/缺失原因/版本；UTC只关联，不跨机相减伪造DNS/TLS/单向延迟 |
| LOAD-07.1 有界探测调度 | Partial | 3/3 | 分离健康/Prometheus探测，记录schedule/actual/lag，超时future不无界堆积 |
| LOAD-07.2 实际发压与资源 | Partial | 3/3 | 总/每进程CPU/RSS/可用内存/可得句柄与发包率；不可得值带原因，FPS候选单独profile |
| LOAD-07.3 有界JSONL与session隔离 | Partial | 3/3 | 批写/flush/轮转记录序号；会话隔离在autoload读取前；原子替换缺口仅用有界新鲜缓存 |
| LOAD-07.4 发压器故障矩阵 | Partial | 3/3 | 注入慢磁盘、坏JSON、单进程hang、信号、STOP与监控失败；记录停止后最终错误 |
| LOAD-08.1 TLS连接复用边界 | Partial | 3/3 | 复用顺序连接，重叠请求走兼容fallback；验证完整body而非简单Connected状态 |
| LOAD-08.2 GET单飞一致性 | Partial | 3/3 | 合并同一只读请求并共享真实结果；写后新版本隔离旧响应；先量化重复读取 |
| LOAD-08.3 有界去同步重试 | Partial | 3/3 | 抖动在最小等待之后、受总deadline/取消约束；不重放解码失败/跨会话不确定写入 |
| LOAD-08.4 结算轻量查询 | Partial | 3/3 | 有ID优先单项，无ID经协议评审最小只读入口；保留旧fallback/鉴权/match/holds边界 |
| LOAD-09.1 enqueue回放关联 | Partial | 3/3 | 固定回放ticket与其preparation/match关联，与GetTicket一致，保留玩家锁/冲突 |
| LOAD-09.2 launch与旧路由恢复 | Partial | 3/3 | 注入snapshot保存/registry/MarkRunning失败；释放终态玩家路由只删仍指旧room者 |
| LOAD-09.3 慢连接隔离候选 | Partial | 3/3 | 先测队头阻塞；必要时同match内有界投递且每玩家序列仍保序 |
| LOAD-09.4 实例级热点裁决 | Partial | 1/3 | 逐热点最小候选，固定SQL计划与资源限额；不凭整机平均加资源 |
| LOAD-10.1 独立离线/协议套件 | Partial | 3/3 | 非实现作者视角重跑统计/真实进程/exit/schema兼容，新增文件纳入CI触发 |
| LOAD-10.2 真实同账号三局 | Partial | 3/3 | 各职业单账号连续至少三局，再10账号各三局；明确正常/兜底/清理完成 |
| LOAD-10.3 全链路故障用例 | Partial | 1/3 | 逐用例冻结注入点、预期终态、DB/route后置条件，再在集成SHA运行 |
| LOAD-10.4 同负载性能与保持 | Partial | 2/3 | 单→10→50→100，三轮交错配对，保持期按覆盖率与实际请求率验收 |
| LOAD-11.1 基线来源冻结 | Partial | 3/3 | 分开source checkout、CI checkout、实际运行镜像digest、部署marker、有效配置hash；保存差异 |
| LOAD-11.2 全量manifest脱敏 | Partial | 3/3 | 记录字节hash、种子/flags/硬件/region/selector，私密原始资料只保存在授权artifact |
| LOAD-11.3 可重复CI覆盖 | Partial | 3/3 | 检查新增文件触发、当前checkoutSHA、真实执行/跳过、日志artifact；非可信PR无生产凭据 |
| LOAD-11.4 MAIN交付与回滚 | Partial | 3/3 | 汇总逐项实现/NoChange/Blocked、配置/兼容/风险和演练回滚；保持Draft到人工合并决定 |
| PR13-A01.1 历史raw取证 | Partial | 3/3 | Use sufficient authorized local generator resources and actual server/actor collectors without weakening safety lines, limits or gameplay; resolve the failed mixed-class baseline and rerun fixed-profile acceptance. |
| PR13-A01.2 统一三截止点 | Partial | 3/3 | 独立算运行期、收尾增量、最终累计；ack与cycle完成分开，兜底分层 |
| PR13-A01.3 差异逐事件解释 | Partial | 3/3 | Use sufficient authorized local generator resources and actual server/actor collectors without weakening safety lines, limits or gameplay; resolve the failed mixed-class baseline and rerun fixed-profile acceptance. |
| PR13-A01.4 单来源报告生成 | Partial | 3/3 | 正文/分布/总表由同一派生数据生成，旧统计与新口径并存；加入守恒回归 |
| PR13-A02.1 负载模型预登记 | Partial | 3/3 | 区分循环玩法与固定active-hold，声明online/active目标、覆盖率/连续时长/命令率和gap上限 |
| PR13-A02.2 时间覆盖验收函数 | Partial | 3/3 | 计算连续满足时长与有效时长覆盖，不用峰值代替保持；缺采样不得默认延用 |
| PR13-A02.3 STOP尾部证据 | Partial | 3/3 | grace结束重读所有最终状态与尾事件，累加最终读取错误和STOP后异常 |
| PR13-A02.4 服务端后置清理 | Partial | 3/3 | grace内查询取消/超时回收和待结算恢复；进程结束与业务资源状态单独签署 |
| PR13-A03.1 真实入口反例 | Partial | 3/3 | 第一次NOT_IN_ROOM清room，Bootstrap无receipt，再发同错误，然后M就绪；不直接填恢复变量绕入口 |
| PR13-A03.2 旧局回调隔离 | Partial | 3/3 | HTTP/WS/恢复poll异步沿用context，回调重新核对当前局与恢复目标 |
| PR13-A03.3 ack丢响应恢复 | Partial | 3/3 | 超时后查询receipt/ack事实，重试同一幂等操作；UI显示已提交待核实 |
| PR13-A03.4 三局和回归 | Partial | 2/3 | 结合重复错误、旧回包、ack失败恢复做同账号三局，核对资产与poll清理 |
| PR13-A04.1 丢required主动恢复 | Partial | 3/3 | 无required也有界查询可ready状态，合法确认；定义NOT_FOUND/expired分类 |
| PR13-A04.2 ready乱序/send失败 | Partial | 3/3 | 测send=false/重复accepted/accepted后required/旧match；不把本地send当权威成功 |
| PR13-A04.3 启动失败与恢复 | Partial | 3/3 | 在三处单独失败再重试并重启，验证room唯一、route、hold和ticket终态 |
| PR13-A04.4 多局/STOP组合 | Partial | 3/3 | 合并断线resume、晚通知、第二/第三局和取消，逐账号查后置状态 |
| PR13-A05.1 持久化失败恢复 | Accepted | 3/3 | 本子项适用层已裁决；全范围门槛另行汇总。 |
| PR13-A05.2 队友和旧房间隔离 | Accepted | 3/3 | 本子项适用层已裁决；全范围门槛另行汇总。 |
| PR13-A05.3 幂等/重启资产矩阵 | Accepted | 3/3 | 本子项适用层已裁决；全范围门槛另行汇总。 |
| PR13-A05.4 ledgerChainMismatches告警归因 | Accepted | 3/3 | 本子项适用层已裁决；全范围门槛另行汇总。 |
| PR13-A06.1 响应完整性fixture | Partial | 3/3 | 按协议判断body完整结束；合法close与截断区分，保留大小/超时保护 |
| PR13-A06.2 连接失效/并发/会话 | Partial | 2/3 | 空闲close下一请求重连、重叠走fallback，generation变化取消并阻旧响应 |
| PR13-A06.3 请求开始context | Partial | 3/3 | 发起时冻结run/client/cycle/match/phase/logicalID，attempt及终态沿用 |
| PR13-A06.4 边界与收益复验 | Partial | 3/3 | 先全部边界通过，再三轮固定请求组合A/B；报告成功/失败/pending及实际复用率 |
| PR13-A07.1 旧数值合同定位 | Partial | 3/3 | 复现旧布尔/余量成员错误，列每断言迁移映射给B02；不恢复废弃参数 |
| PR13-A07.2 全PG关键矩阵 | Partial | 3/3 | 执行完整适用Server测试；关键settlement/asset/route/restart/replay用例不用单个filter替代 |
| PR13-A07.3 CI触发和证据 | Partial | 3/3 | 覆盖所有新增测试/helper路径，上传TRX/日志/skip/版本；离线网络隔离 |
| PR13-A07.4 MAIN复跑适用套件 | Partial | 3/3 | MAIN固定SHA重跑关键回归并核对计数/skip/artifact，独立Numerical和load均记录 |
| PR13-A08.1 运行来源与历史基线 | Partial | 3/3 | 区分cb96d16构建与a33f58f仅checkout；记当前head与历史run来源，无法读取写missing |
| PR13-A08.2 任务状态同步 | Partial | 3/3 | 每项分别记录实现存在/历史测试/当前复验/可验收；对账差异加入阻塞非覆盖历史 |
| PR13-A08.3 隔离回滚演练 | Queued | 0/3 | 在隔离实例恢复旧镜像/配置，验证健康/房间/receipt；DB迁移单独预演 |
| PR13-A08.4 交付来源与未完清单 | Partial | 3/3 | 更新PR/报告/状态一致，记录暂存旧云端补丁、备份和临时范围；未验证线上状态标历史 |
| PR13-A09.1 固定集成验收输入 | Partial | 3/3 | 测前冻结输入与必跑用例，独立设计反例；每run只验一个确切集成版本 |
| PR13-A09.2 多账号正常三局 | Failed | 1/3 | 继续独立层与场景；保留自然三局失败和600秒截止，不改基线判据或数值默认。 |
| PR13-A09.3 全故障与资产后置 | Partial | 3/3 | 注入丢失/乱序/超时/重启/STOP，记录客户端DB/route/holds四方实际状态 |
| PR13-A09.4 独立裁决反馈 | Partial | 1/3 | 继续独立层与场景；保留自然三局失败和600秒截止，不改基线判据或数值默认。 |
| PR13-A10.1 三组成对A/B预登记 | Partial | 3/3 | AB/BA顺序交错至少三对，固定warmup/hold/drain/拒绝标准；收益目标先冻结 |
| PR13-A10.2 默认限流建立负载 | Partial | 1/3 | 合法多发压源或预登录/渐进启动，记录各IP持续写/读率；无法建立目标直接Blocked |
| PR13-A10.3 长期资源回收 | Partial | 2/3 | 先30分钟稳定观察再明确预算的浸泡；资源斜率/GC后水位/每已完成局回收及drain核查 |
| PR13-A10.4 性能收益和容量裁决 | Blocked | 2/3 | Use sufficient authorized local generator resources and actual server/actor collectors without weakening safety lines, limits or gameplay; resolve the failed mixed-class baseline and rerun fixed-profile acceptance. |
| PR13-B01.1 战斗关联合同 | Partial | 2/3 | 冻结config hash/strategy/seed/phase与发起context；数据不可得为null+原因 |
| PR13-B01.2 通信、机会和有效进展 | Partial | 3/3 | 区分心跳、动作机会、submit/ack、有效伤害/治疗/盾/抽牌、目标变化及等待原因 |
| PR13-B01.3 分层体验指标 | Partial | 3/3 | 输出首次有效操作、10/30/60秒有效量、操作占比、连续控制、抽牌/溢出/请求率 |
| PR13-B01.4 终点与删失 | Partial | 3/3 | 保留全部分母，截止样本observed_duration+censored；停滞兜底单列非独立随机删失 |
| PR13-B02.1 过期测试API迁移 | Partial | 3/3 | 旧布尔与余量成员逐断言映射CurrentRhythm/CoreCardsSpent、CurrentSteps/FractionalRemainder；先编译复现 |
| PR13-B02.2 真实Resolver规则向量 | Partial | 3/3 | 首核/R/P/B/逐卡floor、46/72/113限定向量、双元素/调节/两种治疗用真实Resolver |
| PR13-B02.3 预览/协议/权威一致 | Partial | 3/3 | 预览与提交比较有效伤害/治疗/盾/控制/余量；前后状态/RNG hash不变 |
| PR13-B02.4 房间策略和恢复 | Partial | 3/3 | 创建/PVE/PVP工作副本/持久化/恢复保策略；缺旧字段按已批准默认解释 |
| PR13-B03.1 三种脚本策略 | Partial | 3/3 | 保留baseline_all_hand，新增确定性basic/build策略；不能看库序/隐藏路线/未来drop |
| PR13-B03.2 同预算场景矩阵 | Partial | 3/3 | 默认/纯核/续航/控制过牌/调节混核，同品质等级成本；单/双/精英/Boss/PVP换边，成对加极值 |
| PR13-B03.3 配对样本与区间 | Partial | 3/3 | 首轮每主要声明层至少1000配对seed、三独立seed块；按seed成对重抽样，真人资料另记 |
| PR13-B03.4 profile边界和可重放 | Partial | 3/3 | 策略/卡组/时长/兜底任何变化均新profile；原baseline保留同版本可重放 |
| PR13-B04.1 真实默认牌表诊断 | Queued | 0/3 | 读取有效牌表，测无有效行动、缺防御、满血治疗、凑核和关键牌到手；区分策略打空 |
| PR13-B04.2 单卡替换候选 | Partial | 3/3 | 一次替一张，先协同再收益；保留正式默认，不加初始资源或改基础手牌 |
| PR13-B04.3 抽牌与等待提示 | Partial | 3/3 | 显示正在抽牌/受控/阻断/满手轮空/等确认，ETA仅在可可靠估计时显示 |
| PR13-B04.4 初始体验裁决 | Partial | 3/3 | 对比有效操作、首战结果、凑核、资源守恒和保留牌决策；不只看点击频率 |
| PR13-B05.1 具体怪物归因 | Partial | 2/3 | 复现白名单长尾并区分高耐久/恢复闭环/克制/控制/目标/通信问题 |
| PR13-B05.2 单因素HP/预告实验 | Partial | 2/3 | HP1.00/0.95/0.90一轮；首意图预告0/0.25/0.50秒另轮，不组合偷因果 |
| PR13-B05.3 强度/经济边界 | Partial | 3/3 | 保留Boss阶段/PVP，算每局与每分钟收益、药耗和死亡损失；漂移先阻塞 |
| PR13-B05.4 候选推荐判据 | Partial | 3/3 | 用配对区间判断：长尾P95相对改善15%草案、通关率5百分点/资源分钟5%漂移复审；high censoring不按完成样本推断 |
| PR13-B06.1 CurrentRhythm对照 | Partial | 3/3 | 固定同核单张推rhythm至5的返2路径，核对手牌上限/抽牌来源/洗牌/动作节拍 |
| PR13-B06.2 CoreCardsSpent候选 | Partial | 3/3 | R1/2/3/4/5返0/0/1/1/2，B不作真实消耗；C/E继续既有蓄能0.5上限 |
| PR13-B06.3 复合过牌长序列 | Partial | 3/3 | 被动单独/水调节/即时抽/双抽/加速分别及组合，记消耗、请求draw、实际draw、蓄能、洗牌与cap |
| PR13-B06.4 候选体验和版本 | Partial | 2/3 | 比净卡差、10/30/60秒有效量、空等/死亡/对位，测试restore与PVP持同policy |
| PR13-B07.1 当前与定点表 | Partial | 3/3 | 对照[1,1,2,2,3,3]与十分点[10,14,18,22,26,30]，上限与端点不变 |
| PR13-B07.2 存量+2/+4影响 | Partial | 3/3 | 单独评价2至1.8、3至2.6的生存/溢出/实际盾；记录受影响等级与审核 |
| PR13-B07.3 余量提交/清零 | Partial | 3/3 | 无截断五次贡献5/7/9/11/13/15；逐边界验证余量一次提交及清零 |
| PR13-B07.4 有效盾和余量显示 | Partial | 3/3 | 显示本次整数、实际盾、溢出和候选余量；候选字段不假扮已启正式规则 |
| PR13-B08.1 既有8秒控制合同 | Partial | 3/3 | 分请求/减免后/重叠新增控制和不可操作union，核对full/half/zero边界 |
| PR13-B08.2 同品质单卡边际 | Queued | 0/3 | 分净卡差、有效伤害/盾/治疗/控制和cap损失，整体输出与稀释一起比较 |
| PR13-B08.3 主核/抵消/回复合同 | Partial | 3/3 | 调节可定核/计同核不增P不进E0，但其他反牌可经K影响；两类治疗分开 |
| PR13-B08.4 帽内有效值和候选条件 | Partial | 3/3 | 理论/有效/溢出/边际强化并列；只有获证异常提单卡/同来源版本候选 |
| PR13-B09.1 实际怪物pool基线 | Partial | 2/3 | 核查已有接纳/跳过/替换能力，再测池大小/关键牌到手/同核/路线稀释 |
| PR13-B09.2 3/5/8位候选 | Partial | 3/3 | 比3/5/8，同基础20，新接纳入弃牌不补抽，非战斗选择，无跳过补偿 |
| PR13-B09.3 来源、幂等和状态切换 | Partial | 3/3 | 重复submit、满位、入侵中断、恢复、死亡撤离清理；验证唯一instance和本玩家击杀 |
| PR13-B09.4 连续性与选择成本 | Partial | 1/3 | 比有效构筑/选择时长/请求量/资源分钟与可见策略，不自动启用候选 |
| PR13-B10.1 顺序/主核可见 | Partial | 3/3 | 选序编号/主核标识，明确重选/调整；preview绑定target/room/revision/policy不暗中排序 |
| PR13-B10.2 有效值与多语言说明 | Partial | 3/3 | 展示基础/核倍率/向反/伤害/治疗/盾，随机或不可得阶段不虚构精确值，窄屏折叠 |
| PR13-B10.3 本地按下与权威成功 | Partial | 3/3 | 本地选中/按下及时反馈；submitted/confirmed/rejected/recovering不同，合法业务command单条 |
| PR13-B10.4 帧率/延迟/失效目标 | Accepted | 3/3 | 本子项适用层已裁决；全范围门槛另行汇总。 |
| PR13-B11.1 可见等待状态 | Partial | 3/3 | 准备确认/进房/抽牌受控/切目标/终态/资产处理中/待ack各显示真实原因 |
| PR13-B11.2 结算UI恢复 | Partial | 3/3 | 复用重复NOT_IN_ROOM/旧回调隔离，回大厅不吞未确认receipt；ack丢包有待核实入口 |
| PR13-B11.3 有证据才轻量化 | Partial | 3/3 | 成本显著才评审轻量查询/单飞/退避，复用LOAD08.4同契约与兼容，不另造接口 |
| PR13-B11.4 有渲染三局和窄屏 | Partial | 3/3 | headless流程另列，录rendered准备至ack三局；长文/语言/断线等待全检查 |
| PR13-B12.1 集成来源冻结 | Partial | 3/3 | 收集source SHA、配置内容hash与策略版本；原始/派生hash分开，由MAIN核实 |
| PR13-B12.2 独立off/on和体验矩阵 | Partial | 3/3 | 独立重跑默认与每candidate及获益组合，真人反馈按skill分层；失效反例回owner |
| PR13-B12.3 配置生成与版本回滚 | Partial | 3/3 | 只改受控源定义，经现有export/校验；生成bytes不手改，新房策略锁定，旧房保原 |
| PR13-B12.4 全量最终裁决 | Partial | 3/3 | MAIN逐项Accepted/NoChangeWithEvidence/Blocked，原容量与候选体验分开；存在阻塞保持Draft |

## 未达验收门槛

- PR13-A01.1：Original files were deleted. Current original-profile 50/100 attempts and owned launch manifests are retained, but capacity targets were not met and old count differences cannot be reconstructed.
- PR13-A01.3：Original files were deleted. Current original-profile 50/100 attempts and owned launch manifests are retained, but capacity targets were not met and old count differences cannot be reconstructed.
- PR13-A09.2：Current original ten-client profile completed 14 natural cycles; distinct legal cleared-route control 18. Neither achieves 10x3. Both have verified clear business state and runtime-owned cleanup, but coordinator exit-zero cleanup fails. No paired performance claim.
- PR13-A09.4：Current original ten-client profile completed 14 natural cycles; distinct legal cleared-route control 18. Neither achieves 10x3. Both have verified clear business state and runtime-owned cleanup, but coordinator exit-zero cleanup fails. No paired performance claim.
- PR13-A10.4：Local generator safety redline stops the original 50/100 target; shared-host diagnostics lack actual server/actor metrics and the mixed-class correctness prerequisite remains failed.
