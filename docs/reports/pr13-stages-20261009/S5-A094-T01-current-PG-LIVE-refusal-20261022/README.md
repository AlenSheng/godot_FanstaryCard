# A09.4-T01：数据库和脚本成功也不能覆盖坏按钮（2026-10-22）

本轮只补LIVE、POSTGRES两层；旧RENDER的54张原图和三轮记录不重复执行或计数。缺失case/profile由64降至62，仍为100 Accepted、24 Partial、8 ReadyForAcceptance，32项未整体验收，六门仍NotAccepted。A09.4还缺T03三层，A09.3前置未Accepted。

当前Server DLL在自有PostgreSQL18.6网络命名空间运行，cwd=/runtime，实际加载本轮私有连接配置。独立C#进程在UI启动前、UI活着时、UI退出后分别提交一份私有marker，再用新连接读回；3次原生退出0，事务号递增，marker行数1/2/3，players和matches始终0。完整PGDMP与pg_dump退出0均保管，未声称做了恢复测试。这个marker只证明实际DB读写和取证关系，不替代游戏资产、结算或既有原生9项PG套件，后者未重跑。

当前Godot进程自己向真实Program发出3次匿名健康HTTP请求，均收到200和原始Healthy正文，PID、正文SHA和服务端进程与中间PG回执关联。UI中的gateway.online仍是明示的启用夹具，右下角保持Disconnected；没有账号登录、实时WS、完整牌组保存或新增玩家/对局。

正式DeckBuilder原SaveDeck回调使用3张本地草稿，仅测英文960×540下正常、故障禁用、恢复3态，共3次鼠标点击尝试。真实pressed计数1/0/1，正对照显示原本地未满20张提示，禁用态无响应、提示为空。脚本退出0，数据库三次均成功；当前未经修改的execution_state仍对禁用态判Failed，其他两态仅ReadyForAcceptance。它是预期拒绝反例通过，不是把坏UI或QA自述升级MAIN Accepted。

3张WebP均使用lossy=false，解码RGBA与引擎原像素SHA逐字节一致。正常与恢复像素完全一致；故障差异仅在按钮区域(791,461)-(934,493)。三态图集及禁用原图已复核，正对照卡面、列表和按钮可读、无旧提示遮挡，蓝金风格一致，无须修改正式UI或ImageGen重出。

本轮native/APP/controller均0，完整原生stdout与engine无脚本/解析错误或资源泄漏。本地仅无窗口、headless、Dummy、60FPS、低优先级解析和C#编译，没有本地PG执行或桌面输入。实际模型/数据库只在现有云主机隔离容器；新增玩法/账号0。没有放宽业务、像素或坏UI必须失败的判据。

所有源、实际观测、三图、当前321编译源与2148客户端+3覆盖、运行依赖身份及生产者在G盘核验。RAM归档624872字节、SHA44ad6b0a89f8f78da958ee8e181f16416ee5847d456c0cda027f8b3653066363，32个成员G校验后才ACK。最终PGdump与控制器元数据也已回存；只在核对owner/plan/包/102输入/全部源与依赖/ACK/PID0无容器/无符号链接/生产指纹后删除本轮唯一输入目录。旧原件、共享UI缓存、A073父依赖和自然周期任务输入保留。

资源门沿用私有功能标准：空闲>3GB、比例>=4.9%、MemAvailable>500MB，实际值和每个谓词先落盘再断言；本轮136次全通过。它不构成容量通过，资源不足CAP按用户要求保留未通过。生产镜像、启动时刻、环境摘要与health200未变，无commit/push/部署。GDD两卷保持原SHA，合法80/70边界不改。真人排除，本例不声称真人体验通过。

详细文件身份、实际数量与最低资源值见summary.json。继承的console标签overlays2不准确，冻结清单、安装与独立复核的覆盖文件数均为3。
