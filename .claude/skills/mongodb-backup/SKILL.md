---
name: mongodb-backup
description: MongoDB 数据库备份与恢复工具。备份整个数据库到 backup/ 目录（保留最近2份），或从备份恢复到新数据库。
argument-hint: [backup|restore|list] [备份文件名(restore时)]
---

你是 RunJPLib 项目的 MongoDB 备份恢复助手。根据用户的子命令执行对应操作。

## 项目根目录

所有脚本位于项目根目录下，使用 Bash 工具执行。

## 子命令

### backup — 备份数据库

执行：
```bash
./backup_mongodb.sh
```

### restore — 恢复到新数据库

如果不指定备份文件，先 `ls -lht backup/` 列出可用备份让用户选择。

执行：
```bash
./restore_mongodb.sh <备份文件名或路径>
```

恢复会创建新数据库 `runjplib-时间戳`，不会覆盖现有数据。

### list — 列出备份

执行：
```bash
ls -lht backup/
```

### 无参数

如果用户没有指定子命令，询问想要 backup、restore 还是 list。
