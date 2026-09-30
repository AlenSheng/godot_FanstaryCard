# 固定 PR13 f812879e + UI d76d7165 最终组合候选

组合输入固定为 PR13 **`f812879e4518fd09bf22656451cb563d62940298`**（父任务受测源 `38c2caccb5f8327f52d97dffb3b9f9303360dd46`）和已审 UI/怪物标题 **`d76d7165c915c94732ca7087af4e22876afc76e5`**。本批实际执行测试的组合源码是 **`4f174ac04accafbb1ec34cbda85d962fecbd523e`**。

独立分支 `fix/ui-pr13-final-f812879e-20260930`；冻结审阅基准 `audit/pr13-f812879e-ui-base-20260930` 指向 f812879e。PR13/PR16/PR19 原分支、release/main 未改，没有合并或部署；CI 受计费阻断，没有重试。后续仅添加本报告和临时验证适配器归档，生产内容保持实际受测源。

## 来源和冲突

在初始组合提交中，f812879e 的 **7550 个既有非 UI blob**（排除 `client/ui`、`client/assets`）全部保持 mode/type/blob 一致；13 个生产 UI/资源路径与 d76d7165 全部精确一致。原怪物标题修复和 imageGen 美术原件保留，没有新美术生成或生产补丁。相对 de1157f 的 gateway、game_store、gameplay_load_client 新逻辑保持 f812879e 原件，原测试、schema、配置、服务端源码保持该固定输入。`git apply --check` / apply 均退出 0，真实组合冲突清单为空。

见 `inputs-and-preservation.json` 与 `non-ui-inputs-01.json` 至 08 分卷。运行时构建删除/重建的 2332 个已跟踪 bin/obj 已在全部测试结束后从 f812879e 恢复。`preservation-final.json` 再次确认组合提交与最终工作区的 7550 个既有非 UI 文件一致，13 个 UI/资源文件与 d76d7165 一致，差异数均为 0。导入生成的 10 个未跟踪 UID 已移除；生产源码没有新增修改。`source-map.json` 提供新增 PR13 源码和已审 UI 的精确 blob、mode、SHA256。

## 本批新执行结果

| 检查 | 结果 | 证据 |
| --- | --- | --- |
| 根 Godot 4.7.2 资源导入 | 退出 0，无 Parse/Script error | `logs/root-import.log`、`import-exit.txt` |
| 旧回调/NOT_IN_ROOM 隔离 | 6 用例通过；真实 loopback HTTP/WS，其他事件受控注入 | `callback/report.json`、requests、cases、commands |
| HTTP protobuf | codec 177 + transport 24，零失败，退出 0 | `http-codec/` |
| 真实 loopback HTTP 边界 | 零失败，退出 0 | `http-boundary/` |
| UI/目标/确认相关模块 | 19/19，退出 0 | `ui-modules.json` |
| 新 session sequence / settlement polling | 2/2，退出 0 | `new-session-modules.json` |
| 新 load runner 解析 | 退出 0 | `logs/load-parse.log` |
| 实际 Program + Godot + 独立 PostgreSQL READY/STOP | 5/5 通过，退出 0；依赖适配版 | `ready-stop-compat/report.json`、cases、SQL 后置条件、commands |
| 原 ACK 响应丢失/三局/STOP 测试 | 第二轮 7/7 通过、0 跳过，退出 0；完整 Program / 实际 Godot / 独立 PostgreSQL | `ack/ack-process-02/results/targeted.trx`、原始客户端收据、commands |
| 新原生代表性 UI | 48 全图、272 断言，零失败 | `representatives/report.json` |
| 新原生邮件 | 24 全图、180 断言；8 组完整按钮原生像素比较零差异 | `mail/report.json` |
| 新原生图鉴 | 20 全图、32 断言，零失败 | `codex/report.json` |
| 新原生怪物标题 | 36 全图；72 标题/72 原生像素对照，零溢出/差异 | `monster-titles/report.json` |

本批新原生全视口图为 **128 张**，全部保留原始 PNG；另保留 144 张怪物标题实际/参考裁图。UI/邮件/图鉴为中英 1280×720、960×540；怪物覆盖 12 物种、中英、1920×1080/1280×720/960×540。它们都是此次 4f174ac0 运行结果，没有拿历史 530/1066/294 图计作新通过。`new-capture-index.json` 给每张图的 source、尺寸、字节数和 SHA256。联系图仅拼接真实截图，未替代运行时资源。

代表夹具通过生产目标按钮、事件/快照入口验证：旧预览在目标切换后废弃、等待确认时禁止向旧目标出牌、revision 9 快照后生成新目标预览、选牌保留、recovering 清空预览。三职业均提供完整 passive_kind、说明和六分段布局数据；不是旧空正文 fixture。确认窗和邮件、图鉴面板反复开/关/再开。该视觉层使用 recording Gateway，不是实际服务端交易；真实 READY/STOP/ACK 证据另列。

已人工查看四张联系图、两张全部 12 物种/三尺寸标题页，以及英文 960 待确认/确认后目标预览、三职业本命六分段、中文 960 牧师本命、英文 960 邮件和图鉴原图。怪物物种名保持完整，Thorn Mite 完整显示；英文邮件 Claim/Delete/Claimed 完整。不是声明对 128 张全图均逐字原尺寸审阅。

