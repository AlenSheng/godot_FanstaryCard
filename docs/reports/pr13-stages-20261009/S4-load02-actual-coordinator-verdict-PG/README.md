# PR13 LOAD-02 协调器判定与有界清理真实数据库集成结果

腾讯云原九 PostgreSQL 回归与新增一个故障矩阵方法共十方法通过，零失败、零跳过、无 OOM。新增方法调用八个真实外部 Python 子进程；每次期间和之后保持实际默认 Guardian 20 卡 PostgreSQL 房间完整快照与持久字节不变。matches／room_snapshots 各一条。生产 Domain 程序集 SHA 保持原值。

八模式按当前协调器实际 main／最终报告／返回值测试：短时限未达负载时 execution Passed、load Failed、退出 1；性能与审计损坏保留 CPU／memory／audit loss 全部触发，退出 3；应急报告写出且退出 3；准备 CLI 退出 0 但没有执行目录或负载报告；纯性能超线退出 2；证据无效 3 与人工 STOP 130 分开。hang 用两个真实子进程验证原 stop_all 只强退被列入拥有清单的 PID，另一进程保持运行，再由独立测试收尾回收；此模式的 3 是故障包装器分类，不能称作原协调器返回值。

协调器采用明确的既有故障 fixture，其观测／时钟／客户端是受控注入；所有原 raw、最终完整报告、first／all triggers 与应急文件均保留。CPU 及旧百分比内存字段是兼容故障注入，真实云端资源准入仍遵循 500 MB 和云盘 15% 安全线。不存在新增真实容量／负载样本，不能将这些故障控制当作 50／100 人或 LIVE 通过。

完整 747 原件、G 盘归档 SHA／CRC、逐文件 SHA、328 当前 Git 源码及 11 份真实协调器输入再次核对。通过且终态、无绑定占用后清理本次云端 work／persistent-output，回收 51,585,024 已分配字节；共享输入和所有失败原件保留。阶段副本因 Windows 长路径限制只缩短路径，G-original-to-report-paths.original.json 保存完整 G 原件路径到副本路径的映射，所有原字节保持不变，未重新执行原生任务。首轮未发布的部分复制也保留在本地 outputs。七项 POSTGRES 证据登记在下一阶段执行，本阶段未修改门禁与 MAIN。
