# PR19 怪物卡标题定向修复

英文怪物卡标题曾先按正文字体缩小，再改用较宽的标题字体，导致末尾裁切且没有省略号。本批只修 `client/ui/card_view.gd` 的 `_monster_text` 显示段：先设置真实 themed title 字体，再拟合；保持单行，优先完整标题，最低字号 16。若通用 “Monster” 前缀使标题超宽，先省去该前缀，保留完整物种名。未来更长译名使用省略号，并在卡片 tooltip 保存完整标题。没有新增 imageGen 调用，也没有改动美术像素、状态或协议。

固定输入仍是 PR13 `de1157fdf490a5bce3ba888c07519fc957c46782` + UI `070c7b441ffc5dbd7253aea1dcbc9793b1fef449`。独立分支 `fix/ui-pr13-integration-de1157f-20260930`、草稿 [PR19](https://github.com/AlenSheng/godot_FanstaryCard/pull/19) 的基准是冻结分支 `audit/pr13-de1157f-ui-base-20260930`。没有修改 PR13/PR16 原分支、release/main，也没有合并或部署。

## 源码和结果对应

| 阶段 | 精确 SHA | 用途 |
| --- | --- | --- |
| 上批集成生产源码 | `ea94d97fe30d3622777f9190d7696c640f70b02a` | 上批宽范围回归，详见旧报告 |
| 上批交付 | `a9a30d8535c427d4a4b45bcd546c00f75f36173d` | 上批证据提交；生产与 ea94 相同 |
| 本批 before | `f4eba590605024d52cb89ff9c3bb2fdd885106ce` | 只添加标题检查夹具，生产与 a9 相同；实测失败 |
| 中间修复 | `5641b39651d1245a99bbafeafb1488ef9c59a2e3` | 最低 14；检查通过后看图发现字号偏小，已被下一版本取代 |
| 本批最终实际测试源码 | `652549aa7db1f99f5313aba960163cc4c0984c7f` | 最低 16；本目录 after、模块、导入和溢出补充均对应此 SHA |

本目录后续归档提交仅添加证据，最终交付 SHA 由 Git commit/PR19 head 标识。`preservation.json` 记录源码 blob guard；before/after 三个夹具文件字节相同。中间版本只保留报告和日志，**不计入最终通过数**。

## 本批新执行的验收

Godot 4.7.2；真实原生 Xorg `:93` / Mesa llvmpipe / `gl_compatibility` / Dummy audio。截图通过生产战斗手牌控件生成，采用隔离本地状态夹具和独立 XDG 配置。12 个真实物种 × `zh-CN`/`en` × 1920×1080、1280×720、960×540：每次放两个怪物卡，共 36 张完整视口图、72 个标题样本；before 和最终 after 各运行一次。

| 检查 | before f4eba590 | after 652549aa |
| --- | ---: | ---: |
| 完整视口 PNG | 36 | 36 |
| 实际标题 / 独立原生参考裁图 | 72 / 72 | 72 / 72 |
| 真实 title 字体安全区溢出 | 36 | 0 |
| 原生实际/参考像素不一致 | 27 | 0 |
| 综合断言数（含策略要求） | 165 失败 | 0 失败 |
| 最低实际字号 | 13 | 16 |
| 进程退出码 | 1 | 0 |

具体复现：英文 1280 Thorn Mite 的 Label 属性在 before 虽然包含完整字符串，但标题字体 19 的测量宽为 192，安全宽仅 172，2 行只可见 1 行；实际像素显示 “Monster Thorn Mi”。最终为标题字体 17，宽 172，1 行，完整显示 **“Monster Thorn Mite”**。`before/report.json`、`after/report.json` 和原始裁图可独立复核。165 个断言失败包括单行、省略策略等，不能解读为 165 个独立视觉缺陷。

像素参照是相同文本、真实字体、字号、颜色和几何位置的独立 Godot Label，禁用换行和省略；短暂隐藏原 Label 获取参照后立即恢复。完整物种名/tooltip、真实字体宽高、单行检查与原生像素字节对照**共同**验证已知标题完整。单靠裁图相等不能证明框外文本完整。

另在最终 SHA 新执行：Godot 资源导入退出 0；19/19 相关 Godot 模块通过（`--headless`，包括卡片、字体、多语言、目标和确认快照等，详见 `native-final.json`）；4 个中英文模拟长译名守卫通过，退出 0。模拟长译名测试是 headless 补充，不能当作真实目录名称的原生像素验证。

实际人工查看全部 6 张双语/三尺寸标题 before-after 对照页、2 张全视口联系图，以及最终英文 1280 第一组、英文 960 第四组、中文 960 第六组原图：已知名称末尾完整，较长名称去掉通用前缀后仍保持完整物种名。联系图只拼接截图/裁图用于证据浏览，不用于运行时美术。

## 证据文件

- `before/`、`after/`：全部 72 张原生视口 PNG + 288 张实际/参考标题裁图，**本批原始图全部归档**，没有仅留云工作区的缺口。
- `review/titles_<locale>_<width>_before-after.png`：6 张标题比较页；原生裁图最近邻放大 4 倍，原始像素另存。
- `review/before-full-viewports.jpg`、`review/after-full-viewports.jpg`：全范围缩略联系图。
- `logs/`、各退出码、`native-final.json`、`fallback.json`、`fallback.gd`：实际进程日志与结果。
- `test-summary.json`、`preservation.json`、`image-index.json`、`file-index.json`：源码映射、保护检查和尺寸/字节 hash；`production-display.patch.gz` 是本批唯一生产文件的精确 diff。
- `verify_archive.py`：离线检查归档文件 hash、图片尺寸和实际/参考像素结果。

最终英文 1280 原始 PNG 已保存到用户 Library：**`libfile_6f138602cd84819184a07c1c16e47db6`**，文件 `monster_title_fixed_652549aa_en_1280.png`，1280×720，1,411,531 bytes，SHA256 **`291ae860cb5090e57626a957dd481bb84ace6954cb35a9b645dece1b9b3a7da8`**。与 `after/monsters_1_en_1280.png` 字节一致；不是重新绘制或重新 imageGen。旧 ea94 图的 Library ID `libfile_fe293993e05081918038a865cdfd3f7c` 仍为旧证据，两次完整视口 PNG 并非 byte-equal，因为动态绘制状态随帧变化。

已有 imageGen 怪物框原件继续沿用，Library ID `libfile_02794d971ed0819187e0ab7a3269d610`；原生成和导入证据见旧 UI 报告。本批未改变此原件或运行时框。

## 隔离与未验证边界

最终源码树及当前工作区对固定 PR13 的 **5803 个既有非 UI blob 均零差异**。原 UI 输入的 13 个生产 UI/资源路径有 12 个保持精确一致，唯一差异是上述 `card_view.gd` 标题显示修复；本批没有显示 hunk 冲突。旧报告的“13 个全部相同”是 ea94 历史结果，不适用于本次有意修复后的源码。新增夹具/归档为独立路径。

旧 294 张宽范围截图、C# 25 检查/8 个官方向量、HTTP 177/24/边界和 1800 个服务端/客户端数值对照属于 ea94 的[前批报告](../ui-pr13-integration-de1157f-20260930/README.md)，**没有在 652549aa 重执行，也不计作本批新通过**。本批没有重新验收邮件、图鉴、目标切换预览、三职业本命正文、面板重复开关或线上多人压力。固定 de1157f 之后的新 ACK/READY/STOP 逻辑也不在该组合范围。

before 日志保留退出时 6 ObjectDB / 3 resources 警告；最终 after 日志只打印显卡 VSync 警告，最终模块/补充日志无警告或错误。未据一次未打印退出警告声称解决资源生命周期问题。首次导入重建 6 个既有缺失 test UID，这些自动生成文件未进入本批提交。最终导入退出 0，所有保留日志没有 Parse/Script error。

GitHub CI 仍待账户计费问题解除。父任务已从[run 36769267481](https://github.com/AlenSheng/godot_FanstaryCard/actions/runs/36769267481) 登录后的 Annotations 确认 job 未启动，因为付款失败或 spending limit；两种具体原因未区分。旧 PR19 [run 36773897757](https://github.com/AlenSheng/godot_FanstaryCard/actions/runs/36773897757)、[run 36773896151](https://github.com/AlenSheng/godot_FanstaryCard/actions/runs/36773896151) 的 5 jobs 均零执行 steps，不是代码失败也不是 CI 通过。本批提交使用 `[skip ci]`，依照 [GitHub 官方跳过说明](https://docs.github.com/en/actions/how-tos/manage-workflow-runs/skip-workflow-runs) 避免触发无效重试；解除计费阻断后仍需对最终交付源码补 CI，没有修改 workflow、账号、付款、额度或权限。

## 可复现命令

下列是重现命令，非再次执行的声明。before 使用 f4eba590，after 使用 652549aa，场景夹具字节相同。需可用原生 Xorg 显示；`OUT`、`PHASE`、`SOURCE` 根据该阶段设置，两个阶段用不同 XDG 目录。夹具 state 为本地隔离状态。

```bash
source /workspace/relicround-env/activate.sh
OUT=/tmp/relicbound-monster-title-after
PHASE=after
SOURCE=652549aa7db1f99f5313aba960163cc4c0984c7f
mkdir -p "$OUT" "$OUT/user/data" "$OUT/user/config"
export XDG_DATA_HOME="$OUT/user/data" XDG_CONFIG_HOME="$OUT/user/config"
timeout 180 "$A3GAME_GODOT_EXECUTABLE" --headless --editor --path client --import --quit
DISPLAY=:93 FANTASYCARD_ART_EVIDENCE="$OUT" FANTASYCARD_TITLE_PHASE="$PHASE" FANTASYCARD_SOURCE_SHA="$SOURCE" timeout 180 "$A3GAME_GODOT_EXECUTABLE" --path client --rendering-method gl_compatibility --audio-driver Dummy res://tests/ui_monster_title_review.tscn
FANTASYCARD_UI_CHECKS="$OUT/native.json" timeout 120 "$A3GAME_GODOT_EXECUTABLE" --headless --path client --script res://tests/run_ui_style_checks.gd
FANTASYCARD_FALLBACK_RESULTS="$OUT/fallback.json" FANTASYCARD_SOURCE_SHA="$SOURCE" timeout 60 "$A3GAME_GODOT_EXECUTABLE" --headless --path client --script "$PWD/docs/reports/ui-monster-title-20260930/fallback.gd"
python3 docs/reports/ui-monster-title-20260930/verify_archive.py
```
