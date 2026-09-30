# Codex Cloud 与受控测试服流水线（2026-09-30）

当前结论：**配置已实现并完成下列离线／本地隔离验证；尚不可部署。**
PR14 集成基线为 `release`，开发分支为 `codex/cloud-test-deployment-20260930`。
PR13 的实现及 132 项验收独立进行；本报告不能替代它。

## 授权与实际配置

- 用户指定 `release` 为开发、发布和受信任控制器来源。默认分支目前仍为
  `main`；此次没有修改默认分支，也没有合并或启用自动合并。
- 用户已批准明确的 **`owner_dispatch` 人工触发模式**。它不使用当前不可用的
  GitHub Required reviewers，也不声称配置了 GitHub 人工审批保护。
- 父任务通过用户界面核验 `silicon-valley-test` 为仅 `release` 的一条 Branch
  规则、0 tags；两个 Secret **名称**已存在。私钥由用户亲自录入，工具没有
  读取、导出或复制其值。公开主机公钥来自此前成功严格登录所匹配的记录，
  不是未验证扫描。**CI 登录仍未验证。**
- 用户 15:10 UTC 已授权任务推进所需的测试服重启。该授权不触发每次 push、
  PR 或 CI 自动重启，也不免除固定部署版本、构建、兼容性、互斥和证据门槛。
  本任务没有进行任何线上部署、重启或数据库恢复。线上操作先交父任务协调。
- `ubuntu@43.172.70.182:22` 的 sudo Docker 权限可控制整台测试服。它只进入
  Environment 部署作业的单个传输步骤，不进入 PR／构建／静态检查作业。
  未创建服务器凭据、注册 runner、安装持久权限或改变服务器安全设置。

