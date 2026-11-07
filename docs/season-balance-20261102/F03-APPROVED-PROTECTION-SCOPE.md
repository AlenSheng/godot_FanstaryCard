# F03 用户批准的具名保护验收

2026-11-07。用户对问题call_46151f4602a14b0a8c7b1844dcabf721明确选择：“按本轮具名范围验收，明确保留79项未执行限制”。本轮保护子门禁据此通过，状态为AcceptedWithinExplicitUserNamedScope；不再把保护验收口径本身列为待确认项。

## 准确覆盖

只适用于源码1fe8e4b219714688c0bed061a3162628c5dd1cbe导出的固定18文件保护包，全部文件与原记录逐SHA及长度复核。1218个方法定义分为1139个本次执行方法和79个排除方法，集合无重叠且完整。逐份TRX核对实际方法及Passed结果，共1867条、零失败零跳过（Domain759、Server1108）。没有只依据汇总数字给出通过。

保护前后21128条接口/JSON属性/默认值及命名参数记录一致；双侧50快照规范化结果逐份一致，实际加载的Domain/Contracts SHA匹配本包。云端准确18文件、UID1654、只读根文件系统、52迁移自有schema与14项HTTP通过，归档SHA和全部容器/镜像/schema/私有配置/上传tmpfs清理证据复核。

79项仍标记current_fixed_package_executed=false，逐项保留类型、方法、门禁、原因及历史缺口。它们没有被改为Passed，没有推算Theory展开场数，也不宣称当前全1218方法或真实原生/外部平台均实测。之前的失败、超时、来源和性能payload缺口原样保留。

## 凭证与发布边界

本次凭证为[protection-scope-verification.json](evidence/F03-approved-scope-r1/protection-scope-verification.json)，附原答复、79项清单和每份证据SHA。它明确whole_suite_all_methods_passed=false、protection_subgate_accepted=true、whole_F03_accepted=false和production_deployment_authorized=false。该最后字段表示当前放行条件尚未满足，不撤销用户原目标中已有的最终部署授权。

默认全套验证工具不改，用户批准仅为本包/本轮声明范围的例外。原18文件包、原tested=false报告和候选标记均不修改，保持已测输入与原始阶段证据的字节完整；后续正式发布准备应显式引用本次范围凭证，不能把原全套报告改成全绿。候选标记当前仍阻止整体验收前直接部署，不表示本轮保护口径仍待答复。

D03仍308/308封账，追加至317执行既定9场的答复尚未收到；这次答复未授权增加任何场次。F01仍300、B05仍330。正式分支更新、切换前新备份、实际部署重启及公网核验依原放行条件完成，不能据保护子门禁通过提前更新生产。整体33/35，剩余D03及完整F03。

没有新测试、对局、UI或云端操作。总报告与接续记录同步本次决定，历史规则及失败保持可追溯。
