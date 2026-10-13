# PR13 B12真实源表重导与旧包不同步数据库验证

使用当前工作簿和当前ConfigExporter，先实际重导原工作簿并核对双方六个发布成员字节一致。在隔离工作簿只改Cards中C01的name文本一格，其他ZIP成员及语义单元格保持；不改ID、卡值、品质、成本、规则或生产源。用相同版本由真实导出器再次生成完整server/client包，验证各自嵌入内容hash有效，输出不同于旧发布包。没有手改生成bytes。

真实PG新增用例持有当前配置、20张默认守护者房间，执行当前完整freeze来源检查，预期仅因Source re-export differs from frozen published config而拒绝且不创建运行阶段。旧PG房间快照、持久字节和matches/snapshot数量必须保持不变。隔离源码只追加一个测试方法，反向去除即原Git文件；编译并执行原九项PG合同加此一项，十项零跳过。

保持原内存/磁盘线、原截止及单工作进程，在B04物理批次边界执行。完整原件持久保存、转存G核验后回收拥有副本，共享输入和失败原件保留。S0尚未执行，不关闭POSTGRES、EXPERIMENT、RENDER或MAIN，不启用任何生产候选。
