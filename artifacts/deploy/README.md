# 腾讯云服务器更新

腾讯云实例与私有 GitHub 仓库使用只读 Deploy Key 连接。当前跟踪分支为 `release`，不是 `main`。云端 Git 工作副本在 `/opt/fantasycard-github`；原始上传的代码仍保留在 `/opt/fantasycard-app/server`。

从本机执行更新（需要部署 SSH 私钥）：

```powershell
ssh -i "C:\Users\SHENGJIAHAO\AppData\Local\CodexTempKeys\gpt-deploy.pem" ubuntu@43.172.70.182 '~/fantasycard-update'
```

或者先 SSH 登录服务器，再执行 `~/fantasycard-update`。必须先将代码推送到 GitHub 的 `release` 分支；仅在本机提交不会更新云端。

脚本先验证只允许快进更新，备份 PostgreSQL 至 `/opt/fantasycard-app/backups/`，构建镜像，然后只重建应用容器，最后检查 `/health/ready`。不会清空数据库或覆盖云端 `.env`。如分支被强制推送、构建失败或健康检查不通过，脚本会停止并保留备份供人工检查。
