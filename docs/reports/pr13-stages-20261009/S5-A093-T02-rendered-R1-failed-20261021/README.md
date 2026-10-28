# A093-T02 当前原生渲染补测 R1：失败保留

本轮当前原生测试仅执行1项，TRX为1 Failed、0 Passed，测试进程退出1。数据库对新N的原断言要求Running，实际为Starting；APP未OOM。未关闭LIVE或RENDER缺口，登记仍为100 Accepted、24 Partial、8 Ready，32项未验收、113个案例/层级缺口。release提交86ddee23不受此未通过补测影响。

实际输出14张原图，原计划24张。原始观察中的actual_new_N与actual_old_M全相同，且卡牌点击未改变选牌，因此图片不能作为进入新N的证据。running-N、callbacks-observed、recovered-N这些文件名不是实际阶段通过证明。没有完成协议result、渲染result和client.log，不能声称Godot退出干净、实际OS重启或B最终退出已验收。

原C#测试、资产断言、180秒测试期限均未修改。夹具本轮按2局、5账号、1份初始装备计入累计预算，成功进入新N及自然完成样本均为0；重试前必须登记累计修订。当前证据尚不足以判定产品根因，需分别查原生检查失败、旧M状态来源与ActionBar阶段真实UI控件。不能因修正渲染观察器就授予业务通过。

原始包114份文件共22,915,424字节已逐文件SHA256核对并存于G:\PR13Evidence\A093T02-current-rendered-route-20261021-r1-originals。压缩包20,066,552字节，SHA256 dfac25e95c7681e7877488fb5c9fefcd3b493e3438c526a5b6299d6ee571975f。PG实际18.6，前后私有schema数0；结束前pg_dump退出0。所属APP/PG容器已删除、systemd主PID0；生产指纹不变。云端本轮代码目录仍保留，原始证据不删除。

本机只进行了先前已记录的无窗口headless解析，全部新原图来自既有云主机Xvfb/Mesa。没有修改正式UI或生成美术，没有放宽业务判据，也没有增加云主机。