GitHub 官方说明：私有仓库的 Environment 分支／Secret 能力和 Required
reviewers 能力不是同一功能；Free／Pro／Team 的 Required reviewers 限公开
仓库。不能从 Environment 已存在推断其审批功能可用。
[官方 Environment 文档](https://docs.github.com/en/actions/how-tos/deploy/configure-and-manage-deployments/manage-environments)。
当前 Cloud `gh api` 读取 Environment 返回 Forbidden；没有绕过网络限制。
运行时必须重新读取真实 API 配置，无法读取即失败，不凭 UI 报告放行。

## 每次运行的信任边界

`test-server-deploy.yml` 只有 `workflow_dispatch`，无 push、PR、定时或完成事件。
只允许 canonical repository 的 `refs/heads/release`。控制器完整 SHA 必须等于
`TEST_DEPLOY_APPROVED_WORKFLOW_SHA`。用户需先审查这一控制器版本；变量不能
代替代码审查。Environment API 必须证明只允许准确的 `release` Branch，
禁止 main、通配符、额外分支、tags、缺失类型或分页未完整核验的结果。

触发者和再次触发者必须是固定 owner `AlenSheng` / ID `20944685`；仓库 owner
ID 也必须一致。重跑 attempt > 1 被拒绝，需新建一次有记录的 dispatch。
每次输入 PR 号、完整目标 SHA、重复的目标 SHA、必要应用重启确认、已审查
回退基线完整 SHA，以及数据／快照兼容性确认。PR 必须仍开放、同仓库、
指向 release 且 head 未移动。输入经验证后才进入命令参数；没有表达式直接
插入 shell 输入。以上确认记录随运行 ID、attempt、控制器 SHA 进入 manifest。
必要重启可根据已有任务授权由父任务协调确认；不需要再次询问睡着的用户。

部署启用前的 repository variables：

| 名称 | 值／条件 |
| --- | --- |
| `TEST_DEPLOY_ENABLED` | 仅父任务确认全部门槛后设为 `true`；当前任务没有设置 |
| `TEST_DEPLOY_APPROVAL_MODE` | 明确设为 `owner_dispatch`，不接受隐式降级 |
| `TEST_DEPLOY_APPROVED_WORKFLOW_SHA` | release 上经过审查的完整控制器 SHA |

构建使用固定目标 SHA、无服务器密钥，执行 Domain／Server 测试并拒绝失败、
跳过或缺少实际 PostgreSQL 用例的 TRX。现有 Dockerfile 没有提交 ARG／LABEL，
因此由受信任的 `docker build --label org.opencontainers.image.revision=...`
设置 OCI revision。随后构建匹配的私有 build stage，复用现有
`tools/validate_docker_server.py` 验证最终混淆 DLL/hash、Linux 全套测试、
HTTP/WebSocket、强制重启、Production 本地认证禁用、DB outage/recovery 和清理。
仅通过后才能生成部署 manifest。验证工具拒绝存在真实 release key 的 checkout；
测试用 admin 值只存在于可丢弃隔离容器。私有编译产物、映射、DB dump、应用日志
和 `.env` 不上传到部署证据；部署 artifact 只有镜像、manifest 和清洁验证摘要。

部署 runner 重新核验 API、固定 PR 和控制器。Artifact ID 来自本次 build 输出，
API 必须证明正确名称／run／attempt／控制器 SHA、非过期、摘要和合理大小。
manifest 严格限定字段，核验 archive／健康脚本／两个控制模块／最终镜像证明的
SHA256。可执行控制器和健康脚本由新的可信 checkout 重新产生。
SSH 不读默认配置、不开 agent forwarding、不用密码／全局 known_hosts；强制
准确已有主机条目和 `StrictHostKeyChecking=yes`，不扫描、不隧道、不直接由 Cloud
连接线上服务器。Secrets 在取出写入 runner 临时 `0600` 文件后从子进程环境移除，
临时目录退出即删除。错误日志只输出异常类别／已知状态。

## 事务、备份、回退与未知状态

同一个 SSH 会话从 preflight 到外部接受／回滚持有
`/tmp/fantasycard-update.lock`，与旧 updater 共享。GitHub concurrency 不取消
已执行的部署。旧 updater 不应与此控制器同时操作，也不能在 active override
存在时忽略它继续按分支构建。

服务器 checkout、deployed-git marker、deployed-runtime marker 和运行 OCI
revision 在锁内重新核验。此前只读旧基线为
`8489fe97c7da71e1a5bfe1a860faf86fd4e0a4af`，镜像为
`sha256:e7defa05caeb1188afb4cfc4390d96900bfc10afb4996ced23a042fb09132697`；
这是旧版本，不能当作当前 PR13。现在代码不假定它仍在运行。

回退门槛同时要求明确的版本兼容性审查和保守的差异阻断：Persistence、
Server Rooms／Realtime、Domain、Contracts、csproj 迁移资源、启动入口、
配置／Compose／部署文件等变化均阻断。路径检查本身不能证明 app-only 回退
安全；人工兼容性确认也不能覆盖被阻断路径。需另行设计迁移兼容方案的目标
不能偷偷跳过检查。程序／经济语义仍可能影响旧版对新数据的读取，审查必须
覆盖这些语义，不能只看 SQL。

服务器 `.env` 仅作为现有 Compose 的参数路径传入，从不读、打印或复制。
备份用 `O_EXCL` 与 mode `0600` 安全创建，文件名含 run ID + attempt + source；
要求非空、`pg_restore --list` 成功，记录清洁的文件名／长度／摘要。**不自动恢复
数据库。** 新容器写入的数据仍留在数据库，回退只恢复应用镜像／override／marker。
若不兼容或不可逆，保持阻塞，备份存在不等于安全自动回退。

加载并验证不可变 image ID 与 OCI revision 后，持久化 `pending.json` 再激活。
候选通过本地 readiness、TLS 和 admin 暴露检查后，状态为 `awaiting_external`。
runner 从外部以真实 TLS 验证 readiness 和两个公共 admin 路径 404，再在同一
会话中发 accept。EOF、坏输入、外部失败、取消和正常操作总期限触发补偿。
只有本地＋外部通过、marker／accepted evidence 持久化成功后才移除 pending。
日志写入失败不能阻止补偿；补偿失败或终态不能可靠保存时保留 pending 阻断后续。

正常操作总预算 1500 秒，runner 为补偿预留 450 秒（控制会话 1950 秒），
SSH 传输另有限时。inspect／identity 查询各 15 秒、compose up 180 秒、健康重试
180 秒（单次 35 秒）。重复取消信号不打断补偿。SIGKILL／机器丢失／磁盘失效
仍可能阻止补偿：本地进程退出绝不等于远端完成回退。拿不到合格远端证据时
runner 写 `unknown` + `recovery_required`，CI 失败。不能自动重跑或清掉 pending。

父任务协调后可使用**同一固定 bundle**进行显式恢复；不包含新版本激活：

```text
python3 /opt/fantasycard-app/test-deploy/incoming/<run>-<attempt>/remote_deploy.py \
  --bundle /opt/fantasycard-app/test-deploy/incoming/<run>-<attempt> \
  --source-sha <原固定SHA> --run-id <原run> --run-attempt <原attempt> \
  --controller-sha <原控制器SHA> --recover
```

该命令即使恢复成功也返回失败部署语义；必须核对 `rolled_back`、旧镜像／marker、
本地和外部健康，以及资产／持久数据证据。不要把 CLI 非零解释为回滚一定失败，
也不要把无结果解释为成功。恢复期间仍用同一个共享锁。此任务未运行该线上命令。

## Cloud 初始化和 Start

仅支持无 root 的 Linux x64。默认工具目录 `/workspace/fantasycard-cloud-tools`。
Debian 13 用官方发行包的固定 SHA256；其他发行版用锁定的官方 SDK tar。
Godot 和 PostgreSQL 源码／便携构建工具均在下载后核验摘要，再安全解包。
构建先在临时目录完成，验证版本后才替换工具目录；缓存不能跳过摘要。
云镜像需已有 cc／make／Perl／Python venv／dpkg-deb 和运行库；缺失会明确失败，
不会申请 sudo、注册 runner 或更改宿主权限。Install 需要既定包管理器和 NuGet
域名访问。可用公开缓存 `FANTASYCARD_CLOUD_DOWNLOAD_CACHE`，以及独立 NuGet
缓存 `FANTASYCARD_CLOUD_NUGET_CACHE`；不拷贝任何凭据。

Install script：`bash tools/cloud/setup.sh`。
Start：`source tools/cloud/env.sh`，然后 `bash tools/cloud/start.sh`。
每个 shell 都必须 source；环境 UI 需使用可获得这些脚本的审查分支／固定版本。
此次只完成仓库配置，没有声称已修改父任务环境 UI。

PostgreSQL 只监听 mode `0700` 私有 Unix socket，host auth 为 reject，无 TCP。
Start 有锁且不会让后台 postgres／MSBuild 继承锁；恢复只使用 NuGet 缓存。
`bash tools/cloud/stop.sh` 可重复停止。
`bash tools/cloud/check.sh` 运行基线回归、云模块测试及最小 Godot loopback fixtures，
退出时清理该独立测试数据库并停止 PG。它不启动完整游戏的联网 autoload。

## 默认分支工作流发现依赖

GitHub 的 workflow_dispatch 入口要求该工作流文件存在于默认分支。
[官方触发说明](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#workflow_dispatch)。
默认 main 仍无本工作流；PR14 仍 Draft 且未集成 release。因此目前不能从 GitHub
UI 运行受信任 release 控制器。

最小后续方案：另行审查并授权在 **main** 增加同路径的纯注册工作流，只有相同
workflow_dispatch inputs、`permissions: {}` 和 `if: false` 的占位 job，不带
Environment、Secrets、checkout 或服务器操作。真正执行时在 UI／API 选
`ref=release`，加载 release 上审查过的完整实现。main 只提供发现入口，不是
发布基准或部署来源。也可另外授权将相同门禁工作流同步 main，其 jobs 仍严格
只运行 release；改动范围更大。此次没有写 main，没有合并 PR14，也没有改默认分支。

## 已执行证据与剩余阻塞

以下验证都在独立 Cloud，未依赖个人电脑：

| 项目 | 实际结果 |
| --- | --- |
| 精确接手提交／分支／初始工作区 | `1b49f4f22f83521fa055d73afc92107006b1f046`，干净 |
| Digest-locked 新安装＋重复安装＋停止恢复 | 通过；独立 `/workspace/pr14-tools`，.NET 10.0.400／Godot 4.7.2／PG 18.6 |
| 真实私有 PG 服务端回归 | 251 passed，0 failed，0 skipped |
| Godot 最小项目／codec／loopback transport | 通过；173 + 19 checks，0 failures |
| 云授权、artifact、事务、失败／信号测试 | 29 unittest 方法通过（含参数反例） |
| 真实 Docker scratch + PG controller drill | 接受／外部拒绝回退／坏健康回退均通过；资产行 12345 不变，0600 dump 可列举；清理通过 |
| actionlint v1.7.7（摘要核验）、Python 编译、全部 Bash 语法 | 通过；覆盖两个新增／改动工作流 |
| PR14 交接基线 Domain 回归 | **失败**：CombatAuthoritativeRulesTests 引用源码缺少的 useConsumptionBasedFenxian／useFractionalGuardianWeapon／快照成员；未改 PR13 来修补 |
| 最终游戏 Docker 本地构建／验证器 | **阻塞**：mcr.microsoft.com manifest 请求 Forbidden；没有扩大到全网或绕过限制 |
| GitHub 静态／安装／最终镜像 CI | 推送后核验；最终结果记录在 PR14 和完成报告 |
| 真实 Environment API／严格 SSH／线上 rollout | **未验证／未执行**；Secret 名称存在不代表登录成功 |

初次真实恢复测试暴露后台进程继承 Start 锁的问题，已修正并验证停止／恢复。
初次 scratch 容器因新 fixture 文件模式导致执行失败，已对新 fixture 的 COPY
显式设置可执行模式后完成三条真实演练。没有修改既有服务器权限。
服务端构建产生的 tracked bin/obj 已恢复，新增生成文件清理，不进入 PR14。
完整本地日志保留在 `/workspace/pr14-*.log`，结构化结果在
`/workspace/pr14-tools/evidence`；提交的清洁摘要见 `docs/reports/cloud-deployment-20260930/`。

部署前父任务需要一次集中确认：审查并集成控制器／注册入口，固定完整目标 SHA
与当前 baseline SHA，确认数据兼容性和线上独占窗口，检查启用变量、实际 API、
最终镜像证明、Strict SSH、备份及回退点，再记录已有任务授权下的必要重启范围。
若任一门槛失败，明确不可部署；CI 绿也不能等同 PR13 全量验收。
