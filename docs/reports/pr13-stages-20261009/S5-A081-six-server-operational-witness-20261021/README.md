# A08.1 六组历史运行服务端来源关联推进，整项未验收

本轮新增163项只读关联核对，补核此前六份大报告的服务端运行元件。A08.1仍ReadyForAcceptance，A08.2/A08.3不自动接受；仍100 Accepted／24 Partial／8 Ready，32项未整体验收、118个case/profile缺口，所有global gate保持。本轮没有新增规范案例/profile通过或新容量测试。

第一组20261009运行的execution与原runtime记录一致：实际旧server实例ID、host PID、image113d以及镜像revision da845均有原记录。执行过的isolated_runtime.py完整SHA1104同时等于Git da845原blob；启动命令使用所选镜像，除/evidence外未替换/app程序集。当前同一内容寻址的保留镜像被docker create成完全未启动的自有容器，只docker cp三份程序集：Server838688…、Domain8ecc0d…、Contracts7cbd55…。始终State=created、PID0、StartedAt为零，没有启动镜像代码、游戏、数据库或新账号。此证明是同一不可变镜像当前内容，不补造当年运行中overlay的哈希，也不把revision标签单独当编译来源证明。

后五组20261018—19容量运行，原service-ready真实记录的Server DLL为eaaa9c…、Domain为fdb611…、Contracts为013c16…，并非后来8eb当前程序集。原输入stage/installed控制副本、控制manifest SHA、source-cache-manifest、全部21份compiled文件声明与实际G盘缓存tar原字节逐一匹配。封存包完整SHA67dce9…也与原G-receipt一致。原Docker create命令明确使用不可变SDK/runtime镜像180f52…，并只读挂载实际compiled_root到/runtime；该镜像digest不等于挂载的Server DLL，也不能从production_before.image7c…推断测试镜像。原app容器ID、各自容器内PID及owner/unit分别对账，多个命名空间相同PID不合并成同一进程。

两类Domain程序集的PE元数据资源均读出120495字节FantasyCard.Config.fantasycard.config.bytes，实际SHA同为49ce83…。使用有界.NET PE元数据读取器，仅解析字节，没有Assembly.Load或执行SUT；因此代码/Domain哈希不同而包相同的事实得到实物支持。这里的游戏嵌入包hash与原otel/prometheus监控配置hash分开，也不据此推断环境覆盖或每个room锁定策略全部相同。

四组后期服务的native_finish明确确认最终报告SHA；另一组ramp50-R1服务先失败，原service_result没有native_finish，但原finish.request内的客户端最终报告SHA与实物一致。该组只登记“客户端finish已记录、服务未确认”，不补造服务确认或整轮完成。首次复核器曾要求每组都有服务确认并触发断言；原检查脚本与失败来源保留，后续按这两种证据级别分类，不改变原服务失败或容量判定。

所有原50/100容量失败、资源停止、未知状态、旧预算、actor/对局数量保持原样，没有用当前较新成功结果覆盖它们。当前8eb、最新HEAD86ddee23和marker前进都没有被用来重标历史执行。本轮没有重建或重跑旧容量，也不宣称恢复原cb96/a33已删除运行文件。

嵌入包、镜像及缓存21文件、原controller/blob和运行记录、解析器编译/实际输出及163核对原件已G67逐成员SHA/CRC封存。其后再次核对image-reader容器ID/name/owner/image/State=created/PID0/从未启动，以及三DLL和tar SHA，再只移除该自有未启动容器。原image113d、云端证据目录、G、本地代码、共享缓存全部保留；生产容器指纹与当次health200不变，这不是永久健康承诺或生产回滚。

A08.1的完整MAIN范围仍未完成：其他运行族、压缩包与远端血缘和独立编译输入证明待关联；四个原editor运行未记录原引擎哈希，当前路径不能补出旧字节；第一组运行overlay没有原SHA；历史删除原件继续missing。六组补核不能代替全部范围，因此不签整项通过。

全程无Godot窗口/全屏/焦点/输入，只有后台低优先级单worker元数据工具与解析器编译、只读旧镜像内容提取；没有PG、游戏、SUT启动或生产/Git变更。完整GDD两卷快照、合法80/70、基础L护盾、真人排除、现有云主机限制及所有测试预算保持；无UI资源修改、新像素验收或ImageGen。
