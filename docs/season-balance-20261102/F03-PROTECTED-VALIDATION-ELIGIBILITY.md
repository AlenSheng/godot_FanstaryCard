# F03 保护测试门禁与正式验证可执行性

2026-11-07。本批仅读取固定保护测试DLL的PE元数据，没有执行加载测试程序集、构造属性、调用数据提供者/测试方法、启动PG或对局。它是放行前盘点，不是测试通过或保护证书；F03仍未验收，整体33/35。

## 实际盘点

Domain461、Server736，共1197个Fact/Theory方法定义；223个Theory定义不能直接等同于223条实际测试或游戏场数。773个无属性门禁，424个SkipUnless，后者分36显式手工/预算门禁及388数据库/专用隔离夹具门禁。没有无条件Skip或SkipWhen。属性数据解码均成功，输入DLL前后SHA保持。

36个手工类开关包括Enabled31、MatrixEnabled1、FinalNineEnabled1、CandidateEnabled2、ReuseEnabled1；有些是零场次预检，因此不能把36全部算成需要36场。数据库/隔离类为HasTestDatabase365、HasRealClientDatabase8、HasPrivateDatabase14、HasOwnedRollbackFixture1；仅有数据库地址不证明其他专用夹具已满足。

每个类型/方法、属性Skip文本、SkipUnless、属性blob SHA和测试程序集SHA完整记录。当前源码的环境开关另存路径/SHA映射；不通过反射实例化Enabled属性来猜测执行资格。

## 当前放行缺口

现有validate_protected_server只创建隔离PG、设置FANTASYCARD_TEST_POSTGRES及E2E打包ServerDLL，然后全套执行并要求无跳过。它没有为手工预算开关提供明确授权/冻结计划；直接调用会跳过相应方法，或若盲目全开则可能重跑封账数值队列、触碰预算。两者都不能诚实生成完整无skip证书。

本批没有修改验证器、抑制跳过、以50快照/镜像工具检查代替全套测试，也没有移除候选标记。固定suite来自075d0c4e导出，产品源码至今一致，但之后新增的F01/配对路线测试不在这批suite里；未来最终导出和覆盖计划必须对应实际固定输入。

下一步必须形成允许执行和既有证据复用的明确覆盖：保留所有未跑/跳过及已封账范围；若执行许可不足则继续候选，不写假全套证书。门禁盘点本身不证明测试体没有新匹配或其他副作用，实际选择前仍要按源码和原要求核查。

D03仍308、F01封300、B05封330；D2拟9场至317尚待答复。本机持续2GiB、1GiB启动/三点3GiB准入、隐藏BelowNormal单重编译保持，探针二进制私有，全部句柄已终态。生产未改动。

见[范围结果](evidence/F03-protected-test-inventory-r1/result.json)、完整元数据原件、属性/环境映射和读取器源代码，逐SHA清单。
