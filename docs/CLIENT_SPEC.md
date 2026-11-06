# 客户端规范

## 邮件大厅入口

大厅导航提供邮件入口和未读高亮。进入后调用 `GET /api/v1/mail`，按服务端顺序渲染标题、正文、附件；点击领取调用 `POST /api/v1/mail/{mailId}/claim`，成功后刷新大厅资源与邮件列表。邮件图标资源为 `client/assets/UI/Hall/mail_icon.svg`。

红点配置来自 `client/data/catalog.json` 的 `MailRedPoint`：`hallEntry=mail`、`showUnreadCount=true`、`maxBadgeCount=99`。大厅刷新时同步未读数量，导航和大厅身份行均显示数量角标。
