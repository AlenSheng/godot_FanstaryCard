# PR13：真实 PostgreSQL TLS 三项完成

腾讯云运行实际 Godot 网络组件、完整 Program 和隔离 PostgreSQL。LOAD-08.1 三条原用例全部通过：完整 Content-Length、chunked 和正常 TLS EOF 保留真实认证 profile 字节，server-close 后重新连接；截断长度和 chunked 失败且不返回部分成功 body；不受信任证书及超过 2MiB 的响应均被拒绝，后续合法 TLS 请求仍成功。

独立核验真实后端 200 与 body SHA、正常 TLS close_notify、不同重连端口和不受信任 CA 的实际握手拒绝。数据库只读结果证明一名真实认证玩家、一条 session，版本 1、金币和药水及购买流水均为 0。328 个服务器/协议对象与 21 个生产客户端对象匹配当前实现，完整原件通过 G 盘哈希及 gzip CRC，原始管理器日志证明正常退出。

首轮失败原件保留：测试工具对空失败 body 执行哈希 update(empty)，成功 EOF 测试未发送 close_notify；修正这两处测试条件后，120 秒截止和所有原断言保持。只清理本次通过且 G 盘完整核验后的临时输出，私钥只保留在 G 盘原件，不上传仓库。不修改系统信任库或产品代码，不签整体 MAIN 或其他验收层。
