# 固定 PR13 / UI 隔离交叉回归

本批把 PR13 `de1157fdf490a5bce3ba888c07519fc957c46782` 与 UI `070c7b441ffc5dbd7253aea1dcbc9793b1fef449` 组合到独立分支 `fix/ui-pr13-integration-de1157f-20260930`。实际受测源提交是 **`ea94d97fe30d3622777f9190d7696c640f70b02a`**。其后的交付提交只增加证据和索引工具，生产代码没有变化。

审阅基准分支 `audit/pr13-de1157f-ui-base-20260930` 固定在 de1157f；它不跟随 PR13 后续推进。本批未写入 PR13 / PR16 原分支，未合并、部署或推送 release / main。PR13 后续证据提交 0bceca3 不改变本批输入；后续 ACK / READY / STOP / 旧回调批次不在本结论范围。

组合前后的 **5803 个既有 PR13 非 UI blob 完全一致**。范围是 de1157f 所有 `client/ui/`、`client/assets/` 以外的既有文件，包括协议、网络、store、服务端、原始测试、文档、工具及配置。详见 [逐文件保留清单](non-ui-blobs-01.json)、其余 02–06 分卷，以及 [最终工作树核验](preservation-final.json)。没有显示 hunk 冲突，解决清单为空。九个 UI 脚本、manifest 和三个新增运行时资源文件，共 13 个 UI / 资源路径与 UI070 输入 blob 完全一致。

以下 UI 分支修改没有覆盖 PR13 既有文件：`client/tests/art_preview.gd`、`client/tests/test_boxspirit_instances.gd`、`docs/UI_ASSET_MASTER_CHECKLIST.md`、`docs/UI_MISSING_ASSETS.md`、`docs/ui_missing_assets.json`。修正版美术与 Boxspirit 夹具另存为 `ui_integration_art_preview.gd` / `ui_integration_boxspirit_instances.gd`；新增集成场景使用 PR13 原 store 和 gateway。新增 UI runner 显式执行原 PR13 target confirmation 测试。

[输入和路径映射](inputs-and-preservation.json) 记录全部接入路径、原始 UI patch hash、跳过项和 apply 日志；[production-ui.patch.gz](production-ui.patch.gz) 保存九个生产 UI 脚本的精确压缩差异。新证据不与 [历史 UI 审计](../ui-style-20260930/README.md) 的 530 / 1066 图合计。

| 新执行检查 | 退出码 / 结果 | 证据 |
| --- | --- | --- |
| Godot 4.7.2 固定源资源导入 | 0，无脚本 / 解析错误 | [导入结果](import-result.json) |
| 新 UI runner + 原 PR13 target 模块 | 0，19/19 模块；2640 卡牌说明变体 | [native.json](native.json) |
| 官方 C# protobuf | 0，25 PASS，8 个 Google.Protobuf golden vectors | [日志](logs/protocol-csharp.log) |
| 协议生成器 `--check` | 0 | [日志](logs/schema-check.log) |
| 本地 HTTP protobuf codec / transport | 0，177 + 24 检查，零失败 | [结果](http-fixture-result.json) |
| 本地 HTTP boundary | 0，零失败 | [结果](http-boundary-result.json) |
| 真实服务端 numerics / Godot 预览一致性 | 0，1800 组，零差异 | [manifest](preview-parity-result.json) |
| 原 PR13 `run_play_retry`，独立默认中文环境 | 0，17 模块 | [日志](logs/run_play_retry-isolated.log) |
| 原 PR13 `run_lobby_race` / `run_gameplay_load_parse` | 各 0 | [竞态](logs/run_lobby_race-isolated.log)、[加载解析](logs/run_gameplay_load_parse-isolated.log) |
| 新原生集成主矩阵 | 0，150 PNG，480 断言 | [report](render-report.json) |
| 新原生邮件短标签 | 0，36 PNG，270 断言；12 次本机无省略号像素对照零差异 | [report](mail-report.json) |
| 新原生图鉴长标题 / 正文 / 重开 | 0，30 PNG，48 断言 | [report](codex-report.json) |
| 新原生英文美术场景 | 0，66 PNG，零布局错误；含 12 物种 / boss 阶段 / 三职业 | [report](art-report.json) |
| 新原生设置底部滚动 / 返回关闭 / 再开 | 0，12 PNG，60 断言 | [report](settings-report.json) |
| 所有 manifest 位图和资源字面引用 | 563 位图成功解码 / hash 匹配，181 引用存在，零缺失 | [assets.json](assets.json) |

本批接受 **294 张新 Godot viewport PNG**：150 + 36 + 30 + 66 + 12。前三套和设置补充覆盖中文 / 英文及 1920×1080、1280×720、960×540；66 张美术补充是英文、1920 / 1280。所有 [capture-index](capture-index.json) 条目都记录 ea94 源、实际尺寸、字节数和 SHA256。九张联系图仅缩小真实截图用于浏览，没有生成或替代运行时美术。

主矩阵使用真实按钮信号和 PR13 store：切换目标立即废弃旧预览；等待确认时不能向旧目标出牌；ACK 后接受 revision 9 snapshot，生成新目标预览并保留选牌；进入 recovering 清空预览。六组双语 / 分辨率的实际发送记录位于 `render-report.json`。三职业战斗夹具有完整 `passive_kind` 与完整说明，含六伤害分段、治疗、护盾；没有用正文为空的旧 fixture 证明布局。

