# F03 最新集合源的双平台集成

2026-11-07。集合75d7ef91与此前已验证的Google/Steam候选分别完成新的隔离合并和完整Release解决方案编译，两套均0警告/0错误。此为F03子链路进展；整体仍33/35，D03及F03未完成，未更新正式目标分支或生产。

Google以bc24f56e为原候选，最新隔离提交406fb2eb93b3f02f93853663c38a6a59fee1c721；Steam以14b3a172为原候选，最新隔离提交018cd7ab51f94897e275d0baca041bdbc7cc49a5。两次合并均保留平台父提交与完整集合父提交，无新增冲突。

两候选已以非强制原子推送保存到codex/season-balance-google-candidate-20261107和codex/season-balance-steam-candidate-20261107，并独立查询远端逐SHA确认。它们用于保留和审阅集成源码，不是正式release_google/release_steam分支。

逐路径核对server/src、protocol、client/ui/state/network/data及config，新候选相对各自已验证候选的产品源码变化为0；近期新增F01控制器、当前D03报告及证据已进入各自合并树。Google登录/注销、Steam票据/昵称和11语入口修正均保留。完整编译固定4947/4935项输入且前后SHA不变；协议原生成器分别检查76实时/114HTTP/71路由及76实时/112HTTP/66路由通过。

之前平台功能、PG/HTTP/WSS与实际多语言三宽UI证据按原范围保留。本轮没有新平台SDK实测、UI渲染或完整玩法验收声明，也没有重新运行这些已验证矩阵。

两个任务自有隔离检出各留下840份Godot自动更新的.import元数据，先把原字节无损归档并逐成员验SHA，再仅将这些精确文件恢复到已验证提交，随后合并。未处理其他项目或修改原画面证据；当前两检出均干净。完整构建及其未保护程序集存于原私有ACL目录，不发布到Git。

实际远端release/release_google/release_steam/main仍为15198cb5/fdd47a1f/49acae01/5658c57a；不是把隔离提交误报成正式发布。D03总账299/300、补9场申请仍待答复，F01为255/300、B05封账330，新增实战0。本机持续2GiB、原1GiB启动/三点3GiB准入、单重隐藏BelowNormal保持，未使用云端资源或改变生产。

见[本轮结果](evidence/F03-current-platform-r1/result.json)、[双平台独立核查](evidence/F03-current-platform-r1/f03-current-platform-audit-r1.derived.json)及逐源/构建日志与原件清单。D03仍有严格15%、成长/收益/持续性缺口，正式切换备份、受保护部署、重启及公网新版本核验仍需完成。
