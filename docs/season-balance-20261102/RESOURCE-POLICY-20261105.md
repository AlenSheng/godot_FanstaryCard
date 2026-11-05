# 本机2GiB内存保护调整

2026-11-05用户明确要求“内存保护改为2GB”。本任务从该要求起，将本机可用内存保留量由6GiB改为2GiB；按GiB执行，保留原1GiB单进程启动预算，因此三点准入门槛为3GiB。运行期间持续检查2GiB保留量，只结束本任务自己持有的进程，不停止或修改其他项目进程。

调整落在`client/tests/fixture_runtime.py`与`tools/validate_ui_hidden.py`。Godot仍无弹窗／私有桌面，进程保持BelowNormal，重任务顺序执行。通用保护器的错误文本同步改为validation process，避免.NET构建再次被误标为Godot。

云端条件未调整：RAM保留500MiB，磁盘保留3GiB且至少5%；原生无界面与.NET运行时原1800MiB准入、已有容器上限、只读输入及暂存余量继续适用。未获授权调用云端SDK，没有新增100人补测或放宽功能断言。

历史6GiB准入拒绝和中途保护触发按原条件保留，不能按新门槛追认为通过。已通过的17项控制器与阿拉伯语36帧仍保留原证据；后续新批次在报告中标明2GiB条件。待验范围、测试场次预算、最终集成及生产重启条件均未因此完成。


2026-11-06再次核对：client/tests/fixture_runtime.py为2GiB持续保留加1GiB启动，tools/validate_ui_hidden.py的RESERVE=2*GIB、START_BUDGET=GIB；当前C16三个批次均沿用该保护，无需重复降低。外部接续JSON中早期resource_rules字符串已与当前2/1/3GiB字段对齐，原6GiB记录先完整归档保留。
