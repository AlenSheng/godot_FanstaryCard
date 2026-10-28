# B08.4 法师 BOSS 火属性等级 5 的全部三个种子块

只有 B0、B1、B2 三个完整块都取得原始 G 核验及云清理收据之后才生成本报告。每块保留 1,000 个配对种子、两装备臂共 2,000 场；本次共 6,000 场、3,000 配对，种子覆盖 440001～443000。cast、tick、全部 outcome、原始事件累计字节及用例分母均动态来自实际原始 summary／cloud validation／G 收据，不借用等级 0 的结果。

原生 mixed 源为 `581cd9f74962dd61424e77c529b1259afbb39fe7`，业务源仍为 B042，instrumentation 为 `66c7420532536431b906d1fdb1e68d6d3448e6b9`。372 文件中只有 collector 与 validator 两个显式 override，其余 370 原业务／源文件不变；Domain 三个原 hash 相同，Numerics 明确属于新 instrumented runtime。每块显式 16 GiB 未压缩原始事件预算，128 MiB 单 part／encounter 上限和 512 MiB 压缩输出预留不变。旧 2 GiB 限制是否满足分别照实记录，不把旧限制失败改名为通过。

报告复查完整 G 归档及全部已提取成员的当前字节 SHA，核对 collector-proof 三个解析对象及原 SHA与 native manifest／summary／validation 相同，复用 transport 已完成的完整 gzip CRC／raw SHA／条数证明，不再重演大量原始事件的业务 oracle。独立原生 validator 四个负对照及 collector 三个元数据负对照必须都拒绝错误数据。云清理收据必须对应同一份原始 G 归档、manifest 和 backup receipt SHA。

原先 90 个旧源逻辑 G 单元加上火属性等级 0 的三个块及本次等级 5 三个块，封闭子集后共 96／360 个逻辑单元、192,000 场、96,000 配对；成功完整原生执行尝试为 97，含那一次另命名的缺失原始文件恢复尝试，逻辑块仍只计一次。还剩 264 块、528,000 场、264,000 配对；这些数字是本子集之后的记账，不宣称其他并行任务的实时结果，三套 collector pilot 也不混入完整块计数。旧源与新 mixed 源分别保留 90／6 个逻辑块的明确来源。

完整原始归档与事件留在 G 盘 `outputs/pr13-tencent-20261009/cap-experiment-full-r3-raw/`。本目录只保存原始结果、预注册、collector-proof、native summary／小型 manifest、cloud validation、G 和云清理收据以及来源记录。原始结果中 transfer 前的 `G_backup_verified=false` 是历史快照，未修改；后续 G 和清理证据独立保存。

未改卡组或平衡数值，守护者长对局仍在推进时不按时长直接判合同失败。完整正式统计、用例适用性、EXPERIMENT／MAIN 仍待完成；原 master register 不变，容量测试保持暂缓，真人体验不在本次自动测试范围。报告没有执行云操作、原生游戏或本地业务 oracle；原始 JSON 按字节保存，新增文本 UTF-8 LF。提交后须核对实际 committed Git blob bytes 与 manifest。
