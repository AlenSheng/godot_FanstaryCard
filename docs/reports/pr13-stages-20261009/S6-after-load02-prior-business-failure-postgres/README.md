# PR13 人工 STOP 不覆盖先前业务失败的数据库证据

复核腾讯云原 Real_LOAD02_timeout_STOP_preserves_original_business_truth 的 timeout-before-stop 变体。真实 Godot 负载客户端在人工 STOP 前已发生 preparation HTTP 超时，first-failure 单调时间早于 STOP 观察；最终仍 failed=1、cancelled=0、completed=0，原错误完整保留，原场景仍为 failed。原生断言检验的正是失败不被 STOP 洗成成功，而非压力通过。

真实隔离 PG 与原 Program 在清理后保留相同钱包、消耗品和装备归属；后续真实 preparation 创建／取消使装备版本和取消的 preparation 行合法变化，原件保留这些变化，未抹去以制造完全相同。源文件与当前对应，G 盘 3,456 个原件及归档 SHA／CRC 再核对。原 wrapper 计数错误保留，使用原始 TRX 29 条实际执行／通过、零跳过和精确变体的独立核对。

原 LOAD-02.2-T01 断言同时覆盖 LOAD-02.1-T02 先业务失败再 STOP 的不变量，仅补齐该 POSTGRES 层，没有重复计算新样本；缺口 111 降至 110。LOAD-02.1 其他层和案例、容量、暂缓失败及门禁保持未接受。
