# A04 五个当前 LIVE 边界复核

关闭5个case/profile缺口，142→137；当前92 Accepted／31 Partial／9 Ready，仍40项未整体验收。A04.4三例的OFFLINE、POSTGRES、LIVE证据已齐，但依赖A04.3仍Partial，故只列ReadyForAcceptance。A04.1与A04.3保持Partial，全部全局gate不变。本轮只复核已封存的真实云端原件，新增0场、0账号、0次云调用。

- A04.1-T01：R3全丢实际required及其重放，原始完整READY入口从权威ticket与snapshot恢复，同匹配完成真实周期和清理。
- A04.3-T02：实际Program捕获的DI RoomRegistry单例注入同roomID自有ghost，真实注册两次失败；数据库保持同匹配Launching和一份snapshot，移除精确自有ghost后重试原匹配，四客户端完成、四唯一ACK，无双房或重复资产变动。
- A04.4-T01：当前原始完整压测入口在第一条READY发送前STOP，主程序130、Native0且cleanup通过；真实deadline后成员Removed、准备取消，无本账号收据／ACK／锁。历史Matched记录保留属合法事实。
- A04.4-T02：原Gateway真实socket断开并自动重连，generation、游标及权威room保持正确；实际重放与丢required条件下恢复同匹配并完成原周期。
- A04.4-T03：当前A03.2实际旧M事件与已完成HTTP回调在同session的N交付，N完整业务指纹不变；另由A03.3／A03.4一个真实账号的三局验证旧M成功回包不篡改N、不增加完成数。私有消费时序和原入口范围见父原件，不冒充旧started专例。

当前Gateway、GameStore、HTTP客户端、HTTP schema整文件SHA与R3执行原件相同，原始_run_expedition整函数字节相同。driver仅结束清理和音频退出相关函数发生后续变化；R3已正常ACK且清理无room/ticket，没有进入新增latejoin分支。报告按函数适用范围资格化，不声称旧driver整文件SHA等于当前。23项独立原件核对、父120项复核、G盘原包SHA/CRC、真实Server8eb和Native终态日志均保留。

R1／R2原整体Failed保持原值，不以当前派生裁决改写原件。原注册控制器错误、READY推测snapshot预算耗尽问题及之后的3次推测读取加1次权威启动快照修复均保留。未放宽READY次数、15秒期限、bot填充、HTTP预算、资产正确性或验收标准。

其余七个LIVE缺口继续保留：A04.1暂未found和deadline过期；A04.2前两次send=false第三次成功、accepted后required、第二局旧started；A04.3真实保存失败与MarkRunning已提交后丢结果。连续三次发送失败不能替代两次失败后成功，旧snapshot或HTTP回包不能替代旧started，registry失败不能替代另两处启动故障。

完整GDD两卷SHA已重核；Mage70、Priest80、Guardian100及用户已确认80/70合法边界保持。无本地GUI／全屏／焦点／输入、无新UI资源或ImageGen；无新增提交、推送、生产部署。容量仅限现有云主机，资源不足项继续未通过，真人体验仍排除。新报告封存到G盘后再更新当前指针。
