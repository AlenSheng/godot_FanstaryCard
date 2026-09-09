# FantasyCard 本地数据库备份

双击 `../backup-all-local-data.bat` 会在本目录生成：

- `fantasycard-local_yyyyMMdd-HHmmss.dump`：PostgreSQL 自定义格式的完整数据库转储。
- 同名 `.sha256`：跨设备复制后的完整性校验。

转储包含全部本地用户和业务数据，包括身份绑定、会话令牌哈希、钱包、材料、卡牌、编组、装备、准备快照、幂等记录及迁移表。它属于敏感数据，已被 Git 忽略；请通过可信介质复制，不要提交到仓库或上传到公开位置。

目标设备应使用相同或更新的 FantasyCard 服务器代码和 PostgreSQL 主版本。恢复前先保留目标数据库自己的备份，再使用容器内的 `pg_restore` 恢复该 `.dump`。
