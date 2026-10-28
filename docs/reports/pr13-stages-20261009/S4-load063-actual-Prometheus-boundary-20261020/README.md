# 真实 OTLP 与 Prometheus 查询通过

LOAD-06.3-T03 LIVE使用完整当前Program、第一方Protobuf HTTP和二进制WebSocket、原有隔离PG及官方Prometheus3.13.4。100个不同的已持久化match-ID上下文均得到权威拒绝；是身份夹具，不是100场自然战斗。没有创建新对局或账号。

实际SDK发送的5批OTLP protobuf报文逐字节保存，透明转发体SHA一致，真实接收端全部HTTP200。按[OpenTelemetry官方schema](https://github.com/open-telemetry/opentelemetry-proto/blob/main/opentelemetry/proto/metrics/v1/metrics.proto)独立解码，目标duration单位ms、累计直方图、数据点属性仅phase。真实Prometheus查询的完整series前后均36条，包含所有标签的键集合完全相等；SocketSend计数1→101。观察到SocketGateWait和SocketSend两个实际phase，业务不随100个ID增加series。完整六phase枚举由此前实际生产者记录另行证明，不声称本次导出了全部六phase。

**失败与口径修正明确保留。** 首轮过早查询，只有先到达的Actor导出，SocketSend查询为空；控制器失败，等待客户端自身120s期限后正常清理。这轮新上下文命令0条，原日志／64批报文保留。第二轮等待真实SocketSend计数可查后使用同一份100条预留额度，未重复增加预算。准备检查曾把21个运行文件写成21个DLL，及独立读取schema曾遇GBK解码错误，均为工具错误，修正后没有重跑业务测试。

**标签解释修正。** 原测试草案笼统禁止GUID值，但当前Program的AddService会生成固定的服务实例资源ID，Prometheus据此保留instance标签。它是进程基础设施身份，和对局业务ID不同；原值完整保留，不删除或改为常量。所有36条完整series包含该instance且前后相等，没有match/player/request标签或这些业务ID值。按规范“无高基数业务label”审查，没有放宽业务判据。

独立78项核验通过。累计104个match记录及292条命令，仍沿用200世界／300命令上限，首轮0命令也保留，不重置额度。本地均隐藏、低于正常优先级，无Godot窗口／焦点／输入；完整Program、客户端、Prometheus均原生退出0，PG干净停止。原件、官方工具、实际数据报文、两轮TSDB和实际PG快照保存在G盘并逐成员SHA/CRC验证。接收与查询接口采用[Prometheus官方OTLP文档](https://prometheus.io/docs/guides/opentelemetry/)及[查询API文档](https://prometheus.io/docs/prometheus/latest/querying/api/)。

原件：G:\PR13Evidence\load063-actual-prometheus-boundary-20261020-originals。
