# 跨服务器传输功能设计文档

## 概述

支持从 Server B（PDF 处理服务器）将已处理完成的大学招生信息传输到 Server A（生产服务器）。两台服务器均运行 RunJPLib 项目，通过 HTTP API 进行单向数据推送。

## 架构

```
Server B (处理服务器)                         Server A (生产服务器)
┌──────────────────────┐                     ┌──────────────────────┐
│ Admin 面板            │                     │                      │
│                      │   multipart POST    │ /api/transfer/receive│
│ 选择已完成任务/大学   ──────────────────────→│                      │
│ 点击「传输」          │   Authorization:    │ 验证 token           │
│                      │   Bearer <token>    │ 校验 PDF checksum    │
│ 打包:                │                     │ 存入 GridFS+MongoDB  │
│  - university JSON   │                     │ 或标记为冲突待处理    │
│  - PDF binary        │                     │                      │
└──────────────────────┘                     └──────────────────────┘
```

## 传输内容

每个大学传输一个 multipart 请求，包含：

| 部分 | 类型 | 内容 |
|------|------|------|
| `data` | JSON | university 文档字段（不含 `_id`、`content.pdf_file_id`） |
| `pdf` | binary | GridFS 中的原始 PDF 文件 |
| `pdf_checksum` | string | PDF 文件的 SHA256 哈希值 |

### data JSON 结构

```json
{
  "university_name": "東京大学",
  "university_name_zh": "东京大学",
  "deadline": "2026-03-01T00:00:00",
  "created_at": "2026-02-15T10:30:00",
  "is_premium": false,
  "tags": ["国立", "关东"],
  "content": {
    "original_md": "...",
    "translated_md": "...",
    "report_md": "..."
  },
  "pdf_checksum": "sha256:abcdef...",
  "original_filename": "東京大学_20260215.pdf"
}
```

## 冲突处理策略

Server A 接收到数据后，按 `university_name` 查找是否已存在：

| 场景 | 行为 |
|------|------|
| 不存在同名大学 | 直接插入 |
| 存在且 PDF checksum 相同 | 自动覆盖（更新文本内容） |
| 存在但 PDF checksum 不同 | 存入 `transfer_conflicts` 集合，等待管理员处理 |

### transfer_conflicts 集合结构

```json
{
  "_id": "ObjectId",
  "university_name": "東京大学",
  "incoming_data": { "...完整 university 文档..." },
  "incoming_pdf": "Binary (GridFS ObjectId，临时存储)",
  "incoming_checksum": "sha256:...",
  "existing_university_id": "ObjectId",
  "existing_checksum": "sha256:...",
  "status": "pending",
  "received_at": "datetime",
  "resolved_at": "datetime | null",
  "resolution": "accepted | rejected | null"
}
```

管理员可在 Server A 的后台对冲突执行：
- **接受**：用传入数据覆盖现有数据
- **拒绝**：丢弃传入数据

## 安全

- 共享密钥 `TRANSFER_SECRET_TOKEN`，配置在两台服务器的 `.env` 中
- 接收端验证 `Authorization: Bearer <token>` 请求头
- 接收端点 `/api/transfer/receive` 不经过 `@admin_required`（跨服务器调用无 JWT），仅校验 token

## 配置项（.env）

```bash
# Server B（发送方）
TRANSFER_TARGET_URL=https://server-a.example.com   # Server A 地址
TRANSFER_SECRET_TOKEN=your-shared-secret            # 共享密钥

# Server A（接收方）
TRANSFER_SECRET_TOKEN=your-shared-secret            # 同一密钥
```

## API 端点

### 发送端（Server B，需要 admin 登录）

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/admin/api/transfer/send` | 传输选中的大学到 Server A |
| GET  | `/admin/api/transfer/config` | 获取当前传输配置状态 |

### 接收端（Server A，token 验证）

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/transfer/receive` | 接收来自 Server B 的数据 |

### 冲突管理（Server A，需要 admin 登录）

| 方法 | 路径 | 说明 |
|------|------|------|
| GET  | `/admin/api/transfer/conflicts` | 获取待处理冲突列表 |
| POST | `/admin/api/transfer/conflicts/<id>/resolve` | 处理冲突（接受/拒绝） |

### 页面路由

| 方法 | 路径 | 说明 |
|------|------|------|
| GET  | `/admin/transfer` | 传输管理页面（发送 + 冲突管理） |

## 文件结构

```
utils/transfer/
├── __init__.py
├── sender.py      # 发送逻辑：打包数据 + POST 到目标服务器
└── receiver.py    # 接收逻辑：验证 + 冲突检测 + 存储

routes/admin/
└── transfer.py    # 所有传输相关路由

templates/admin/
└── transfer.html  # 传输管理页面
```

## 用户流程

### 从 Server B 发送

1. 进入「数据传输」页面
2. 页面上半部分显示传输配置状态（目标 URL 是否已配、token 是否已配）
3. 页面中部分为两种选择方式：
   - **按已完成任务选择**：列出所有状态为 completed 的 PDF_PROCESSING / OCR_IMPORT 任务
   - **按大学列表选择**：列出所有大学，支持勾选
4. 勾选后点击「传输到生产服务器」
5. 逐个传输，显示每个的结果（成功/已存在自动覆盖/冲突待处理/失败）

### 在 Server A 处理冲突

1. 进入「数据传输」页面
2. 页面下半部分显示冲突列表（仅当有冲突时可见）
3. 每个冲突显示：大学名、接收时间、现有数据摘要 vs 传入数据摘要
4. 管理员点击「接受」或「拒绝」
