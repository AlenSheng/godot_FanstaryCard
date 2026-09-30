# 有界生命周期批次

稳定代码/测试候选 `38c2caccb5f8327f52d97dffb3b9f9303360dd46`；生产逻辑与f93e32da逐文件相同，本批只新增或扩展7个测试文件。实际源码起跑与候选输入等价见[source-proof.json](source-proof.json)，两个纯提交来源分列，不声称所有测试在同一SHA执行。

源码内部freshbuild零警告/错误；针对13/13、非PG206/206通过（含3项Caddy重复，不相加覆盖）；真实READY新增5/5纯提交通过，另有8/8开发回归。新.NET7case含两个Register组件SupportOnly，不能当完整Program/Godot/LIVE profile。

真实生产Godot三局中，第二ACK提交后丢响应或提交前丢请求，各3个不同match、3次完成，4次HTTP尝试；STOP在ACK提交前/后各started1/completed0/cancelled1，持久ACK1，清理Passed。三局使用额外合法extract/abandon驱动，不是完整玩法/Boss。

注册真Program+私有PG在UPDATE1/Idle响应丢失后重放UPDATE0，四个ticket WS路由及实际OS重启仍同match/room，资产只预留一次。Register冲突的真实组件连续2次失败再恢复保留SupportOnly。READY仅丢原始PB帧；重放SHA/序号完全一致，全3发送丢失经原15s deadline Removed/Cancelled/释放/路由清理。

[REPORT.json](REPORT.json)、[CASE_MATRIX.json](CASE_MATRIX.json)供独立裁决OFFLINE/POSTGRES部分证据。8个原case均PartialEvidence，132项仍53Partial/76NotRevalidated/3Blocked/0Accepted，G0–G5未签署。原27回执与396覆盖分开。新故障没证明生产缺陷，不伪造修复前失败；已保留所有夹具错误原raw。

临时服务/PG/proxy停止，自有schemas0；未线上操作、未CI重试、未上传4raw、未合并。UI/协议本批0修改；相对de115运行逻辑路径仍只有gateway.gd/game_store.gd/gameplay_load_client.gd。下一项为pending holds/busy旧receipt、STOP settlement/reconnect await及真实跨局旧事件；完整LIVE/RENDER/人工仍缺。

补充：注册夹具已兼容自有loopback TCP的PG服务，保持原超时；38c2cacc的TCP3/3与Unix3/3定向验证通过。之前TCP夹具超时原证据保留，修复的是relay默认Nagle延迟。GitHub仍未执行；不是CI绿灯。源码一致、派生报告和生成产物dirty事实分开记录。
