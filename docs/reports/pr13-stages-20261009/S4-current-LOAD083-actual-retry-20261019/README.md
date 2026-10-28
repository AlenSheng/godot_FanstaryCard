# 当前有界重试：三个实际边界补齐，失败轮不改写

实际Gateway/current8eb完整Program/PG隔离复制库，中继用官方Protobuf错误向量声明注入429和503。T01实际等待5284ms、两attempt，实际客户端请求间隔5203ms，满足Retry-After5；调用者移到新phase/cycle后仍保留原context。T02外部STOP标记调用原用例的Gateway.end_session取消原语，17ms完成、仅一次attempt且未触后端，原context保留；不冒认整个GameplayLoadClient收尾。

T03实际后端先200完成购买，中继才替换503，实际重试继续同一键、trace和16B请求体。两份真实购买回复完全相同，第二次为后端幂等回放；数据库金币180→0、WarriorSoul0→20，购买记录1。账本按币种为Gold-180和WarriorSoul+20各1条，**总2条是合法分币种记录，不是重复发资产**，与EconomyRepository.GrantAsync及PurchaseAsync一致。

原R4整轮仍失败：控制器误断言总账本只能1条而强制结束原生进程。T03只复用其已持久化Native结果、真实回复、稳定键/体和PG事实作为限定组件证据，没有重复购买，也不把R4说成退出0。只读R5新轮正常退出0、双日志干净，按原冻结条件完成T01/T02并逐条落盘，八类业务摘要及world/account/ACK不变。

原R1私有Node.owner字段冲突导致编译失败、R2源账号无180资金、R3控制器漏导入urllib、R4单总账假设及强制结束均保留。前三轮没有Native实际业务购买；R3前明确声明复制库现有账号初始180测试金币，R4/R5复用同一PG而未再次注资。游戏默认资产、价格、2–20昵称、限流、HTTP10/30和取消<1s均未放宽；合法80/70规则同样不靠改数据规避。新增真实局/账号0，LOAD084累计21及B11121/B11227均不重置。

MAIN关闭LOAD08.3三个EXPERIMENT缺口，任务改ReadyForAcceptance，仍等待LOAD08.2真实单飞/新鲜性/隔离依赖及MAIN链审。当前60Accepted、61Partial、11Ready，仍72项未验收，缺口265→262；LOAD084仍Ready、其他131项及全局门保持，没有NoChange或整项目通过。

所有本地进程仅隐藏低优先级headless/Dummy，无窗口/焦点/桌面输入，全部自有进程已停。没有云端、生产、UI或美术修改；所有原件/代码回存G盘SHA核验。本轮的“合法双币种账本”识别规则已固定到后续上下文，避免再按单行总数误报。

原件：G:\PR13Evidence\load083-current-retry-20261019-r1-originals。
