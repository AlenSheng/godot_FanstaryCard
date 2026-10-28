# GET单飞、新鲜性和隔离：真实回退缺陷修复后通过

当前Gateway/8eb完整Program/PG，两个已有真实账号，声明只延迟或保留真实后端回复、没有改造业务payload。T01两个同时同版本GET只触发一次后端200、各自取得相同真实结果；约284ms包含明确200ms回复延迟，不是网络延迟性能宣称。

T02先保存旧Bootstrap，再用公开select_class实际写入Priest/version3。原逻辑中服务器已保存，但迟到旧回复把客户端退回Mage/version2，R1真实Native退出1和原数据完整保留。修复只在职业写成功后增加_lobby_request_epoch，使之前大厅请求失效；新GET因Gateway写后read_epoch变化也不会加入旧flight。固定后实际旧消费者返回，客户端保留Priest/version3。旧单位负例退出1，新单位及22套351项原生检查退出0/双日志干净，旧私有源码先解除硬链接保留。

T03两个真实UID访问同一路由独立请求、返回各自档案。两个相同重叠PUT不合并：第一个真实200，第二个独立“请求正在处理”status0错误，不能把它伪造成相同成功。后端只有一次PUT、PG档案version只增1。完整固定Native正常退出0，三个案例原件齐全；全部业务资产摘要、玩家/对局/收据/ACK数不变，新账号/真实局/初始资产/货币0。

MAIN关闭三个EXPERIMENT缺口，任务ReadyForAcceptance；LOAD08.1仍缺TLS/完整body三项实验依赖，082/083/084都不自动Accepted或集成。60Accepted、60Partial、12Ready，仍72未验收，缺口262→259；其他131项、全局门和原失败保持。没有NoChange或阈值放宽。

只新增职业写后epoch失效与回归用例，未改服务端、schema、GDD或数值；原LOAD084投影与三轮收益作用域源码不变，但当前完整客户端已为2146输入，不能继续声称旧2145全字节相同。代码未提交、推送或部署。所有本地步骤低优先级隐藏headless/Dummy，无窗口/焦点/桌面输入，全部自有进程已停止；没有云、生产、UI美术或新渲染操作。合法80/70和合法按币种双账本不误报规则继续。

原件：G:\PR13Evidence\load082-current-singleflight-20261019-r2-originals。下一步完成当前TLS/body边界，审查依赖链并继续全目标。
