# 实际 Web／HTTPRequest 边界：两轮未通过

本次补的是实际浏览器执行证据。使用与现有引擎匹配的官方 Godot 4.7.2 单线程 Web 模板；完整模板包 SHA-256 对照官方发布值通过，模板只放任务私有目录。7 个当前客户端输入冻结后导出，浏览器中 `OS.has_feature("web")` 为 true，调用当前 Gateway 的 Web 分支。没有把历史原生 HTTPRequest 参考臂冒充 Web 结果。

**原版本 20/24，候选 22/24，两轮整体均 Failed。** 原版本失败为合法 gzip、deflate 非空响应、截断空 gzip、未知编码。候选仅在隔离副本关闭引擎二次解压并拒绝未知编码，前三项中的合法 gzip／deflate 和未知编码修复；但浏览器解压后的坏 CRC 载荷也被接受，新增一个未通过案例。截断空 gzip 在两臂中均仍被接受。不能以通过数量增加宣布候选合格，候选源码没有写回原工程、提交或部署。

独立核对 48 份原始 HTTP 明文帧及 48 份实际浏览器返回 body。候选坏 CRC 帧的 trailer 与载荷 CRC32 确实不符；截断空 gzip 确实缺少最后一个字节。浏览器交给 Godot 的是已解压内容，不能由空输出、Content-Length 或尺寸特判倒推出原始压缩流完整。本次没有加入这类启发式，也未改 24 项原期望、2 MiB 限制、超时或正确性标准。原生已通过的矩阵没有重跑。

另发现测试夹具按 Windows MIME 注册表把 JS 发成 text/plain，导致两个 AudioWorklet 模块报 MIME 错误；不是游戏音效或网络接口错误。独立使用 text/javascript 控制后两个现有模块加载通过，AudioContext 随即关闭，无音频播放、无 Gateway 案例重跑、控制浏览器无 error。原夹具源码和两轮浏览器诊断保留，未来夹具的显式 JS MIME 修正另存。首次私有导出预设缺少 exclude_filter 产生两条 ERROR，导出完成且实际案例随后执行；候选预设补全后 stderr 为空，原错误记录未删除。

合计 3 次浏览器启动，其中 2 次实际 WebAssembly 矩阵；2 次导出均退出 0。48 次案例请求＋52 次证据控制＋9 次状态读取＋5 次独立 MIME 控制＝114 次合成请求，低于 200；导出资源读取 15 次，低于 100。浏览器测试页已关闭，两个本地夹具的服务线程和 socket 均结束，内存／磁盘保留至少 5% 余量。无新增账号、对局、云端调用、上传或全局模板／TLS／CA 修改；所有测试源码、失败、截图及字节原件留本地 G 盘。

本报告不关闭完整 profile，不宣布实际游戏 UI、Web TLS、PG、LIVE 或容量验收。132 任务／396 案例、77 项未验收和 register／gate／MAIN 均保持；旧容量失败也未改写。本次仅同步这份失败诊断报告，不同步未通过实现、原始采样、模板二进制或临时工具。

机制参考：[Godot Web HTTPClient](https://github.com/godotengine/godot/blob/4.7.2-stable/platform/web/http_client_web.cpp)、[Fetch 适配源码](https://github.com/godotengine/godot/blob/4.7.2-stable/platform/web/js/libs/library_godot_fetch.js)、[官方发布与模板校验值](https://github.com/godotengine/godot/releases/expanded_assets/4.7.2-stable)。上述机制判断结合本地同版本源码及实际浏览器字节观察，不以别的版本源码代替本轮执行身份。
