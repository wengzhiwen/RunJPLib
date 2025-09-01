# 大学聊天系统 API 文档

## 概述

大学聊天系统提供RESTful API接口，支持智能对话、会话管理、隐私保护等功能。所有API都支持浏览器会话ID验证，确保用户隐私安全。

## 基础信息

- **基础URL**: `/university/{university_name}/chat/api/`
- **认证方式**: CSRF令牌 + 浏览器会话ID
- **数据格式**: JSON
- **字符编码**: UTF-8

## 通用响应格式

### 成功响应
```json
{
  "success": true,
  "data": {...},
  "message": "操作成功"
}
```

### 错误响应
```json
{
  "success": false,
  "error": "错误描述",
  "error_code": "ERROR_CODE"
}
```

## API 端点

### 1. 创建/恢复会话

**端点**: `POST /university/{university_name}/chat/api/create-session`

**描述**: 创建新会话或恢复现有会话

**请求参数**:
```json
{
  "browser_session_id": "bs_1733123456789_abc123def"
}
```

**响应示例**:
```json
{
  "success": true,
  "session": {
    "session_id": "uuid-session-id",
    "university_name": "东京大学",
    "csrf_token": "csrf-token-string",
    "created_at": "2025-09-01T12:00:00.000Z",
    "is_restored": true,
    "message_count": 5
  },
  "notice": "继续之前的对话..."
}
```

**隐私保护**:
- 优先使用 `browser_session_id` 查找现有会话
- 如果没有浏览器会话ID，回退到IP地址查找（兼容性）
- 确保会话归属验证

### 2. 发送消息

**端点**: `POST /university/{university_name}/chat/api/send-message`

**描述**: 发送消息并获取AI回复

**请求头**:
```
X-Session-ID: session-id
X-CSRF-Token: csrf-token
```

**请求参数**:
```json
{
  "session_id": "uuid-session-id",
  "message": "这所大学的申请截止日期是什么？"
}
```

**响应示例**:
```json
{
  "success": true,
  "response": "根据东京大学的招生信息...",
  "processing_time": 2.5,
  "session_info": {
    "message_count": 6
  }
}
```

**安全限制**:
- 消息长度限制：300字符
- 速率限制：15次/分钟
- 每日消息数限制：根据用户IP统计

### 3. 获取聊天历史

**端点**: `POST /university/{university_name}/chat/api/get-history`

**描述**: 获取会话的聊天历史记录

**请求头**:
```
X-Session-ID: session-id
X-CSRF-Token: csrf-token
```

**请求参数**:
```json
{
  "session_id": "uuid-session-id",
  "browser_session_id": "bs_1733123456789_abc123def"
}
```

**响应示例**:
```json
{
  "success": true,
  "messages": [
    {
      "role": "user",
      "content": "这所大学的申请截止日期是什么？",
      "timestamp": "2025-09-01T11:30:00.000Z"
    },
    {
      "role": "assistant", 
      "content": "根据东京大学的招生信息...",
      "timestamp": "2025-09-01T11:30:02.000Z"
    }
  ],
  "total_count": 10
}
```

**隐私保护**:
- 严格验证浏览器会话ID匹配
- 只返回最近20条消息
- 确保会话归属验证

### 4. 健康检查

**端点**: `GET /university/{university_name}/chat/api/health`

**描述**: 检查服务状态和用户限制

**响应示例**:
```json
{
  "success": true,
  "status": "healthy",
  "service": "university_chat",
  "timestamp": "2025-09-01T12:00:00.000Z",
  "user_status": {
    "daily_message_count": 15,
    "degraded": false,
    "delay_seconds": 0
  }
}
```

## 隐私保护机制

### 浏览器会话ID

每个浏览器标签页/窗口都会生成唯一的会话标识符：

```javascript
// 格式: bs_timestamp_randomstring
// 示例: bs_1733123456789_abc123def
```

**特点**:
- 使用 `sessionStorage` 存储
- 无痕模式下自动隔离
- 浏览器标签页关闭时自动清除

### 双重验证

1. **新会话**：优先使用浏览器会话ID验证
2. **旧会话**：回退到IP地址验证（兼容性）
3. **严格权限**：确保会话归属正确

### 安全限制

- **IP级别限制**：防止API滥用
- **速率限制**：防止攻击
- **CSRF保护**：防止伪造请求
- **会话超时**：1小时无活动自动过期

## 错误代码

| 错误代码 | 描述 | HTTP状态码 |
|---------|------|-----------|
| `FORBIDDEN_ORIGIN` | 请求来源不被允许 | 403 |
| `RATE_LIMIT_EXCEEDED` | 请求过于频繁 | 429 |
| `CSRF_TOKEN_MISSING` | 缺少安全令牌 | 403 |
| `CSRF_TOKEN_INVALID` | 安全令牌验证失败 | 403 |
| `RATE_DEGRADED` | 用户触发降级限制 | 429 |
| `SERVICE_UNAVAILABLE` | 服务暂时不可用 | 500 |

## 使用示例

### JavaScript 示例

```javascript
// 1. 创建会话
const createSession = async () => {
  const response = await fetch('/university/东京大学/chat/api/create-session', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json'
    },
    body: JSON.stringify({
      browser_session_id: getBrowserSessionId()
    })
  });
  
  const data = await response.json();
  if (data.success) {
    // 保存会话信息
    sessionStorage.setItem('session_id', data.session.session_id);
    sessionStorage.setItem('csrf_token', data.session.csrf_token);
  }
};

// 2. 发送消息
const sendMessage = async (message) => {
  const response = await fetch('/university/东京大学/chat/api/send-message', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'X-Session-ID': sessionStorage.getItem('session_id'),
      'X-CSRF-Token': sessionStorage.getItem('csrf_token')
    },
    body: JSON.stringify({
      session_id: sessionStorage.getItem('session_id'),
      message: message
    })
  });
  
  return await response.json();
};

// 3. 获取历史
const getHistory = async () => {
  const response = await fetch('/university/东京大学/chat/api/get-history', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'X-Session-ID': sessionStorage.getItem('session_id'),
      'X-CSRF-Token': sessionStorage.getItem('csrf_token')
    },
    body: JSON.stringify({
      session_id: sessionStorage.getItem('session_id'),
      browser_session_id: getBrowserSessionId()
    })
  });
  
  return await response.json();
};
```

## 最佳实践

### 1. 隐私保护
- 始终在请求中包含 `browser_session_id`
- 使用 `sessionStorage` 存储敏感信息
- 避免在 `localStorage` 中存储会话信息

### 2. 错误处理
- 检查 `success` 字段判断请求是否成功
- 根据 `error_code` 进行相应的错误处理
- 实现重试机制处理临时错误

### 3. 用户体验
- 实现加载状态显示
- 提供清晰的错误提示
- 支持会话自动恢复

### 4. 安全考虑
- 定期刷新CSRF令牌
- 监控异常访问模式
- 实现用户友好的降级提示
