# 变更日志 (CHANGELOG)

本文档记录了RunJPLib项目的重要更改，包括新功能、架构更新、安全改进等。

## [2025-01-27] - GridFS架构重构

### 🚀 新功能
- **GridFS PDF存储**：将PDF文件从MongoDB文档迁移到GridFS
- **安全文件名策略**：使用UUID作为GridFS内部文件名，防止注入攻击
- **智能文件去重**：通过元数据检测重复文件，避免重复存储

### 🔧 架构更改
- **PDF存储方式**：从文档内嵌Binary改为GridFS引用
- **文件名管理**：内部使用UUID，用户显示使用原始文件名
- **元数据结构**：新增`pdf_file_id`字段，移除`original_pdf`字段

### 🛡️ 安全改进
- **防止文件名注入**：GridFS文件名使用随机UUID
- **元数据验证**：通过`university_name`和`deadline`验证文件身份
- **HTTP头安全**：避免非ASCII字符在响应头中的编码问题

### 📁 文件更改
- `routes/admin.py`: 上传逻辑使用GridFS
- `app.py`: PDF服务从GridFS读取文件
- `tools/migrate_to_gridfs.py`: 数据迁移脚本
- `docs/mongoDB_design.md`: 更新数据库设计
- `docs/GridFS_migration_guide.md`: 新增迁移指南
- `docs/admin_panel.md`: 更新管理面板文档
- `docs/数据管理工具.md`: 更新技术设计文档

### 🐛 问题修复
- **文档大小限制**：解决MongoDB 16MB文档大小限制
- **PDF服务错误**：修复HTTP响应头编码问题
- **文件上传失败**：解决"update command document too large"错误

### 📊 性能优化
- **文档查询速度**：移除大二进制数据，查询更快
- **内存使用**：减少MongoDB内存占用
- **网络传输**：PDF按需加载，减少不必要的数据传输

### 🔄 向后兼容
- **现有路由**：保持所有现有API端点不变
- **文件回退**：MongoDB无数据时自动回退到文件系统
- **迁移支持**：提供完整的迁移脚本和指南

## [2025-01-26] - MongoDB集成

### 🚀 新功能
- **MongoDB支持**：集成MongoDB作为主要数据存储
- **Admin管理面板**：提供数据上传、管理和查看功能
- **JWT认证**：管理员登录和API保护

### 🔧 架构更改
- **数据存储**：从文件系统迁移到MongoDB
- **路由重构**：支持MongoDB和文件系统双重数据源
- **缓存机制**：实现大学信息的智能缓存

### 📁 文件更改
- `routes/admin.py`: 新增管理面板路由
- `routes/index.py`: 支持MongoDB数据源
- `app.py`: 新增PDF服务路由
- `utils/mongo_client.py`: MongoDB连接工具

## 技术债务

### 🔴 高优先级
- 无

### 🟡 中优先级
- 考虑添加PDF文件压缩功能
- 实现GridFS文件的定期清理策略
- 添加文件上传进度监控

### 🟢 低优先级
- 优化GridFS查询性能
- 添加文件访问统计
- 实现文件版本管理

## 已知问题

### 🐛 已修复
- MongoDB文档大小限制问题
- HTTP响应头编码问题
- PDF文件上传失败问题

### ⚠️ 待观察
- GridFS在大文件下的性能表现
- 迁移脚本在大量数据下的稳定性

## 升级指南

### 从文件系统升级到GridFS
1. 备份现有MongoDB数据
2. 运行迁移脚本：`python tools/migrate_to_gridfs.py`
3. 验证迁移结果
4. 清理备份数据（可选）

### 从旧版本升级
1. 更新代码到最新版本
2. 检查MongoDB连接配置
3. 运行必要的迁移脚本
4. 测试所有功能

## 贡献指南

- 所有架构更改必须在`docs/`目录下记录
- 新功能需要更新相应的文档
- 重大更改需要更新此变更日志
- 遵循现有的代码风格和架构模式