已人工查看全部联系图，并以原尺寸查看邮件 en / zh 960、图鉴 en960 / zh1280、三职业 Signature 与最长说明、pending / confirmed 目标预览、装备对比重开、设置顶部及滚动底部等代表图。[45 张原 PNG](selected-proof-index.json) 已入仓库，字节 hash 与新索引逐项吻合；包括 [英文邮件](proof/mail_labels_normal_en_960.png)、[图鉴长名](proof/codex_long_detail_0_en_960.png)、[目标待确认](proof/integration_target_pending_en_960.png)、[目标已确认](proof/integration_target_confirmed_en_960.png)、[三职业完整说明之一](proof/passive_six_mage_en_960.png)、[设置底部](proof/settings_bottom_1_en_960.png)。这不等于对 294 张图均作过逐字原尺寸审阅。

1280×720 怪物实图 `integration_ea94_monsters_1_1280.png` 已额外保存到用户 Library：**`libfile_fe293993e05081918038a865cdfd3f7c`**，1,412,186 字节，SHA256 `7b5a444913dd96324d6abfc9ef0e2364941ca550d41e98d0638edcf33d80aa96`。详见 [Library 元数据](library-new-preview.json)。这是新组合运行截图。本批没有新增 imageGen 调用；继续接入 UI070 的两件真实 imageGen 成果，原图 / 提示词 / 调用 / alpha / import 证据在 [generation.json](../ui-style-20260930/generation.json)。生成怪物框原件仍是 `libfile_02794d971ed0819187e0ab7a3269d610`，955×1647 RGBA，SHA256 `3b50bf66192daaa1d2be4a22ea10601d8c10d41cd31f728164ca307ba0044ce5`。

执行使用 `/workspace/relicround-env/activate.sh`；原生截图通过 Xorg :93 / Mesa llvmpipe、Godot `gl_compatibility`、Dummy audio。各套独立 XDG data/config，避免语言残留。复核命令如下，`$E` 为新的证据输出目录；场景输出同时设置 `FANTASYCARD_SOURCE_SHA=ea94d97fe30d3622777f9190d7696c640f70b02a` 和 `FANTASYCARD_UI_EVIDENCE`。不要把测试目录当正式外部服务器。

```bash
godot --headless --editor --path client --import --quit
FANTASYCARD_UI_CHECKS="$E/native.json" godot --headless --path client --script res://tests/run_ui_style_checks.gd
dotnet run --project protocol/tests -c Release -- "$E/official-golden-vectors.json"
python tools/generate_network_protocol.py --check
python client/tests/run_http_protobuf_client.py --godot "$A3GAME_GODOT_EXECUTABLE" --work-dir "$E/http-fixture"
python client/tests/run_http_boundary.py --godot "$A3GAME_GODOT_EXECUTABLE" --output "$E/http-boundary"
python tools/pr13_preview_checks.py --godot "$A3GAME_GODOT_EXECUTABLE" --output "$E/preview-parity"
godot --headless --path client --script res://tests/run_play_retry.gd
godot --headless --path client --script res://tests/run_lobby_race.gd
godot --headless --path client --script res://tests/run_gameplay_load_parse.gd
godot --path client --rendering-method gl_compatibility --audio-driver Dummy res://tests/ui_pr13_integration.tscn
godot --path client --rendering-method gl_compatibility --audio-driver Dummy res://tests/ui_style_mail_labels.tscn
godot --path client --rendering-method gl_compatibility --audio-driver Dummy res://tests/ui_style_codex_review.tscn
```

外部 [art 场景](harness/art-harness.tscn) 选择已提交的 additive art script；[settings 场景](harness/settings-harness.tscn) 指向此次归档的 [脚本](harness/settings-harness.gd)。settings 场景中的绝对云路径应改成恢复后的该脚本路径。它们的精确 hash 在 [test-summary](test-summary.json)。完整 294 张原图目前在云目录 `artifacts/ui-pr13-integration-de1157f`；未选中的 249 张原始字节尚未保存到 GitHub / Library。仓库持久保存的是全部 hash / 尺寸索引、联系图、原始报告 / 日志和 45 张代表 PNG。

两次探索失败均保留且不算通过。首次原 retry runner 使用已保存 `language=en` 的共享目录，装备中文字符串断言失败；同一原测试在独立默认中文目录全部通过，没有修改其源码。设置补充首次把 embedded popup 的逻辑尺寸与物理窗口像素比较，8 个几何断言失败；纠正补充夹具的坐标单位后 60 断言通过，实际 popup 为逻辑 948×724、逻辑 viewport 1920×1080，物理 960 图也已查看，未改生产代码。

**仍保留的原测试问题：** 原 `test_boxspirit_instances` 在精确 de1157f 基线和此次组合均退出 1，其旧中文子串断言不匹配当前完整句子。两侧日志都在仓库；修正版另存测试通过，原 PR13 文件仍保持不变。本批不能表述为“所有原测试均绿”。

范围限制：原生 UI 使用离线状态和 recording gateway，未证明真实邮件经济交易、外部服务器重连或多用户压测；1800 组 parity 执行实际服务端 numerics。面板重复开关验证可见性、关闭及可达内容，没有证明长时间内存稳定。部分原生日志有 ObjectDB / resources 的退出清理警告，未在本批诊断，不能声称 stderr 全干净。协议命名、目标确认和恢复源码保持 de1157f blob；本结论不扩展到 PR13 后续源批次。
