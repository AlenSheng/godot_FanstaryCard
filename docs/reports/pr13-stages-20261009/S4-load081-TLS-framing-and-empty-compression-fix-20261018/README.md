# HTTP空压缩响应修复与TLS／分帧验收

修复一个实际客户端缺陷：完整且合法的gzip／deflate空响应，解压后也是空数组，旧代码把它与解压失败混同并拒绝。仅修改reusable_http_client.gd：空输出时再用内置流式解压器确认全部输入已消费、没有输出，并在流结束后不消费探测字节。截断流仍会消费探测字节或失败，不能只看空数组或ISIZE放行；普通非空解压路径、2MiB线上／展开上限和TLS校验保持原逻辑。

当前连接复用与一次一连接路径各33项通过：完整Content-Length后close、close-delimited、chunked带trailer、HEAD／204、gzip／deflate及合法空压缩体；少字节／缺终止chunk、截断空gzip、CRC／Adler错误、超2MiB线上或解压后数据、非法／未知编码、慢响应均失败且不返回成功的部分body。顺序3次请求的真实socket数，复用路径HTTP／TLS均为1，一次一连接均为3；空闲关闭后使用新连接。

真实CA与hostname校验开启。私有CA只配置在独立探针项目，生产project.godot与系统信任未改。受信任证书成功；错误hostname、已过期证书、不受信任自签名证书均被拒，每个当前臂3种坏证书均没有HTTP请求到达，之后3次有效TLS均恢复成功。验证不是仅看Connected状态。

追加一次实际Gateway集成，冻结当前2127客户端输入：空闲断连、一次真实GET连接在响应前被关闭后，以同logicalID进行2次物理尝试并恢复；busy时两个重叠请求走独立连接并保留各自body。旧A会话请求已上线上后切换B，迟到旧结果为stale且不带data／headers，遥测保留原generation；新会话与正常切换origin后的请求使用正确新凭据和body。9项集成检查通过，均为声明的合成会话，无真实账号或永久资产断言。

**原失败不改写，历史旧传输不能宣布安全回退。** 修复前原轮因gzip-empty／deflate-empty失败；测试记录器还对空字节调用哈希更新产生ERROR，已单独修正并保留原源／日志，未把它误算成204或HEAD产品故障。历史HTTPRequest参考臂真实接受了截断空gzip与未知编码，本轮记录为Failed，没有重新跑成通过。当前关掉连接复用的一次一连接路径已通过，但不等同于旧HTTPRequest或未新测的web路径；整个任务仍为Partial，旧参考的安全性仍未证明。

坏证书和坏压缩输入会产生预期引擎ERROR。记录按具体负例、非成功结果与具体错误文本对账，没有全局关闭日志；当前两个臂各有8个“案例＋文本”诊断事件，在engine／stdout两份日志各出现一次，共16条，不当成16次独立故障。没有未解释的脚本／资源／引擎错误。8个内置解压EOF控制、19项Python夹具控制也通过。

逐案例复核129份应用层HTTP帧与132份原生body哈希。保存的是送入HTTP／TLS socket的应用层明文帧和成功send字节数，不冒充原始TLS密文或网络实收字节。所有8次原生启动均终止、夹具线程与socket关闭；含原失败与控制共135次合成HTTP≤300、125次TCP接收≤400，启动8／8，无限额或正确性放宽。所有源码、失败原件和仅本地夹具私钥保留G盘；Git只含正式修复和本报告，不含原始采样或私钥。

本轮补充6个当前传输组件案例和3个实际Gateway案例的EXPERIMENT观察，不宣称新的完整POSTGRES／LIVE／RENDER／容量或生产时延验收。无云端连接／上传、无新增真实账号／对局、无server源码修改／构建／CSharp测试，真人体验排除。原有726个脏路径保留，canonical register／gate／MAIN及132任务396案例范围不变，正式仍有77项未验收。

测试信任配置依据：[Godot ProjectSettings](https://docs.godotengine.org/en/stable/classes/class_projectsettings.html#class-projectsettings-property-network-tls-certificate-bundle-override)；压缩边界解释参考[Godot StreamPeerGZIP源实现](https://raw.githubusercontent.com/godotengine/godot/master/core/io/stream_peer_gzip.cpp)及[RFC9110](https://www.rfc-editor.org/rfc/rfc9110.html#section-8.4.1.2)。EOF行为以本机实际引擎8个控制和当前33×2HTTP执行为依据，不把master源码当成本机二进制身份。
