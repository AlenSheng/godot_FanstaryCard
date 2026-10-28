# PR13 实际原 env 独占副本恢复审计

读取部署脚本实际使用的当前 /opt/fantasycard-github/server/.env，仅在独占 0700 目录创建 0600 字节副本、加入受控差异后从备份恢复。原／差异／恢复哈希分别记录，恢复副本与当前源逐字节一致，生产源 inode、mtime、mode 与内容保持不变。

精确当前声明函数据真实恢复哈希只标记本次字节恢复，健康仍 Unknown，runtime_rollback_verified false。适用边界仅是当次独占副本；不能推断旧历史恢复、当前健康、生产重启／回滚或 PG 恢复。私人副本在归档前移除，原 env 内容从未打印或归档；G 盘只保留来源代码、哈希和审计元数据，完整五成员 SHA／CRC 核对。

R1 路径定位到 /opt/fantasycard-app/.env 不存在，在读取／复制之前退出；失败记录保留。R2 按实际脚本目录完成，原缺口只补 AUDIT，POSTGRES 和其他层仍待验收。
