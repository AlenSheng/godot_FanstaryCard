# S0 选牌预览与目标按钮布局/输入合同

基线 `2f8eaf06c41643e80464f21cae00d099714e140f`。根据已冻结的 PR13_TARGET_PREVIEW_OVERLAP_20261010.json，使用腾讯云 X11/Mesa 实际项目场景验证两种语言、三种分辨率、2/3 个存活目标、选牌/未选牌、中心/下半部点击，共 48 行。

每行记录实际控件边界、预览是否与按钮相交、窗口及图像像素尺寸、鼠标命中控件，以及现有目标选择命令是否收到预定目标。选牌顺序必须保留。通过条件不允许预览遮挡合法点击；使用正常 GUI 输入路由，不直接触发按钮 pressed 信号。

输入坐标由 CanvasItem.get_global_transform_with_canvas 转换到视口，再以 Viewport.push_input 的 in_local_coords=true 传入移动、按下和松开事件。依据 [Godot CanvasItem 文档](https://docs.godotengine.org/en/stable/classes/class_canvasitem.html#class-canvasitem-method-get-global-transform-with-canvas) 和 [Viewport 输入文档](https://docs.godotengine.org/en/stable/classes/class_viewport.html#class-viewport-method-push-input)。最终判断仍以真实入口的命令观察和画面为准。

修前与修后分别保存 8 张实际英文窄屏图像、完整 48 行观察、原始日志、源码和退出码。每轮限制 180 秒、1 CPU、1.5 GiB 内存；500,000,000 字节可用内存及 15% 磁盘停止线保留。只使用已核验的本任务快照资源，不创建真人或玩家压力会话。

本项为布局/受控指针交互验证。原自然多局、容量、真人及其他未覆盖层保持原状态；修复与验证各阶段独立总结并直接上传 release。