## 临时精简项目的依赖适配

原 PR13 精简 READY/STOP 和 ACK 夹具只复制 Palette/CardDetails，或删除其他 UI 脚本。已审 UI Palette 新依赖 `art.gd`；直接执行原 READY 批次时，业务和数据库检查为真，但 Godot 打印缺少 art 的 Parse/Script error，整批 5 项判失败。原失败报告/日志保存在 `ready-stop/`，退出 1，**未计作通过**。

`harness/godot_ui_compat.py` 只向本批临时 fixture 路径补入字节一致的 art.gd、manifest、两件 art eager texture 和原 import 设置，然后 exec 真实 Godot。没有替代引擎、伪造返回或修改 GameStore/gateway/runner/原 C# 断言。`compat-dependencies.jsonl` 记录逐项 source/copied SHA；三个逻辑文件仍为 PR13 原件。配置只定位本地源码、证据和真实 Godot。

READY 成功批次使用 v1 环境版适配器。ACK 第一轮因原 C# 显式 `Environment.Clear()` 移除了适配器所需变量，在真实 Godot 启动前失败，7 项均失败；不是 ACK 业务验证结果。第二轮使用适配器本地配置回退，保留 C# 原隔离规则；版本 hash 映射在 `harness/wrapper-source-map.json`。不改安全配置、rate limit、匹配等待或 15 秒 READY deadline。所有失败尝试都保留，没有把部分业务为真当作整套通过。

READY 成功范围：normal_ready、required_lost_reconnect、ready_replies_lost_reconnect、ready_send_all_lost_stop、stop_ready_before_send。后两类验证 STOP 后不再发 READY、原 15 秒 deadline、人类成员/route/资产释放；机器人房间仍按原生产行为存在，不删除它伪造清理。实际丢弃的序列化包、重连和 SQL 后置条件保存在相应用例目录。

ACK 第二轮全部 7 项通过：`drop-first-committed`、`drop-all-committed`、`drop-all-uncommitted`；以及原 load runner 的 `cycles-middle-response-loss`、`cycles-middle-uncommitted-loss`、`stop-after-commit`、`stop-before-commit`。运行时长 5.5341 分钟，三个已提交/未提交响应丢失模式检查重试和唯一 receipt；两组三局检查计数和中局丢包，两组 STOP 检查不再完成 ACK。原三局用例使用合法 extract/abandon 驱动，不等同自然完整战斗路线。第一轮 7 项启动失败保存在 `ack/ack-process-01`，未计作通过。第二轮复用第一轮成功构建的同一 DLL；`reused-build.json` 给出受测源和 DLL hash。两轮的 `schema-cleanup-check.json` 均确认拥有的 schema 数为 0，PostgreSQL 停止退出 0。

ACK 原 C# 测试及客户端逻辑没有修改；只归档临时项目顶层日志、收据、状态、STOP、source manifest、TRX 和命令。临时 user-data、数据库目录、引擎缓存和重复字体/资源未归档。READY 原始报告中的 source_dirty 是当时构建 bin/obj 和导入 UID 的记录；最终源码保持核验独立记录，不修改原报告掩盖运行痕迹。

`codex/report.json` 的 `primary_matrix_ui_sha` 是旧夹具继承的历史标签，不是本批源码；它的 `source_sha` 正确为 4f174ac0。本批权威输入和源码对应以本报告、commands、逐文件 hash 为准，原报告保持原始字节。

## 可复核产物与边界

最终怪物英文 1280 原始 PNG 已存用户 Library：**`libfile_8ef134184abc81918594ddd749f1feb1`**，`final_candidate_4f174ac0_monsters_en_1280.png`，1280×720，1,411,535 bytes，SHA256 **`2a28f1910d556b01d5023377eb2a5d138e978c21cbede2f7f4484d8f70cf6e55`**。与本目录 `monster-titles/monsters_1_en_1280.png` 字节一致；不是旧 d76 图或重新 imageGen。

原 imageGen 提示词、调用、alpha、导入证据仍在 `../ui-style-20260930/generation.json`，怪物框原件 Library `libfile_02794d971ed0819187e0ab7a3269d610`。本批源和资源为固定输入，没有修改美术。

`test-summary.json` 汇总本批固定来源及通过/失败边界；`file-index.json` 为本目录归档文件逐项记录尺寸和 SHA256。在安装 Pillow 的环境运行 `python verify_archive.py` 可校验归档全部字节、272 张原生证明图及 72 组实际/参考标题像素，检查本批结果和保留的失败记录；它不会启动游戏或重跑矩阵。`verification.json` 是此次校验结果。原始日志按字节保存，包括末尾空行；本目录 `.gitattributes` 仅将日志设为 binary diff，不改运行配置。

本批不执行完整历史千图、1800 数值 parity、完整数据库 suite、线上账号/压力或自然三局全路线。callback 为真实通信的组件夹具；READY/ACK 使用拥有的完整 Program 和 PostgreSQL；原生 UI 是真实渲染的本地状态，三个层次不混算为线上体验。canonical Accepted 仍为 false/待父任务独立验收，Passed 仅描述列出的定向检查。

计费阻断尚未解除，新增提交用 `[skip ci]`；没有改 workflow、账号、付款、额度或权限，也没有触发无效 CI 重跑。最终 SHA 的 CI 仍待后续授权与账户恢复。
