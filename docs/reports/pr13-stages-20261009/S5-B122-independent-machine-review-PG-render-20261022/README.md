# B12.2 三个独立机器反例：EXPERIMENT / POSTGRES / RENDER闭合

本次仅补T01/T02/T03的九个机器缺层，97→88。100 Accepted、24 Partial、8 Ready、32项未验收和全部全局门不变。B12.2自身显式缺层全空，但B12.1/A07.4等前置和整体来源/容量未Accepted，任务保持Partial。本轮反例分类通过，不代表候选收益、全候选组合、全部适用场景或正式激活通过。

重新核对当前51份模拟器/Domain源后，实际Numerics CLI运行三职业、weapon+1、O1、baseline_all_hand、3个登记seed的off/on，共18次真实领域遭遇，errors0，全部胜负/截尾原件保留。manifest为default合法牌组，没有人为凑themed。PrimarySampleFloorMet=false，不能凭3seed作95%收益或等价性结论。模拟Domain SHA db2a29cd与独立Server Domain f91d19f7是分别真实编译的身份，两个SHA分开存，不冒充同一二进制。

现有云主机新建内部无外网/无发布端口网络与一次性PostgreSQL18.6。等待真正postgres主进程和TCP ready，initdb显式UTF8。当前原始143份测试运行文件全hash核对，管理程序集201b00de、当前Server/Domain/Contracts身份保留，直接运行9个必需PG方法，VSTest0，9/9 Passed、skip0，TRX原计数不改。随后当前原生探针通过实际迁移、RoomSnapshotRepository和BattleRoom恢复创建12个自有逻辑房间记录。

T01在三个自有OFF记录先确认完整PG往返相等，再只对它们的snapshot_json players[0].combat.hp减1。真实恢复结果与原默认快照不等，原生观察明确记录Failed3；实际候选ON三个记录往返Passed。真实candidate_matrix(default_passed=false,...)仍返回Failed/default_off_regression，production_activation=false。69/70、79/80、99/100是这次受控持久化回归注入，不是新的GDD血量异常；合法80/70也不夹为80/80，不修改正式规则来遮盖失败。

T02使用另一个明确独立的off-only schema和证据范围，三个真实PG默认记录通过；该范围没有三个必需候选的on运行文件。实际candidate_matrix返回Blocked，精确列出cards_spent_draw/fractional_guardian/optional_monster_pool。其他案例有候选原件，也不借来填这个受控缺跑集合；没有删除或伪称全项目未运行on。

T03第三个schema中的3个真实PG player均IsBot=true、完整恢复Passed。只收集bot/headless的机器集合缺少RENDER时，当前execution_state即使human_in_scope=false仍Partial，不能把“真人移出范围”当机器层自动通过。随后另一个真实渲染完成的机器集合在明确用户排除真人的范围内为ReadyForAcceptance；同一资料在旧human_in_scope=true控制下仍Partial。actual_human_accepted始终false，没有虚构参与者、体验反馈或真人评级。

渲染从这12个实际PG恢复结果经当前Server投影和Contracts Protobuf编码生成，正式Godot解码并显示。三职业×OFF受控回归/ON正常×中英×三尺寸为36个画面，另外3个真实bot投影、3次UI存活时真实评审请求，共42张完整尺寸无损WebP。每次评审后实际鼠标打开战斗属性面板、触发accepted、关闭，无残留遮挡。Native0，完整日志无脚本/解析/泄漏错误；42图解码RGBA与引擎原始像素SHA逐字节一致，全部五个检查图集逐幅审阅，另看4张原尺寸图，卡面/文字/按钮与蓝金风格统一，不需重出资源。该界面是受控下游投影，隔离后端的原有断线提示不作为LIVE或全量本地化通过。

## 重点：限制调整和多次私有失败

首次打包只枚举缓存顶层得到57文件，错误地要求143；原断言失败保留，改为递归清单得到真实143。其派生脚本又有私有引号拼接错误，发生于实际上传/PG之前，源码/观测保留。没有裁减缓存、改预期143或用文件数量冒充原生测试通过。

第一个UI作业被私有控制器disk_free_fraction>5%拦截，尚未创建APP/Godot。复查仍有3,162,898,432字节空闲，只低于5%比例线约1.6MB。新作业的输出全部在自有/output tmpfs384MiB，原图流G后完整SHA核验并写ACK才销毁。因此仅该RAM渲染作业改成“空闲至少3,000,000,000字节且比例>=4.9%”，内存500MB下限不变。计划与实际值单列，生产配置、服务器SSH/网络、容量目标/容量标准、业务评审和图像质量没有改。该放宽不能用于给资源不足容量项通过。

R2原生渲染和G归档均通过，但控制器最终记录ok=false、G_custody_ack_before_RAM_teardown=false。原因是服务先看到真实ACK后退出0，控制器下一轮先检查到退出，尚未把本地acked变量置true就断言。原错误、false计数与堆栈保持不动。只读复查ACK文件的owner/run、G归档SHA、G清单SHA、容器Exit0/OOMfalse、PID0及容器已移除，证明G全部原件确实先于ACK/销毁保存；独立复核写新文件，不把原控制器改成成功、不重跑渲染。只保存了未来使用的修正控制器源码，未再次执行。

整个机器层381项独立来源/PG/像素检查通过，399份测试源、原生输出、原件和生产者已G托管。实际OFF失败3与其他PG成功9、9方法TRX成功、原controller失败均各自独立保留。G保管后，验证三个输入目录owner/包/plan/全部源、单位PID0、无所属容器、无符号链接和生产指纹，再精确删除PG/UI-R1/UI-R2输入；原PG/host raw、所有旧cloudraw、共享UI缓存和A073/143父证据不删。新RAM图片在完整G核验ACK后才随自有容器释放，RAM源清单和摘要保留。生产health200、镜像、启动时刻和环境指纹不变。

本地Godot仅headless/Dummy60/CNO/BelowNormal，进程viewport内合成输入不操作桌面焦点。实际PG/GPU仅既有云主机；新增真实认证和网络对局0，不扩容、不加主机、不改正式UI/资源/源表/GDD，不提交、push或部署。真人按用户要求不在范围，仍明确没有真人通过。
