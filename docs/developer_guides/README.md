# 开发者指南

本目录包含 RunJPLib 项目的技术开发指南和最佳实践文档。

## 指南列表

### 认证与安全
- **[Admin CSRF Token 处理完整指南](admin_csrf_handling.md)** - Admin 后台所有 CSRF Token 处理的完整解决方案
- **[CSRF 快速参考](CSRF_QUICK_REFERENCE.md)** - 紧急情况下的快速修复指南

### 数据库
- **[数据库设计](database_design.md)** - 数据库架构、集合结构和索引策略

### AI 与算法
- **[推荐算法](recommendation_algorithm.md)** - 博客推荐的时间权重算法实现
- **[日志系统](logging.md)** - 日志记录体系和专项日志配置

### 开发工具
- **[工具使用](tools.md)** - 命令行工具和数据迁移脚本的使用指南

## 功能指南

功能模块的详细设计和使用说明位于 `docs/feature_guides/` 目录：

- **[招生信息处理器](../feature_guides/university_info_processor.md)** - PDF 处理流水线、校对补强、再生成
- **[本地 OCR 导入](../feature_guides/university_info_processor_local_ocr.md)** - 本地 OCR + 线上后处理方案
- **[博客管理](../feature_guides/blog_management.md)** - 博客 AI 生成、可见性控制、Wiki 功能
- **[AI 对话系统](../feature_guides/university_chat.md)** - 混合搜索、隐私保护、同义词理解
- **[Admin 面板](../feature_guides/admin_panel.md)** - 后台管理功能概览
- **[博客 Wiki 功能](../feature_guides/blog_wiki.md)** - 自动大学名称链接

## 架构文档

- **[系统概述](../system_overview.md)** - 项目概览、功能模块和技术栈
- **[技术架构](../technical_architecture.md)** - 模块架构、任务管理、线程池、缓存策略
- **[部署指南](../deployment_guide.md)** - 生产环境部署和配置

## 新功能开发检查清单

### Admin 功能开发
- [ ] 阅读 [Admin CSRF Token 处理完整指南](admin_csrf_handling.md)
- [ ] 确保表单包含 CSRF token 隐藏字段
- [ ] API 调用包含 `X-CSRF-TOKEN` header（全大写）
- [ ] 使用正确的布局文件 `{% extends "admin/layout.html" %}`
- [ ] 测试表单提交和 API 调用功能

### 数据库操作
- [ ] 遵循 [数据库设计](database_design.md) 原则
- [ ] 添加适当的索引（参见 `utils/core/database.py` 中的 `ensure_indexes()`）
- [ ] 考虑数据一致性

### 日志记录
- [ ] 使用 [日志系统](logging.md) 指南
- [ ] 添加适当的日志级别
- [ ] 确保敏感信息不被记录
