# PR13 配置回滚 POSTGRES 证据核对

腾讯云原 current-pg-numerical-nine-r10 批次执行了九个未跳过的数据库原生方法。此次复核其 New_policy_source_changes_new_rooms_without_changing_current_persisted_room、PR13-B02.4-T01 原始数据库回执以及全部原件，按原断言同时映射 A08.3-T02。没有再次运行或增加样本数量。

默认旧房间持久数据和完整恢复快照保持不变；候选源创建新房间，随后源回滚到默认值，新建回滚房间采用默认配置，而已有候选房间恢复后仍锁定候选配置。三房间身份不同，默认与回滚配置哈希一致，候选配置哈希不同。范围仅限本次隔离 NumericalRules 配置源和持久房间，不能推断任意配置包、生产部署或 LIVE 行为。

原 TRX 九条执行和通过、零跳过，精确所选方法通过。当前 release 与原 328 个服务端／协议来源逐字节一致；G 盘 2,199 个原件逐个重算哈希，归档 SHA 和 CRC 再核对通过。仅补齐一个 POSTGRES 缺口，从 112 降到 111；A08.3 变为 ReadyForAcceptance，依赖、门禁和 MAIN 尚未自动签署。
