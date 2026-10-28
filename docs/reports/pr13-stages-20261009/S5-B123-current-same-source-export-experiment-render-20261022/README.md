# B12.3-T01 当前同源重导：EXPERIMENT / RENDER闭合

本次只补齐T01的EXPERIMENT和RENDER，缺失案例/层级109→107；100 Accepted、24 Partial、8 Ready、32项未验收以及全部全局门不变。B12.3仍有配置回滚和正式误启的实验/渲染缺口，B12.1前置未Accepted，因此本项不升整任务。

当前51份Exporter/Numerics/Domain/配置源在独立副本中通过SDK10.0.400新编译，原工作树未写编译产物。冻结同一c5cffc9b工作簿，经真实ConfigExporter独立导出两次，server/client四份bytes、当前已发布两端bytes及实际实验Domain内嵌资源逐字节相同：raw SHA49ce83c0aacbe18f57f84a5b58d682b08c452026de5588dbd7c6be89eac48a87。包内canonical content hash与.sha256声明另行核对，不混同整个文件的raw SHA。随后用原Python客户端导出器从新bytes生成catalog和描述，语义与正式数据一致，真实渲染进程消费这些新生成文件。

实际领域遭遇CLI执行Mage/default/O1/baseline_all_hand，三个预登记seed、Baseline与CoreCardsSpent各3次，共6次，errors0、均保留完整结果。当前合法牌表找不到同品质/同解锁成本的主题替换，所以CLI只生成default；私有检查器把上限12误写为必须精确12，最后的checker断言失败，原源码/原生输出和Native0保留。按实际manifest有1牌组×2profile×3seed复核为6次，不补跑、不改价格、不增卡、不声称完成主题矩阵。形式默认仍全部off，实验隔离候选不代表正式启用；六次只证明同源配置绑定，不能给平衡、收益区间、95%结论或容量通过。

当前实验Domain SHA为db2a29cd07b04b96999167b781a2982d8aed3515c6081d12d73d32763a571d9f，Simulator SHA10cb4613ca029bb5ffd7f5814336a531345e4a1e09d1390db359f378398943f0。它们来自本轮真实编译，不拿旧dll冒认当前。Root HEAD86只是引用，当前源文件摘要和私有覆盖独立固定。

云端使用现有Xvfb/Mesa及Godot4.7.2，在2语言×3尺寸的6个场景中实际配置正式CardView，代表卡C01、MAG-01、GUA-01，各完成原生viewport鼠标选中和还原，合计18组。实际生成bytes与catalog摘要、文字/效果、PNG尺寸、树就绪及非空采样可关联；进程退出0，完整stdout/engine无脚本/解析/泄漏错误。原图6张逐张查看，正式218×376/scale1尺寸文字、金框、卡图及职业标识一致，核心文本无遮挡，选择还原有效，不需要重生美术。这里只验证新生成配置的代表性正式卡面消费，不授予全部卡图、全职业玩法或整体体验通过。

渲染三次尝试均保留：R1包镜像摘要少3位，仅61hex，Docker125拒绝，Godot没有启动，没有下载/安装新镜像；R2修为既有64hex镜像，Native6/18组交互正常，但私有夹具放大1.8导致文字软化，原图照存；R3只把私有显示改回正式scale1并重新完成相同6/18矩阵。没有改正式字体、卡框、资源或产品代码，没有重跑6场领域实验。此前测试标准未放宽，检查器错误与展示夹具修订不变更游戏规则。

本地全部原生进程为隐藏控制台、低优先级/一编译worker，Godot只headless/Dummy60解析，没有本地PG、GPU取图、桌面焦点或真人输入。真实图只在既有云主机上生成；本轮无网络登录账号、真实游戏服务器房间或PG，6为领域模型遭遇而非网络对局。

187项独立复核通过，原生源/编译/输出、原错误和三轮像素/源码等802份原件/生产者已G保管。原渲染56份加正式尺寸补拍38份均逐文件SHA核验，并关联此前完整G源父包。首次清理SSH中断后未盲目重发，先只读确认三目录都存在、PID0、无所属容器和生产指纹正常，再逐目录验证owner/plan/archive/无符号链接后精确清理；原cloud raw与shared cache保留，生产健康200不变。没有提交、推送release或部署，release仍86ddee23。
