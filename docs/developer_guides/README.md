# 开发者指南

本目录包含 RunJPLib 项目的技术开发指南和最佳实践文档。

## 指南列表

### 🔐 认证与安全
- **[Admin CSRF Token 处理完整指南](admin_csrf_handling.md)** - Admin 后台所有CSRF Token处理的完整解决方案
  - 表单提交的 CSRF 保护
  - API调用的 CSRF Header 处理
  - Admin聊天功能的特殊处理
  - PDF上传等特殊情况
  - 2025-09-06 重大修复总结
- **[CSRF 快速参考](CSRF_QUICK_REFERENCE.md)** - 紧急情况下的快速修复指南
  - 常见错误和解决方案
  - 已修复功能列表
  - 开发检查清单

### 🗄️ 数据库
- **[数据库设计](database_design.md)** - 数据库架构和设计原则
- **[日志系统](logging.md)** - 日志记录和监控指南

### 🤖 AI 与算法
- **[推荐算法](recommendation_algorithm.md)** - 内容推荐算法实现
- **[工具使用](tools.md)** - 各种开发工具的使用指南

## 快速参考

### 新功能开发检查清单

#### Admin 功能开发
- [ ] 阅读 [Admin CSRF Token 处理完整指南](admin_csrf_handling.md)
- [ ] 确保表单包含 CSRF token 隐藏字段
- [ ] API调用包含 `X-CSRF-TOKEN` header
- [ ] 使用正确的布局文件 `{% extends "admin/layout.html" %}`
- [ ] 测试表单提交和API调用功能
- [ ] 验证不被重定向到登录页面

#### 数据库操作
- [ ] 遵循 [数据库设计](database_design.md) 原则
- [ ] 添加适当的索引
- [ ] 考虑数据一致性

#### 日志记录
- [ ] 使用 [日志系统](logging.md) 指南
- [ ] 添加适当的日志级别
- [ ] 确保敏感信息不被记录

## 贡献指南

1. 在开发新功能前，先阅读相关指南
2. 遵循项目的最佳实践
3. 及时更新相关文档
4. 遇到问题时，先查看是否有相关指南

## 更新日志

- **2025-09-05**: 添加 Admin CSRF Token 处理指南
  - 解决重复出现的 CSRF token 问题
  - 提供完整的开发检查清单
  - 包含历史案例和最佳实践
  - 创建快速参考卡片
  - 建立标准化的开发流程
