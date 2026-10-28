# 正确快照请求命令

R2 编译通过，但首个开发正式规则路线后，采集请求使用了事件名 room.snapshot，真实 codec 正确拒绝。请求应为现有协议 room.snapshot.read，回应仍是 room.snapshot；已修正测试调用，生产 codec/router 没有修改。R2 整体失败及旧源/日志保留，新 R3 使用独立单元，正式 36000 样本尚未运行。
