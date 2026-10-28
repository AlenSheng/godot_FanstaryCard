# PR13 S0：真实 PostgreSQL 响应的 TLS 完整性

计划覆盖 LOAD-08.1 三条原用例，采用实际 Godot 网络组件、完整 Program 和隔离 PostgreSQL；成功响应来自真实认证 profile 字节，故障层仅修改声明的 framing、附加未知 optional 字段或使用不受信任证书。

测试项目采用独立 CA bundle，依据 [Godot 官方 ProjectSettings 文档](https://docs.godotengine.org/en/4.6/classes/class_projectsettings.html#class-projectsettings-property-network-tls-certificate-bundle-override) 配置，不修改系统信任库和生产客户端。证书拒绝、2MiB 上限和截断响应断言均保持。

首轮原件保存到 G 盘及云端。工具修正为空失败 body 的哈希记录跳过 update(empty)，成功的 TLS EOF 响应发送 close_notify；截断负例仍保留非正常终止。120 秒截止时间不变，此阶段不宣称新增 PG 用例通过。
