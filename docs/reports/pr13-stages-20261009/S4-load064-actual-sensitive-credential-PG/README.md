# PR13 LOAD-06.4-T03 实际会话／票据公共报告拒绝结果

腾讯云外层十方法全部通过、零失败、零跳过、无 OOM。当前 SessionToken 和 IdentityRepository 生成本测试私有 schema 的真实会话，前后按hash查询有效；当前 RealtimeTicketStore 签发真实票据并证实只能消费一次。当前 pr13_public_evidence.inspect_public 与 validated_files 对实际 token 与票据正文候选分别拒绝，原私有候选字节不改。仅摘要和拒绝原因的脱敏元数据正向审查通过，不含原值。

实际默认 Guardian 20卡房间快照和房间持久字节不变，生产 Domain parent SHA 保持。完整672原件和归档SHA／CRC、全部成员、328当前源码核对。G:/PR13Evidence/LOAD064-sensitive-PG-r1 及对应私有归档明确包含本次已结束隔离环境的生成测试凭据原件；生产凭据不涉及。公开阶段只复制声明的测试源、SHA清单、脱敏回执和日志，不复制 owned-sensitive-candidates，所有复制文件再次检验无原token或票据字符串；适用文本／JSON按当前公共审查器检查。

终态无占用且G完整验证后只清理本次通过的 work／persistent-output，回收48,775,168已分配字节。共享输入及旧失败原件保留。本次只对应 POSTGRES 敏感信息报告边界，不能替代 LIVE 全客户端隐私、TLS安全或MAIN验收；下一阶段登记精确格。
