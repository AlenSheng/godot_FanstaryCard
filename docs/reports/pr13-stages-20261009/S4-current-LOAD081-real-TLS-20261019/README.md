# 当前真实TLS边界：修复连接关闭后误复用，三项实验通过

Godot4.7.2实际HTTPClient/Gateway连接自有127.0.0.1 TLS服务，17个直接请求案例和6个Gateway调用。固定轮原生退出0、29项检查；另按服务端实际连接ID、收发body SHA、请求头和握手日志复核90项。21次实际HTTP、14条成功TLS连接、2次预期证书拒绝。新增真实对局/账号/资产/货币均0。

T01完整262163B响应声明Connection: close但延迟150ms才FIN。原代码完整body成功，下一请求却复用正在关闭的旧连接并失败，原R1退出1保留。现在解析Connection头的大小写无关逗号token，完整body验证后主动关闭；下一请求实际新TLS连接成功。立即关闭的262158B响应及正常keep-alive/chunked正例均按实际发送SHA完整匹配。

T02声明ContentLength多100、半chunk、缺终止zero均返回失败/status0/空body，无成功截断。T03不信任根证书和错误SAN各在握手拒绝，服务端未收到HTTP；2097153B原始响应和gzip解压超2MiB均拒绝，生产2MiB/超时/证书默认校验未放宽。自有一天有效CA仅通过私有测试project设置提供；未改系统信任或真实项目设置。该设置覆盖默认CA集合，详情见[Godot ProjectSettings](https://docs.godotengine.org/en/4.6/classes/class_projectsettings.html#class-projectsettings-property-network-tls-certificate-bundle-override)；HTTPS默认校验行为见[HTTPClient](https://docs.godotengine.org/en/4.4/classes/class_httpclient.html)。

两origin和下一请求的实际Authorization摘要正确；Gateway顺序共享同连接，关闭use_reusable_http时每请求独立连接，重叠请求分别完整完成。此处session-next只验证下一请求凭据，完整会话生命周期继续由既有原生/实际Gateway测试支撑，不把名称冒认成额外会话流程。

固定轮只有两条预期TLS握手ERROR，严格位于两个非法证书案例内，无脚本/泄漏错误；它们是拒绝成功的证据，不能按笼统日志ERROR误判。原夹具CA路径斜杠比较和空buffer哈希错误已修，原件保留。分析器原猜13连接及误要求显式TLSOptions调用也保留，按实际A13+B1和HTTPS默认connect_to_host修正分析，没有重跑SUT。当前完整客户端2146输入，较LOAD082仅transport一文件变化；22套351项原生回归退出0、双日志干净，旧硬链接私有源码COW冻结。

MAIN只关闭LOAD08.1三个EXPERIMENT并置ReadyForAcceptance。LOAD05.4仍缺三个LIVE；LOAD06.1/07.4已Accepted。081→082→083→084等待依赖和整链审查，未授予Accepted或全局门通过。当前60Accepted/59Partial/13Ready，72项仍未验收，缺口259→256。其他131项与全局门不变，无阈值放宽。旧LOAD08421局/B11121/B11227预算不重置。

所有本地引擎隐藏headless/Dummy、低优先级、60FPS上限，无窗口/焦点/桌面输入；自有引擎和四服务均已退出。没有云、生产、美术或新UI渲染操作；代码未提交/推送/部署。GDD双卷和合法80/70、按币种两行账本的防误报规则继续。

原件：G:\PR13Evidence\load081-real-TLS-20261019-r2-originals。
