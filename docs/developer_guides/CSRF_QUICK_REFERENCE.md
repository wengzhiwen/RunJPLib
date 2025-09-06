# 🚨 Admin CSRF Token 快速参考

## 问题症状
- 点击 Admin 页面按钮时出现 "Missing CSRF token" 错误
- 用户被重定向到登录页面
- JWT validation failed
- "CSRF double submit tokens do not match"
- 404 Not Found (前端聊天)

## 快速修复

### 1. 表单修复
```html
<!-- 在表单中添加 -->
<input type="hidden" name="csrf_token" id="csrf_token" value="">
```

### 2. API调用修复
```javascript
// ✅ 正确的API调用
fetch('/admin/api/your-endpoint', {
    method: 'POST',
    headers: {
        'Content-Type': 'application/json',
        'X-CSRF-TOKEN': getCSRFToken() || ''  // 注意：TOKEN全大写
    },
    body: JSON.stringify(data)
})
```

### 3. 常见错误修复

**❌ Header名称错误**:
```javascript
'X-CSRF-Token': csrfToken  // 错误
```

**✅ 正确**:
```javascript
'X-CSRF-TOKEN': getCSRFToken() || ''  // 正确
```

**❌ 布局文件错误**:
```html
{% extends "layout.html" %}  <!-- 错误 -->
```

**✅ 正确**:
```html
{% extends "admin/layout.html" %}  <!-- 正确 -->
```

**❌ 前端聊天API路径错误**:
```javascript
const apiBaseUrl = `${window.location.pathname}/chat/api/`;  // 错误
```

**✅ 正确**:
```javascript
const apiBaseUrl = `/api/chat/${universityName}/`;  // 正确
```

## 已修复的功能 (2025-09-06)

### ✅ Admin表单功能
- 大学标签工具 (`/admin/university-tagger`)
- 博客编辑 (`/admin/blog/edit/<id>`)
- 大学信息编辑 (`/admin/edit_university/<id>`)

### ✅ Admin API功能
- 博客生成 (`/admin/api/blog/generate`)
- PDF上传 (`/admin/api/pdf/upload`)
- PDF任务管理 (重启/启动/队列处理)
- Admin聊天 (所有相关API)

### ✅ 前端功能
- PDF处理器 (布局文件修复)
- 前端聊天 (API路径修复)

## 检查清单

开发新Admin功能时，请确保：
- [ ] 表单包含 `<input type="hidden" name="csrf_token" id="csrf_token" value="">`
- [ ] API调用包含 `'X-CSRF-TOKEN': getCSRFToken() || ''`
- [ ] 使用正确的布局文件 `{% extends "admin/layout.html" %}`
- [ ] Header名称使用 `X-CSRF-TOKEN` (全大写)
- [ ] 前端聊天使用正确的API路径格式

## 详细指南
📖 完整指南: [Admin CSRF Token 处理指南](admin_csrf_handling.md)

---
*最后更新: 2025-09-06*
