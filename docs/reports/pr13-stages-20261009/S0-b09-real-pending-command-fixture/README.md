# B09 实际待处理命令记录

R3 编译零警告零错误，四个原生阶段及三批原始 Godot 编码均通过：63 条命令、99 次路由、72 行事件、189 原始帧与 45 重放帧。接收 fixture 的 JSON 输出成功，但引擎日志存在九次 SCRIPT ERROR，因 fixture 手写待处理记录缺少 retry；严格验收正确拒绝。

改为由 GameStore 实际 _send_queued_command 创建完整记录；测试网关只截获网络发送并保留预先冻结的 request ID 和上下文。真实 GameStore 不变。接下来使用原始 native 事件单独运行当前 Godot 接收端，旧 source SHA 保留原标签，仍未授予通过。
