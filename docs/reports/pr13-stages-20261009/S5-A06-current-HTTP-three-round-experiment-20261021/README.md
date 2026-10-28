# A06 四项当前HTTP传输验收通过，收益证据保持Inconclusive

MAIN接受A06.1／A06.2／A06.3／A06.4，补齐12个EXPERIMENT缺口，130→118；累计100 Accepted／24 Partial／8 Ready，仍32项未整体验收。其他128任务和全部global gate保持，不授予全项目或容量通过。

本轮为当前Godot4.7.2实际HTTPClient/Gateway与原LoadTelemetry的受控回环实验，三个独立Native进程重复全部边界与归属场景。fixture元数据、用户标签和令牌是明确输入，不是实际游戏房间、认证账号或PG资产。实际HTTP请求291次，其中测量请求180次，其余为边界、预热和控制请求；新增真实游戏／账号／PG均0，不将请求数量冒充对局或执行上千次玩法采样。

A06.1验证完整Content-Length后close、无长度close定界、完整chunked及close/trailer均成功；少字节和截断chunk失败且没有部分成功。gzip/deflate、合法空压缩、损坏CRC、截断空gzip、非法deflate、未知编码、原2MiB线体/展开上限和短观察超时逐项通过。独立Python解压和chunk解析核对真实原字节，不能只看连接status。自有未信任证书具备匹配IP SAN，真实TLS握手拒绝且服务器未收到HTTP，没有不校验或HTTP回退。仅负向编码/TLS调用中预先声明、可定位源函数且返回0字节的引擎诊断被分类；所有原日志保留，脚本/解析错误或泄漏一律不允许。

A06.2空闲FIN后下一logical请求在新连接有界完成，所有attempt沿同logicalID；预热复用连接上重叠A/B分别在主连接和fallback连接返回各自不同body，原字节和CID可对账。旧origin A的慢请求尚未完成时切换generation、token及origin B，新请求仅携新header并返回B的标签；旧200响应被原Gateway取消，stale_session且无data，不泄漏旧结果或旧header。

A06.3 cycle1请求在cycle2完成、503重试期间stage改变，attempt和terminal均保留dispatch时run/client/process/cycle/match/room/phase/logicalID。另在真实慢body未交付前STOP/end_session，原LoadTelemetry把迟到响应记为observation_phase=drain，同时业务仍为旧cycle/playing/M1，observer当前为cleanup/M2。实际wire received < STOP < response完成时间独立核对。缺失异步context的声明反例被原记录器标Unknown，不借用当前cycle。这些fixture输入明确不作真实资产、room归属或对局证据。

边界三轮全部通过后才执行AB／BA／AB三对原生20请求组合，每arm另1次预热。A为当前per-request原one-off路径，B为当前可复用路径；源字节、实际20个GET顺序、PB载荷/长度/status/编码/framing一致，只有运输选择不同。B的20次测量均复用、实际使用1个连接；A复用0、使用20连接。所有180个测量请求包括失败均有唯一terminal，无pending被丢弃。实际body、trace/logicalID、延迟与复用率逐请求核对；body profile不包含动态requestID或时间header，具体定义已测前冻结。

反例一的慢参考20成功，坏候选19成功1非法PB失败：成功请求P95从184ms到50ms，仍按原审查函数判Failed，不能以快掩盖失败。这个反例刻意改变fixture延迟及输出，明确只测试反误判门禁，不是同负载因果收益。反例二只凭更快但不同字节profile仍判DiagnosticOnly，不给因果结论。

三对同组合的candidate-minus-baseline全terminal均值差为−15.85／−17.20／−15.55ms，平均−16.20ms。现有算法按轮cluster精确枚举27个bootstrap和8个sign-flip，p=0.25。描述性区间虽在负侧，三轮仍不足以确认95%收益，最终Inconclusive，performance_acceptance=false；当前默认运输策略未修改、无新开关启用，也不从60FPS回环和用户并行工作负载推断公网/云端收益。A06.4按允许的NoChangeWithEvidence完成合同验收，不能把任务Accepted读成性能改善已获批准。

27个三轮Native规范案例全部Passed；9个测量/反例arm各20请求结果完整，462项独立源/字节/状态/统计核对通过。源码/fixture/私有脚本、真实边界body/header、逐连接日志、原逻辑与drain审计、所有启动/退出/预热和期望负诊断、合成证书生产器及统计原件完整G430 SHA/CRC封存。合成TLS密钥仅在自有fixture/G私有原件中，不写入公开报告，不是生产凭据；未向系统信任库添加证书。

本地每次只有一个Godot进程，始终headless、Dummy音频、60FPS、CREATE_NO_WINDOW和低优先级，未全屏或抢焦点/输入；没有真实登录、PG、重负载或云端写操作。全部回环服务已关闭。完整GDD v0.70主卷及v0.69基础卷全文快照保持；合法Mage70/Priest80/Guardian100与80/70边界不改、不误报。本轮没有产品代码、UI、图像资源或新像素验收，无需ImageGen；没有新Git提交、推送或生产部署。容量只限现有主机，资源不足继续未通过，真人体验排除。原标准没有放宽，下一步继续剩余集成、数值交付和视觉等未验收范围。
