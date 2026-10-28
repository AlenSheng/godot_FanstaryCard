# PR13 B08.3：当前来源的只读 S4 审查

原正式实验 108 单元、216,000 场、108,000 pairs，以及原 R7 的 54 个渲染矩阵行和 9 张实际图像审查均有通过证据；本阶段核对了它们的原件与来源。当前集成版本的等价性尚未证明，因此 S4 保持 Partial，MASTER 的六个 EXPERIMENT/RENDER 缺口未补，MAIN 和整个任务未通过。

正式实验原来源为 `3a984bc64f5346b7f1d134926deec54be928a060`，统计分析来源为 `49ba3183c247282083f558fd3c3f528d2d476fb3`。原 108 个 G 备份收据和云端清理收据的原字节 SHA 与已发布索引逐项相同，原生结果与索引一致，原件保持完整矩阵、每臂 1,000 样本、每单元 4 个独立负对照及全结局分布。4,127,660 条实际 cast、167,117 Victory、48,883 Death、0 Censored/0 Error 全部保留；没有在本地重算业务或统计 oracle，也未重跑完整实验。详见 [原实验](original-experiment/) 和 [审计](audit.json)。

渲染原来源为 `671299f3c118a195c47cc7ce07d4d68dc84b75f0`，原生向量来源为 `014a601c9a72a8bd2aec357e56a349914f6613f4`。三个 case 各自 18 个 zh-CN/en × 1920×1080/1280×720/960×540 × 30/60/144 配置实际通过、干净退出、拥有容器已删除，合计 432 个 native witness。9 张 PNG 的实际查看记录与 G 原字节 SHA 匹配；它们只代表最终 English 960×540/60 截图，未把其余矩阵行冒充逐张人工查看，也不作硬件 FPS 或音频验收。详见 [原渲染](original-render/)。

新审计工具直接读取 actual G source/input hash maps 和原 Git、当前 Git blob 原字节，使用有界流式 SHA，不凭 Domain DLL 类推源码。当前冻结来源为 `18ae9d4e949cbdb4882b6469aff016f6568fb0fd`。原实验与原生向量的 authored Domain 34 个源/工程文件、所选配置 3 文件均与当前字节一致；统计六文件也实比原始记录和 Git 来源。历史 obj/bin/依赖产物即便曾被 Git 跟踪也单独归类，不冒充业务源。渲染生成 fixture 没有虚构 Git blob，另以原 G native vectors 的 SHA `f384facee3a0907075672bd91b566e07bc5e48e17ace772cf6cbe2c6b192b84c` 实际连接。

目前变化包含 Numerics 的 Program、CombatExperience、CapEffectiveExperiment，以及共享 UI 的 numerical_details、monster_pool_view；新增后续工具/test 另列。[静态调用范围审查](static-call-scope-review.json) 记录 Program 新增 cap 入口、CombatExperience 可选 null observer 和未变化的 TuningRecoveryExperiment 调用范围。这些静态信息帮助缩小后续验证，不构成原编译程序集与当前执行等价的通过证据。没有声称完整旧 tree 与当前 tree 一致，所有原已通过报告保持原来源标签。

下一步是单独冻结当前运行时与所选输入，在云端做原/当前 36 families × 3 paired seeds × 2 arms 的小范围完整 cast/encounter 对照，并用原冻结 native fixture 验证当前渲染及变化的共享 UI。这些新证据应单独记录后再考虑登记。[补单候选](register-supplement-candidates.json) 包含三项原已执行的 EXPERIMENT/RENDER 记录，但 proof 的 `source_inputs_match_git:false`，当前不得应用。

B08.2 的 [长时关闭检查原件](dependency-B08.2-shutdown.original.json) 保持 `long_normal_shutdown_clean:false` 和 `full_fix_verified:false`；本报告不接受该依赖、不签 MAIN。所有复制原件保留原始字节，新文本为 UTF-8 LF，目录 `-text` 的 [manifest](manifest.json) 记录精确提交字节 SHA256/Git blob SHA；manifest 不递归列入自身。
