# UI多语言、多分辨率与字体清晰度验收

本轮已完成当前版本的本地原生UI验收。中文和英文分别覆盖960×540、1280×720、1920×1080，53个界面／状态，共318张实际渲染图、714项自动检查通过。最终源文件在六组合运行期间保持不变；全量总览目检及关键文字原图抽查完成，本范围内没有遗留阻塞项。

最新结论见[final-summary.json](final-summary.json)，逐帧路径和SHA见[final-frame-manifest.json](final-frame-manifest.json)，本轮文件范围见[source-pin-final.json](source-pin-final.json)。更早的progress-r1／r2／r3是保留的过程快照。验收结束时修改尚未提交；后续release推送和云主机重启状态见[PUBLICATION.md](PUBLICATION.md)。

## 字体清晰度

普通界面使用2倍光栅采样、灰度抗锯齿、完整自动hinting、四分之一像素定位和mipmap。卡牌存在额外的局部缩放，改用96px、range8的MSDF字体。字体仍来自完整的思源黑体Regular／思源宋体SemiBold，原字体二进制、授权及等宽数字规则保留。

四种方案已在三档分辨率进行实际对照。普通UI采用2倍采样，卡牌采用MSDF，以改善细笔画和缩放边缘。参考[Godot字体文档](https://docs.godotengine.org/en/stable/tutorials/ui/gui_using_fonts.html)。

- [英文960修复前](samples/font-before-en-960.png)与[修复后](samples/font-after-en-960.png)。
- [中文960修复后](samples/font-after-zh-960.png)。
- 字体方案原图：[960](samples/font-candidates-960.png)、[1280](samples/font-candidates-1280.png)、[1920](samples/font-candidates-1920.png)。

这些样例均从原件逐字节复制，未缩放或加工。总览拼图仅用于布局审阅，未替代原生像素的字体对照。

## 本轮修复

- 修正容器初次布局导致的字体缩至1px、标签高度不足和英文品质筛选截字；按实际字体测量按钮。
- 卡牌图鉴／编组随分辨率调整列数，窗口变化刷新缓存，未拥有卡牌文字保持清楚的前景色，插画和边框仍显示拥有状态。
- 邮件长正文可滚动；长标题省略并保留完整提示；附件改为两列、名称与数量独立排布，品质底板加深。
- 英文装备属性增加词间空格，强化列表分行，装备比较小字按窗口确保主要说明达到约12px；图标下使用简短部位名称，完整属性保留在提示中。
- 修复市场操作按钮因容器最小宽度不足而塌缩；修正Esc关闭详情的所属页面，恢复真实弹层移除及鼠标／触摸交互。
- 探索移动箭头换为与金色、青色幻想风格一致的透明罗盘。使用内置ImageGen；[完整提示词](imagegen-prompt.txt)，资源为client/assets/generated/ui/exploration_move_compass.png，生成后的像素未加工。

## 验证范围

覆盖登录、大厅三职业、准备与锁定准备、装备与比较、强化与不可用状态、商店及尾部、市场、卡牌拥有／未拥有及报价状态、编组满／空、邮件长文与附件、设置／语言／战斗设置、确认、战斗属性、数值说明、怪物卡池各状态、探索／地图／中层、背包／遗物、PVE／PVP／奖励选择、准备提示、结算／恢复／通知。

交互回归原件：reg32-deck_builder_preview、reg34-codex_preview、equipmentreg35，均为native0、断言通过、stderr为空。包含实际设置回调中英往返、未保存编组保留、池化已选文字更新、滚动／短点击／Esc／触摸拖动、装备草稿与比较。卡牌组件回归也在最终headless预检通过。

本轮是离线UI夹具的真实Godot渲染和交互验收，真人体验排除，新增联网对局／容量场次均为0。保留合法80／70哨兵，不把血量超过基础值当异常；未修改平衡、GDD规则或网络协议，也没有重启100人补测。

## 无弹窗校验入口

项目入口为tools/validate_ui_hidden.py。脚本检查走headless，需要图像时以CreateProcessW指定新建的非活动桌面。最终六批1226次渲染主线程桌面检查均通过，SwitchDesktop调用为0；输入桌面读不到时记录null，继续执行严格的私有桌面检查。

每阶段启动前连续三次确认至少7GiB可用（6GiB保留＋1GiB启动预算），运行时保护6GiB，只终止自身持有句柄的超限进程；使用独立APPDATA和127.0.0.1:9夹具地址。命名互斥量阻止同入口重复启动，已实际验证拒绝发生在Godot启动之前。没有修改其他项目进程。

在项目根目录运行，output须为不存在的新目录：

```powershell
python tools/validate_ui_hidden.py --godot "G:/Program Files/Godot_v4.7.2-stable_win64.exe/Godot_v4.7.2-stable_win64.exe" --output "G:/PR13Evidence/new-headless-id" --scripts-only --card-regression
python tools/validate_ui_hidden.py --godot "G:/Program Files/Godot_v4.7.2-stable_win64.exe/Godot_v4.7.2-stable_win64.exe" --output "G:/PR13Evidence/new-render-id" --locale en --width 1280 --screens "cards,deck,mail"
```

## 原件与历史失败

完整原件在G:/PR13Evidence/ui-visual-review-20261027-r1。最终版本为final36-*，finalqueue36保留六组合源文件固定记录；fontprobe26-*为三档字体对照。全部早期失败、部分截图、资源拒绝、语法问题、无弹窗保护失败及修复前原件继续保留，分类见[failure-history.json](failure-history.json)。未通过改阈值、删除失败或复用旧图来判定本轮通过。

原生单批report中的whole_visual_acceptance仍为false，表示自动取图不是整体目检；本报告和final-summary.json记录完成目检后的本轮结论。旧容量／历史来源验收文件未纳入本轮改动。
