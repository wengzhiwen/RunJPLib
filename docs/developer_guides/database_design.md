# 数据库设计 (MongoDB)

本文档详细描述了 RunJPLib 项目中使用的 MongoDB 集合的结构和索引策略。

## 核心集合

### 1. `universities` - 招生信息
- **描述**: 存储大学招生信息的核心数据。

**文档结构**:
```json
{
  "_id": "<ObjectID>",
  "university_name": "String", // 大学日文名
  "university_name_zh": "String", // 大学简体中文名
  "deadline": "Date", // 报名截止日期 (BSON Date Type)
  "created_at": "DateTime", // 文档创建时间
  "is_premium": "Boolean", // 是否为 Premium，用于优先排序
  "tags": ["String"], // 大学标签数组，如 ["国立", "難関", "理系"]
  "content": {
    "original_md": "String", // OCR 识别的日文原文
    "translated_md": "String", // 翻译后的中文内容
    "report_md": "String", // AI 生成的分析报告
    "pdf_file_id": "ObjectId" // 指向 GridFS 中 PDF 文件的 ObjectId
  }
}
```

**索引策略**:
- `university_name`: 加速按日文名查找。
- `university_name_zh`: 加速按中文名查找。
- `deadline`: 加速按截止日期排序和筛选。
- `tags`: 加速按标签筛选查询。
- `("university_name", 1), ("deadline", -1)`: 复合索引，用于高效查询特定大学的最新招生信息。
- `("university_name_zh", 1), ("deadline", -1)`: 复合索引，用于中文名回退查询。
- `("is_premium", -1), ("deadline", -1)`: 复合索引，用于Premium优先排序。
- `("tags", 1)`: 单字段索引，用于标签筛选查询。
- `("tags", 1), ("is_premium", -1), ("deadline", -1)`: 复合索引，用于标签筛选 + Premium优先 + 截止日期排序。
- `("tags", 1), ("deadline", -1)`: 复合索引，用于标签筛选 + 截止日期排序。

### 2. `blogs` - 博客文章
- **描述**: 存储博客文章。

**文档结构**:
```json
{
  "_id": "<ObjectID>",
  "title": "String",
  "url_title": "String", // URL 友好的标题
  "publication_date": "String", // 发布日期 (YYYY-MM-DD)
  "created_at": "DateTime",
  "md_last_updated": "DateTime", // Markdown 原文最后更新时间
  "html_last_updated": "DateTime", // HTML 缓存最后生成时间
  "content_md": "String", // Markdown 原文
  "content_html": "String", // 缓存的 HTML 内容
  "is_public": "Boolean", // 是否对公众可见。默认为 true，AI 生成的为 false
  "generation_details": { // (可选) 如果由 AI 生成，则包含此对象
    "mode": "String", // 生成模式 (expand, compare, etc.)
    "university_ids": ["ObjectID", ...],
    "user_prompt": "String",
    "system_prompt": "String",
    "generated_at": "DateTime"
  }
}
```

**索引策略**:
- `url_title` (唯一): 高效地通过 URL 查找文章。
- `publication_date` (降序): 用于按发布日期快速排序，获取最新文章。
- `is_public`: 用于在前端查询中快速筛选出公开的文章。

### 3. `access_logs` - 访问日志
- **描述**: 记录对大学信息页和博客页的公开访问。

**索引策略**:
- `(timestamp, page_type)`: 复合索引，用于高效地完成仪表盘的聚合统计查询。

### 4. `chat_logs` - AI 对话日志
- **描述**: 存储用户与 AI 的对话历史。

**索引策略**:
- `(browser_session_id, university_id, last_activity)`: 核心复合索引，用于在隐私保护模式下快速恢复用户会话。
- `(user_ip, start_time)`: 用于安全限制和兼容旧会话的查询。

### 5. `processing_tasks` - PDF 处理任务
- **描述**: 存储招生信息处理器中每个 PDF 处理任务的状态和元数据。

**索引策略**:
- `created_at` (降序): 用于在任务列表页面快速显示最新任务。
- `status`: 用于快速筛选特定状态（如 `processing`, `failed`）的任务。

## PDF 存储 (GridFS)

为了解决 MongoDB 16MB 的文档大小限制，所有上传的 PDF 文件都使用 GridFS 进行存储。`universities` 集合中的文档只包含一个指向 `fs.files` 集合的 `ObjectId` 引用。

**`fs.files` 元数据结构**:
```json
{
  "_id": "<ObjectId>",
  "filename": "String", // 内部存储的 UUID 文件名
  "metadata": {
    "university_name": "String",
    "deadline": "String",
    "upload_time": "DateTime",
    "original_filename": "String" // 用户上传时的原始文件名
  }
}
```
