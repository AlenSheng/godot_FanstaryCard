# A04.1-T01 公网 READY 通知丢失复核

一个真实 Windows Godot 客户端经本机临时中继连接测试服 HTTPS/WSS。中继丢弃全部 `room.ready_required` 原始消息及重放，未生成协议消息。实际丢弃 2 份通知，客户端接收 0 份，仍通过权威 ticket 查询发送 READY，并收到同一 match/room 的 accepted、started 和 snapshot。独立 Protobuf 解码、74 条连续原始事件及 PostgreSQL 关联共同支持本例功能通过。

生产清理 Bootstrap 与数据库后置状态均通过：无活动真人路由、待处理 hold、装备锁定或排队 ticket；收尾结算对应一条 ACK 幂等记录。公网服务和原监控未重启，环境配置未修改。测试保留磁盘及内存 5% 余量。

原生载荷报告因指定功能边界 STOP 保持 `ok=false`；本例正常通关周期计数为 0。首轮 TLS 基础失败及第二轮归属监控 STOP 原件均保留，未计为通过。任务内 CA 仅排除现有 Windows 信任库的过期项，继续严格验证主机名与证书，未改全局信任库。

本报告仅补 A04.1-T01 的 LIVE 功能证据，不涵盖 T02/T03、整组 A04、十账号三局、RENDER 或容量验收。中继的 HTTP 连接方式不用于默认公网路径的性能判断。验收 register、gate 和 MAIN 均未更改。

完整原件和源文件已在 G 盘归档，逐成员 SHA256 与压缩 CRC 均校验通过。校验值与精确范围见 `summary.json`；原始数据、临时脚本和 CA 文件不随正式报告提交。
