# 固定来源与重放

本独立实际命令、时点、exit、log SHA见 COMMANDS.json；所有固定源码与新编译 DLL 的 SHA见 SOURCE_METADATA_CHECKS.json。实际 fresh raw 在 `/workspace/pr13-main-two-ready-20261001/evidence/`，完整本地 SHA 索引在 `LOCAL_RAW_MANIFEST.json`，本份只保存关键hash，不上传raw。

A05固定源码 `62772be2a1bc28affffc3d057f259c8c5ded8e37`；固定报告 `1a7f533666164467ecd7de1604bde62db6d9106b:docs/reports/pr13-takeover-20260930/a05-guard-62772be2/`。原 `REPLAY.md`、`minimal-replay.json`、`source-green2-fixed.json` 给原完整命令和全部源文件manifest。LOAD02固定源码 `dfb3f88a73efd85cc4ed12b8d49038bebbb1f953`；固定报告 `b5a746a621a116f7d6e99857f8f8e0c063d2c159:docs/reports/pr13-takeover-20260930/load02-timeout-dfb3f88a/`。其原 `prepare_load02_fixed_source.py --repo <authorized_local_repo> --manifest <source_manifest> --output <new_directory>` 仅从 Git 对象材料化声明文件，亦用于此次A05准备；SHA读取固定manifest的integration_sha并验证，不接受浮动分支。

先 `source /workspace/relicround-env/activate.sh` 验工具版本。取固定报告目录和精确固定 SHA 的源码，以原source manifest逐文件验证，不取当前工作树字节。每个来源内部新restore/build，不执行历史bin/obj/validation-bin。配置自己的 Unix PG data/socket、host reject、空listen address、max_connections64/shared_buffers32MB及Poolingtrue/MaximumPool8，设置自己的 FANTASYCARD_TEST_POSTGRES 和 A3GAME_GODOT_EXECUTABLE。FANTASYCARD_PROCESS_SERVER_DLL 指向该固定 source 内新Release DLL，FANTASYCARD_PROCESS_SOURCE_SHA为该固定SHA，FANTASYCARD_PROCESS_EVIDENCE为新独立目录。

运行原未过滤 `dotnet test tests/FantasyCard.Server.Tests/FantasyCard.Server.Tests.csproj -c Release --no-build --logger 'trx;LogFileName=tests.trx' --results-directory <new_evidence>`。LOAD02另原 focused filter `FullyQualifiedName~Real_LOAD02_timeout_STOP_preserves_original_business_truth` 和 `python -m unittest discover -s tools/tests -v`。filter仅补充定位/关键case重放，不能代替原完整C-SERVER。

修前RED是实际 `2dda41b32ba89f06d5ea722ae8b9469004940c22` 生产源码加原 `8068783331da07ec68354c1874eb0d65adea632f` 报告声明的九个仅测试overlay文件。prepare_red.py逐Git对象读取、验证原九hash并断言overlay不覆盖任何已tracked生产文件；没有改实现或断言。原filter为 `FullyQualifiedName~Frozen_f812_actual_poll_return_during_ACK_must_not_restore_completed_receipt`，真实expected failure exit1，raw f812标签是旧业务baseline名，实际runtime2dda单列。固定62772完整套件包含原同causal GREEN以及原三个canonical/guard/MN/资产只读审计。

本次唯一追加诊断是原新增失败测试 `FullyQualifiedName~MarkRunning_commit_response_loss_retries_same_room_and_restart_restores_it` 在相同62772与原ownedPG配置下单项重放，exit0。不修改其line75期望、不过滤出它来使全套变绿、不声称根因确认。首次62772全套298/1/0 exit1必须保留；dfb完整302通过包含相同未变测试，也不能替换62772整套结果。

verify_a05_actual.py、verify_load02_actual.py只读原客户端/原业务报告/PG审计收据，不回写实现、assertions或权威字段。CLEANUP_CHECKS保留实际74个Program host启停配对、148个已退出子进程状态、原T01 exit1与其余exit0区分，以及两ownedPG查询0schema/0connection、stop0/status3、data/socket删除；不碰其他进程/PID1。完整MAIN Accepted登记留给父协调。
