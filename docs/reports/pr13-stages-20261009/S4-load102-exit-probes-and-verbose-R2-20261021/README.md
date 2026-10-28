# R2 一次完整 LIVE 干净执行；R1 资源问题仍未关闭

只补LOAD102-T03当前R2的LIVE执行证据，整项仍Partial。R1一名Native退出时ObjectDB2／资源1告警保持Open，并列为整项验收前必须处理的问题；本轮没有定位原因或修改产品代码，不能说问题已修复或全系列干净。

先执行6个Windows及12个与R1相同Linux引擎／缓存路径的零对局headless探针。覆盖普通退出、真实挂起HTTP、未结束定时器、小包bootstrap的原收尾方法、40470字节合法protobuf的大包后台解码及四个并行收尾读取。全部原生退出0，未产生VM告警。大包分支有实际decode_worker=true和大于8192字节的输入，不是仅靠参数声称执行。512个诊断CardResponse只构造协议大小，不是实际游戏配置／玩家状态。负结果没有证明缺陷不存在，也不支持猜测性加等待或随意清引用。

由于R1完整LIVE确实未通过且这些零局探针没复现，定向重跑这一未通过层一次：新增1个真实世界／4名法师，在与R1相同SUT8eb、客户端父脚本、61001ms停滞年龄注入、真实原_run／expedition／ACK和原协调器上，仅以exec wrapper增加--verbose，原生PID保持。未改变业务逻辑、请求限制、样本标准或超时。专项新增累计2／20世界、8／80玩家周期，其他所有历史预算与失败保留。

R2四个Native全部OS0，verbose日志没有SCRIPT ERROR、ObjectDB泄漏或资源仍在使用。230条原始审计连续，原stagnation分支各一次，四个fallback完成与四个同局ACK、PG四个唯一Dead收据一致，无hold／未确认收据。协调器实际退出1、incomplete_acceptance，gameplay维度Failed，generic4／fallback4／normal0：负例没有变成自然局通过。source／Native PID／用户／match／cycle／收据及ACK分别核对，2209项审查主要为源码hash，不是2209场。

R2的一次干净执行符合该案例本轮功能预期，作为LIVE支持登记；它不会改写R1数据或自动关闭R1问题。整项、长期资源稳定性、原30自然局和容量依然不通过。后续真实ACK截止超时测试保留verbose观察复现，如再现需读取具体资源类再修；不重复已完成业务只为刷绿色。原peer-close丢回复不能改称HTTP deadline超时。

R2原协调器Git元字段仍null，完整代码内容SHA与现有commit／tree／index导出链另行限定；原捕获器没有异常原因，未填造字段。原核验器曾把既有manifest路径误指顶层，改指真实package/control后核对同一原件，旧源码保留，无重开匹配或放宽断言。私有HTTP探针在Native故意退出后出现一次10053迟到写入，作为夹具已知断连保存并补全ConnectionError处理，未当作产品缺陷。

本地全部Godot为headless／Dummy60／CREATE_NO_WINDOW／BelowNormal，无窗口或输入。云端三个自有临时源码根在546成员新原件／代码和父3042完整源码引用全SHA／CRC后，逐owner／源码hash／unit PID0 inactive／自有容器不存在／生产ID镜像启动时刻环境hash与health200校验清理。完整1.50GB原资源在父G档按逐文件SHA复用，本轮不再重复归档；云raw、PG dump、所有本地代码与共享基础缓存保留。生产、Root产品代码、GDD、血量与UI资源未改，无提交推送部署，未做真人或新渲染。

状态保持88 Accepted、36 Partial、8 Ready、44未验收，case/profile缺口172→171。除4个仍缺的LOAD102层级，还明确保留R1强制资源问题，不能仅按缺口数说整体通过。其他131项和全局门保持。

原件：G:\PR13Evidence\load102-exit-diagnostics-and-verbose-LIVE-20261021-originals；父完整源码／失败：G:\PR13Evidence\load102-current-actual-fallback-PG-20261021-originals。
