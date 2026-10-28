# A01.2 三截止点统计合同验收

三个案例逐项复核，PR13-A01.2 Accepted。当前27/132项已验收，105项尚未验收；另16项ReadyForAcceptance、87项Partial、2项Failed。

STOP后的确认只进入drain；重复原始事件只计一次；最终进程计数声称完成、原始ACK缺失时，evidence/gameplay维度保持Unknown，不补造完成局数。每个cutoff分别核对ACK总数、逐客户端ACK和、至少k次ACK人数的尾和相等；completed_cycles及其分布单独核算，ACK与完成事件跨过截止点时不混用分母。

25份原件及9份精简证据重新核对SHA。三份执行依赖的AST完全一致；runtime_evidence和cloud_load_test存在CR/CRLF行尾字节差异，前后hash均保留，没有把它们说成字节相同。依赖A01.1已验收，复用已完成腾讯云受控审计，不重跑旧测试。

这里只验收截止点计数合同。旧2144份raw仍缺失，86/90和130/139未完成对账；A01.3/A01.4、G3和整体MAIN不自动升级。当前正在运行的三职业9局修订profile仍待独立原件/SQL复核，本项不替它宣称通过。
