# PR13-B06.1 整项 MAIN 验收通过

三个案例的OFFLINE与EXPERIMENT共6个支持已逐项复核。当前实际PlayCards和真实CombatDeck覆盖同核五次请求返牌、满手请求与入手分离、实际库空洗牌和默认／显式CurrentRhythm一致；完整216步账本与Python独立RNG重放匹配。

历史338条原生TRX以原SHA重新核验，仅选三个对应方法，均Passed；完整PlayerCombatState、CombatDeck、NumericalRules和三个测试源文件与原运行清单SHA一致。12个当前实际实验相关完整源文件SHA匹配原Domain构建713文件清单，不把历史测试DLL冒充当前二进制。历史已完成样本不重跑。全部失败仅为准备期工具编译错误，原件保留，未发生业务实验失败或判据放宽。

MAIN按规范“仅证明代码资源路径，不把局部路径宣称全卡池无限循环”签署本项Accepted。正式默认和候选开关不变，受控牌序／合成靶怪／边界快照／250ms输入全部显式报告，不能当作自然战斗或真人体验。

仅本项Partial→Accepted，75 Accepted、49 Partial、8 Ready，57项未验收，缺口230→227；其他131任务与所有全局门不变。继续B06.2及其余未通过项目，252/300当前专项状态预算保留，不因新目录或新轮次重置。
