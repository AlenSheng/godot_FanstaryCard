# A09.4-T02：缺库启动与可用界面仍须 Blocked（2026-10-22）

本轮只关闭T02的LIVE、RENDER两层；旧POSTGRES拒绝反例不重复计数。缺失case/profile由66降至64。仍为100 Accepted、24 Partial、8 ReadyForAcceptance，共32项未验收；六个全局门保持NotAccepted。A09.4仍缺T01两层、T03三层，A09.3前置未整体验收。

当前Server DLL在自有Docker networknone内以/runtime为cwd，实际appsettings的Postgres连接被显式覆盖为空。Program因Npgsql缺少Host退出-6；3次真实loopback健康探测均连接失败。没有伪造HTTP结果，也没有数据库容器、账号、房间或正向PG执行。这是Development私有功能环境，不声称生产全部选项等同。

原同一201b测试DLL的TRX、source、native-exit及143运行依赖身份逐字节核对重用。9条NotExecuted与汇总notExecuted=0矛盾保持原样，未重跑或修改XML。当前覆盖门在同一真实UI PID活着时assess，仍为Blocked/pipeline3；独立复算相同。原native0和可用UI不能抵消缺失的DB执行。

正式DeckBuilder使用3张受控本地草稿；中英两语言、三尺寸共6次SaveDeck原回调各1，点击后原本地提示要求填满20张。gateway.online是明确的UI启用夹具，右下角仍显示未连接；没有真实认证、socket或服务端保存。6张最终WebP的lossy=false，解码RGBA与引擎原像素SHA一致。两份图集逐幅及两张原尺寸复核，提示无残留，卡面、20行和按钮可读，蓝金资源一致，无须ImageGen。

## 重点：三轮不利画面和私有失败未改成通过

R2英文首帧含上一轮中文提示；native0及6次点击成立，独立RENDER仍保留。R3只注入motion，OS光标未动，画面仍残留。早期将它当作原生tooltip的推测不准确，不能据此声称产品存在tooltip故障。R3的capture_cursor在点击后采集，原字段不重写。

R4用Input.warp_mouse移动窗口光标，但私有断言误把窗口2,2当作所有尺寸的逻辑2,2。project.godot24-31规定1920×1080和canvas_items缩放，实际为960窗口4,4、1280窗口3,3、1920窗口2,2。原native1、4行Passed/2行Failed、service/controller失败完整保留；独立坐标换算没有改原行，R4画面也仍未通过。R4清单“BEFORE image”过强，实际坐标在图片同步保存后、点击前同帧记录，无await/input；按源码实际顺序限定。

对照main.gd271/1687和TipsOverlay.clear后，定位到残留来自上次点击的TipsPanel：节点清理后立即读取纹理，读到了上一张已绘制帧。R5只在私有入口clear后await present，等待process_frame与frame_post_draw；正式UI、资源、提示动画与业务代码均未修改。最终每图capture_tips_hidden=true、capture_tips_text为空，实际逻辑viewport和光标换算正确，6次原回调仍各1。最终native0、APP0、controller0，日志无脚本、解析错误及资源泄漏。

R2/R3/R4三轮原图、错误推断、R4退出1和最早私有lambda解析失败全保留，未覆盖为通过。四轮累计24张新图、24次本地按钮回调、新增玩法/账号/PG均0。没有放宽玩法、缺库不得通过、像素一致或界面可用性判据；修正的是测试入口坐标系和渲染读取时序。

原件全部在自有tmpfs压缩，云端验证完整XZ/大小/SHA后分段回传G盘，逐成员核对后才ACK释放RAM。每轮源/原件/生产者保管后，精确核对owner、plan、包、108输入、2148客户端+3覆盖、143运行依赖、321源码、ACK、PID0无容器、无符号链接和生产指纹，才删除本轮唯一输入目录。旧cloudraw、共享UI缓存、A073父依赖和自然周期输入保留。

沿用已登记的功能环境资源门：空闲>3GB、比例>=4.9%、MemAvailable>500MB；实际值、谓词和生产指纹先记日志再断言。这不是容量标准。仅用现有云主机，资源不足CAP保持未通过。生产镜像/启动/环境摘要及health200未变，无部署或release新提交。自然周期APP保持原身份继续运行。GDD两卷SHA保持，合法80/70不钳制；真人排除，本地仅headless/Dummy60/无窗口/低优先级解析，无焦点或桌面输入。

实际数量、资源最低值、独立检查数和文件身份见summary.json。继承的控制台“overlays2”标签不准确，冻结清单、安装回执和独立校验均为3。
