# 三种策略：目标失效与等待边界

当前真实BattleRoom、正式RoomSnapshotProjection/Protobuf、当前GameStore/Gateway/LoadClient通过本机真实WebSocket跑9个有效场景：baseline_all_hand/basic/build × 3个seed，合法20张牧师牌组、空装备、武器0、PRI-01等级3，其余0。目标失效通过真实怪物TakeDamage API形成，随后明确恢复同battle原目标快照；眩晕通过真实ApplyStun，出牌真实PlayCards，抽牌通过100ms Domain推进。它们是受控边界，不能当自然远征或TTK样本。

实际主循环原有目标选择/出牌分支提取为_try_battle_action供主循环与原生实验共用，分支顺序、卡牌策略、合法门和原等待均不改。外层pending门同主循环使用。33组、99次真实负向观察中：stunned、target、drawing，basic/build的单牌健康蓄牌为strategy_wait/intentional_hold；每组均核对真实服务端接收命令增量，0非法出牌、0选目标、0弃战。baseline继续原有全手牌策略，抽到一张时真实出牌，不假装策略等待。12次真实出牌全部牌在手且实例唯一，预览实际执行并逐字节证明房间不被修改。

**诊断失败与规则核对：** R1实验权威端未实现恢复目标后触发的正式combat.preview，连接被测试端关闭，整轮未验收，原件保留。R2误预期推进3秒即可抽一张；GDD_BASE §2.3及PlayerCombatState明定基础4秒，眩晕暂停充能，因此无牌属于正常，未报为玩法缺陷。R3按实际引擎100ms步进，到首张自然牌即停并设10秒上界；实际基础间隔4秒。没有改变抽牌规则、眩晕、策略或验收阈值，没有以放宽标准掩盖问题。

此前216场实际Domain/Numerics T01/T02原件与45个当前依赖重新核对：54重复轨迹和54隐藏库序/RNG控制、1084/1084合法出牌，40正常胜利和68删失保留。与本轮原生12/12合法分别报告，不混合时钟或推导策略强弱。该任务累计216+2诊断+9有效=227场，低于300上限；3个seed不保证精度，也不外推真人。

原生27个当前依赖重新逐SHA匹配。最小实验project.godot与只禁用服务发现的boundary_store均明确为测试接线，不能称完整Program/auth/PG/LIVE/容量/渲染验证；边界origin版本为空仍保留，不补造全上下文证明。没有公网、云资源或源码上传，所有本地进程已终止。原件、三轮控制源、编译物和执行的驱动器逐SHA备份G盘。
