# PR13 有界离线故障批次

固定候选 `f93e32dac07608e8375e709cd357c4793bdcc41a`：Domain317、Server/PG284，零失败零跳过；READY/STOP10项（9真实服务/1SupportOnly）、旧回调6项、ACK三种真实响应丢失模式均通过。[报告](REPORT.json)保留各单位和重叠范围，不能相加充当canonical覆盖率。

[CASE_MATRIX.json](CASE_MATRIX.json)明确21个选定case：16项部分证据、5项本批未执行、0Accepted。全132项53Partial/76NotRevalidated/3Blocked；G0–G5未签署。

原始反例保留：回调baseline4/6失败；同一最终READY harness、有效GUID，f93+de1157单文件preimage准确记为dirty overlay，旧事件导致0ticketreads且cleanup误报Passed；固定纯f93十场景通过。cleanup第二反例和ACK代理/导入失败均按真实原因保留，不写成不存在的生产ACK缺陷。

GitHub八job无runner/无步骤。MAIN从另一个同账户run确认计费阻断（付款失败或spendinglimit，具体子因未知）。[CI清单](ci-f93e32da.json)保留精确SHA/run；未发重试、未改账户/权限。代码CI仍待补。

历史raw/ledger异常、线上容量、真人/RENDER、完整Boss和多局真实成功计数仍未关闭。所有新账号/资产和PG均为本地隔离fixture；[清理证据](cleanup-proof.json)确认13个完整服务进程全部停止、随机schema零残留。四份原始模拟ZIP继续本地保留等待明确上传授权；没有线上操作。
