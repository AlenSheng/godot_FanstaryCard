A09.1 R2完整原生联机测试退出0，原始TRX为1 Passed、0 Skip，三个Git/fixture/run_id反例和六份实际PG旁证均完成。18张正式联机画面生成，控制器、G保管ACK和清理全部成功，生产未变。

像素独立验收在第一幅图失败。逐幅核对确认18个解码RGBA摘要均不等于原生原始像素摘要，实际WebP块为VP8有损。当前Godot4.7.2 ClassDB实际接口为save_webp(path,lossy=false,quality=.75)，私有采集脚本误传true，把quality=1.0当作无损；原数据中的native_lossless_WebP=true声明不正确，原件和错误声明均保留，不把独立失败改成通过。426项诊断检查成功只证明原生/来源与编码缺陷已查明，不代表RENDER验收。

本轮不发布新的通过层，77缺层、32未验收和当前登记保持。原始993成员、12,719,448字节归档及1109份G源/原件已核验，保管后仅移除本轮输入；R1旧失败及旧cloudraw/shared/A073不删。下轮只修私有采集lossy参数为false，先用零玩法样本的本地headless编码校准，再单独登记额外2房间/5自动化账号完成同轮联机PG渲染复验。R1未知自动房间数按6个规划预留而非观测值，R2实际两个房间/5账号，R3追加上限2/5，保守累计10房间/15自动化账号。失败不归零，原C#180秒、bot-fill30秒、业务/容量/图质标准均不放宽。

R2整轮界面和证据位于自有/evidence384MiB与/screens256MiB tmpfs，磁盘保护未再触发；没有修改产品UI、资源、配置、GDD或生产，也没有commit/push/deploy。真人不在范围，actual_human_accepted=false。
