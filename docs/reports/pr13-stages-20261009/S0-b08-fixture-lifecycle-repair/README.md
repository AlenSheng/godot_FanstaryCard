# B08.2 测试前置条件与退出等待修正

REST 测试替身原先没有 token，Game.refresh_cache 会在首行返回，导致 deck_refresh_switch 的第二份响应未消费。现在明确提供模拟 token、非空 lobby 与原有顺序的 20 张卡组，隔离并恢复 fixture 改动的 Game 缓存和 host 状态。真实 gateway、UI 和音频服务未修改。

Element 显示 fixture 在原有停止音频、销毁 UI 和绘制帧等待后，增加与其他通过场景相同的 0.25 秒等待。弱引用确认 UI 已销毁后才写结果。旧长场景四个对象、两个资源告警的确切来源尚未证明，不能把这次候选修正视作告警已消除。

本阶段只保存代码修正、文本/括号/顺序静态检查及原字节差异，不是 Godot 解析或运行通过。后续必须使用最终 release 全部客户端及 renderer 原字节的新云端 attempt，独立验证 REST 和 Element T01/T02/T03 的功能与严格退出日志，并保留旧失败数据。已完成数值实验不因 fixture 修正重跑。normal_shutdown、REST_session_fixture_regression、full_fix_verified 和 MAIN/LIVE 仍未授予通过，主验收表不变。

公开原件沿用 -text 字节保护，manifest 排除自身；本地没有执行 Godot、原生采样或业务 oracle。

代码按 Git 的 LF 文本规则统一换行；原修改快照仍逐字节保留。committed-source-byte-normalization.json 分别记录原快照与将提交代码的 SHA，去除 CRLF 后内容相同，此步骤没有运行原生解析或测试。
