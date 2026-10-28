# S6 B08.1 当前 EXPERIMENT 补齐

腾讯云在当前原登记表上按 case/profile 补入三条 EXPERIMENT，原始 54000 行/486000 次事件、三组独立 seed、三职业六档、完整 gzip/原文哈希与快照记录均已核验。12 个完整原始/元数据文件共 56315730 字节已本地备份，原文 221244000 字节及全部 CRC/哈希/行数一致。

B08.1 仍为 Partial，三条 RENDER 尚缺，不把 native fixture 或 OFFLINE 预测当作实际界面。EXPERIMENT 缺口 137→134；当前 14 Accepted、105 Partial、2 Failed、11 ReadyForAcceptance 保持。共 33 包/132 项/396 原检查不变，其他 131 项、其他层次缺口、所有门、严格失败/容量暂缓及真人排除完全保持。

当前实现/原生/解析来源 90713f2fc032178fdcb2cc26b479070bb822ccaa，旧 case 来源保留历史。云端合并归档 385016 字节，SHA 4f8205bedef5c30467083f24cf81049bd2b1fc1561d2671ce552c29d6fc7638f，四份产物逐字节核验。当前指针转本目录，回滚恢复 S6-after-b07-authoritative-render 指针。GitHub AccountBilling 零步骤仍未通过，未授予 MAIN。
