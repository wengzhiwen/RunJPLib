# 数据库设计 (MongoDB)

本文档描述 RunJPLib 项目中 MongoDB 集合的结构和索引策略。

## 核心集合

### 1. `universities` - 招生信息

**文档结构**:
```json
{
  "_id": "<ObjectID>",
  "university_name": "String",
  "university_name_zh": "String",
  "deadline": "Date",
  "created_at": "DateTime",
  "is_premium": "Boolean",
  "tags": ["String"],
  "content": {
    "original_md": "String",
    "translated_md": "String",
    "report_md": "String",
    "pdf_file_id": "ObjectId"
  }
}
```

**字段说明**:
- `deadline`: 报名截止日期，BSON Date 类型（已从字符串迁移）
- `university_name_zh`: AI 识别的简体中文全称
- `tags`: 大学标签数组，如 `["国立", "難関", "理系"]`，由 LLM 驱动的标签工具生成
- `content.pdf_file_id`: 指向 GridFS 中 PDF 文件的 ObjectId

**索引策略**:
- `("is_premium", -1), ("deadline", -1)`: Premium 优先排序
- `("tags", 1)`: 单字段索引，标签筛选
- `("tags", 1), ("is_premium", -1), ("deadline", -1)`: 标签 + Premium + 截止日期
- `("tags", 1), ("deadline", -1)`: 标签 + 截止日期

### 2. `blogs` - 博客文章

**文档结构**:
```json
{
  "_id": "<ObjectID>",
  "title": "String",
  "url_title": "String",
  "publication_date": "String",
  "created_at": "DateTime",
  "md_last_updated": "DateTime",
  "html_last_updated": "DateTime",
  "content_md": "String",
  "content_html": "String",
  "is_public": "Boolean",
  "generation_details": {
    "mode": "String",
    "university_ids": ["ObjectID"],
    "user_prompt": "String",
    "system_prompt": "String",
    "generated_at": "DateTime"
  }
}
```

**字段说明**:
- `is_public`: 是否对公众可见。AI 生成的博客默认 `false`，手动创建的默认 `true`。
- `generation_details`: 可选字段，仅 AI 生成的博客包含。

**索引策略**:
- `url_title` (唯一): 通过 URL 查找文章
- `publication_date` (降序): 按发布日期排序
- `is_public`: 前端筛选公开文章

### 3. `access_logs` - 访问日志

记录对大学信息页和博客页的公开访问。

**索引策略**:
- `(timestamp, -1), (page_type, 1)`: 复合索引，用于仪表盘聚合统计

### 4. `chat_sessions` (即 chat_logs) - AI 对话会话

存储用户与 AI 的对话会话与消息。

**关键字段**:
- `browser_session_id`: 浏览器会话 ID，用于隐私保护
- `session_id`: 会话唯一 ID
- `user_ip`: 用户 IP（用于安全限制和旧会话兼容）
- `university_name`: 关联的大学名称
- `messages`: 消息数组
- `last_activity`: 最后活动时间

**索引策略**:
- `(browser_session_id, 1), (university_id, 1), (last_activity, -1)`: 隐私保护模式下的会话恢复
- `(user_ip, 1), (start_time, -1)`: 安全限制和旧会话兼容
- `(university_name, 1), (start_time, -1)`: 按大学查找会话
- `(session_id, 1)` 唯一索引: 会话 ID 查找
- `(start_time, -1)`: 按时间排序

### 5. `processing_tasks` - 后台处理任务

存储所有后台任务的状态和日志。

**关键字段**:
- `task_type`: 任务类型（`PDF_PROCESSING` / `OCR_IMPORT` / `TAG_UNIVERSITIES` / `REGENERATE_ANALYSIS` / `REFINE_AND_REGENERATE`）
- `status`: 任务状态（`pending` / `processing` / `completed` / `failed` / `interrupted`）
- `pid`: 执行进程 ID（用于中断检测）
- `processing_mode`: PDF 处理模式（`normal` / `batch`，仅 `PDF_PROCESSING` 类型）
- `current_step`: 当前执行步骤
- `progress`: 进度百分比
- `logs`: 日志数组，每条包含 `timestamp`、`level`、`message`

**索引策略**:
- `(created_at, -1)`: 任务列表按时间排序
- `(status, 1)`: 按状态筛选

### 6. `ip_geo_cache` - IP 地理位置缓存

缓存 IP 地址的地理位置查询结果，避免重复查询 MaxMind 数据库。

**关键字段**:
- `ip`: IP 地址
- `country_name`, `city_name`, `country_code`: 地理位置信息

**索引策略**:
- `(ip, 1)` 唯一索引: 快速查找
- `(country_code, 1)`: 按国家筛选

## PDF 存储 (GridFS)

所有上传的 PDF 文件使用 GridFS 存储，解决 MongoDB 16MB 文档大小限制。

**`fs.files` 元数据结构**:
```json
{
  "_id": "<ObjectId>",
  "filename": "String",
  "metadata": {
    "university_name": "String",
    "deadline": "String",
    "upload_time": "DateTime",
    "original_filename": "String"
  }
}
```
