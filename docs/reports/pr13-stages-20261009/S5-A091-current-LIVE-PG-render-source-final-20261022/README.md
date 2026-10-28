# A09.1 三个来源反例的九个机器层闭合，整项仍Partial

本次只关闭T01/T02/T03各LIVE/POSTGRES/RENDER三层，77→68。100 Accepted、24 Partial、8 Ready、32项未验收及六道全局门不变。A09.1自身显式缺层全空，但A07.4等前置未Accepted，且本轮原控制器保护失败未取得失败采样值，任务仍Partial。下述独立功能证据不等于原控制器、资源稳定性、容量或整体验收通过。

当前Server dd56dfc4、Domain f91d19f7、Contracts f532671e、201b00de原生测试DLL及143运行依赖全部按原件SHA固定。2148客户端源加私有观察覆盖在同一R3执行，产品源/资源没有改动。原A05健康旧房/新房C#断言不改，180秒期限和bot-fill30秒不改；原生退出0，TRX 1 Passed、0 Skip，实际约2分34秒。真实本地认证、PB HTTP/WebSocket、PG权威持久化、正式Godot界面与实际OS服务重启均参与。三反例共享同一轮两个逻辑房间、五个自动化账号、两次服务进程和六个真实结算ACK，不冒充三个独立完整探险或真人。

T01在真实N已经运行时，把独占源副本321份当前源真实提交为Git A，再只在未编译副本CombatResolver.cs追加注释提交为B。当前生产source_references实际解析A/B，different_sources=true、runtime_execution_verified=false；原冻结收据与运行二进制保持A身份。独立复核逐份读取实际Git A对象，与321份当前源SHA一致。私有A/B不是根仓库或线上部署版本，根HEAD仍86ddee23，不把新HEAD或marker当作重建/运行证明。

T02从同一在线Godot接收的两次权威房间观测产生旧/新fixture。真实validated_files拒绝旧manifest，对新字节重算摘要后验证通过；保存两份真实观测，不合成玩法状态。每个来源检查点都有真实PG前后repeatable-read旁证，六份SQL原件关联实际UID、match/room及运行schema，资产SHA逐对不变，SQL旁证不新建领域模型。

T03使用同一Godot客户端实际成功M结算ACK，PG中存在对应M、UID且acknowledged_at非空。原事件有真实native run_id、PID/epoch、client/UID、match身份，reconcile_cycles计算ack1、completed0；副本只移除run_id，另加明确声明的agent哨兵，真实代码报missing_context、ack0/completed0，不拿agentID填runID，不捏造完成周期。原native run_id常量owned-a05-runtime本身不能单独作全局唯一键，外层R3 run/container、PID/epoch、UID和match一起保留。

当前N的实际Mage PVE界面，三个检查点各中英×960×540/1280×720/1920×1080，共18张全尺寸无损WebP。每张解码RGBA与引擎原像素SHA逐字节相等，18条逐帧JSONL也与最终原生结果相等。两个图集逐幅审阅，另看4张原尺寸：关键卡面、文字和出牌按钮无重大遮挡，蓝金风格统一，无需重出资源。本轮只覆盖该Mage同轮来源界面，不推成其他职业、全部路线、全部本地化或完整UI可用性验收。HP70→67→64→58来自真实PVE过程，不是夹血或故障注入；GDD70/80/100和合法80/70不改、不误报。

## 重点：三轮失败、修正、额外预算与监控边界

R1控制器保护触发，原生私有观察随后在没有有效新房间/在线上下文的T03断言失败并提前终止VSTest，退出143；不授任何层。前置画面采集可能扰动下一局排队窗口，具体原Xunit原因未完整取得，不能写成已证明的产品故障。R2将检查点移到真实N以后，整个/evidence放入384MiB tmpfs、/screens256MiB，观察错误写false收据而不提前中止原驱动，并逐帧保存JSONL；原生通过，但18图像素核对失败。实际save_webp(path,lossy,quality)误传lossy=true，quality1.0仍有损，原声明native_lossless_WebP=true不正确。实际ClassDB接口、VP8块和18个RGBA差异均保留，不能把R2有损原图重编码后冒充原像素。R3仅把私有采集参数改为false，先以零玩法/认证/PG的headless编码校准逐字节验证，再进行本轮真实复验。产品源码、资源和规则不变。

原失败样本不归零。R1自动生成房间数不能由现有字段完整枚举，按6个房间作保守规划预留而非观测值；R2和R3各实际两个房间/五个自动化账号。三轮累计规划上限10逻辑房间/15自动化账号，均单独登记，不将规划数冒充实际统计。原C#180秒、bot-fill30秒、业务、容量和无损图质标准未放宽；功能作业磁盘>=4.9%且>3GB、MemAvailable>500MB的已说明保护门仍保留，不能据此给资源不足CAP通过。

R3原生业务和画面完成后，原控制器复合保护断言中止监控，原ok=false/堆栈不改。已保存483个成功样本中最低MemAvailable约1.84GB、最低磁盘比例约5.0277%，都高于门线；但失败瞬间四项条件值没有先落盘，不能反推具体是磁盘、内存或生产指纹/健康的哪项，也不能直接宣称内存耗尽或生产故障。原控制器仍未通过，资源连续稳定性不授通过。未来私有监控应先保存全部实际条件值和各谓词再断言；本次不重跑已通过的业务来掩盖这个监控缺口。

第一份SSH原图归档虽然exit0，实际23,602,661字节末尾被截断，XZ完整性检查失败，原文件保留且没有发ACK。直接从仍在同一个APP内存中的同一批原件预建有效XZ到自有/tmp内存，云端验证完整归档为23,703,608字节、SHA f17f5cd8ff2abcfafe1485a87fb0bba5b8053038830168d8ab191930d9c4ece2，再分六段下载，校验总SHA及993成员SHA后才写G保管ACK。恢复传输没有新运行任何业务测试。截断副本、六段原始传输、有效归档、原生计数和所有旧失败分开保管。

独立复核426项来源/原生/PG/像素检查通过。G完整保管后独立确认APP实际退出0/OOMfalse、保存自有PG最终dump并按owner和容器ID清理；这个独立cleanup ok不是给原controller false改判。全部源/原件/失败生产者1153份G托管后，唯一R3输入目录owner/包/plan/101输入/2148源与覆盖/143运行文件/321源/ACK/PID0/无容器/无符号链接/生产指纹两次核验，精确清理。R1/R2输入此前也已保管后清理，所有旧cloudraw、shared UI与A073父依赖保留。生产镜像、启动时刻、环境摘要和health200未变；不声称全程生产健康已获验证。

真人按用户要求排除，actual_human_accepted=false。仅现有云主机；本地Godot始终headless/Dummy/CNO/低优先级，解析和编码校准零玩法样本，无桌面窗口/焦点。没有产品UI/美术/工作簿/GDD修改，没有commit、push或部署。下一步A09.2正常三局、A09.4和历史来源等未完缺口，不重跑本项已闭三个来源反例替代上游。
