# PR13 LOAD-06.4-T03 实际会话与票据公共报告边界补测

腾讯云隔离 PostgreSQL 创建真实一次性测试会话，使用当前 SessionToken.Create／Hash 与 IdentityRepository 建立并查询身份。当前 RealtimeTicketStore 签发真实票据。实际 token 与票据正文分别写入私有候选 JSON；当前 pr13_public_evidence.inspect_public 及 validated_files 都必须以对应敏感字段理由拒绝，原私有候选字节不改。

只输出候选文件名、大小、SHA和拒绝原因；脱敏元数据再次通过公共审查。会话查询前后保持有效、票据只能消费一次，真实默认 Guardian 20卡房间完整快照和房间持久字节不变。正式数据／凭据和源码不改，原九回归加新增一方法共十方法执行，生产Domain parent SHA保持。

完整私有 G 归档明确包含本次生成的已结束隔离环境测试凭据原件，绝非生产凭据；descriptor 显式区别 production_credentials_not_included 与 generated_ephemeral_test_credentials_included_in_private_G_archive，禁止以含凭据归档冒充公共档。完整原件仅存 G:/PR13Evidence/LOAD064-sensitive-PG-r1，Git报告只复制声明的源代码、脱敏回执和安全结果，不复制候选正文；上传前对公共文件再次按现有审查器核对。

共享锁等待B04当前包，500MB内存／15%云盘安全线不变。终态无占用且G完整SHA／CRC后清理本次通过副本；不据此声明LIVE、所有客户端隐私或MAIN通过。当前尚未执行，所有验收状态不变。
