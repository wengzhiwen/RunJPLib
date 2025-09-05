# 技术架构

本文档描述了 RunJPLib 项目的技术架构，包括数据库设计、性能优化策略和后台任务处理。

## Utils 模块架构

### 模块组织结构
Utils 模块按功能领域进行了重新组织，提高了代码的可维护性和可读性：

- **`core/`**: 核心基础设施
  - `config.py`: 配置管理（单例模式）
  - `database.py`: 数据库连接和索引管理
  - `logging.py`: 日志配置和管理

- **`ai/`**: AI相关工具
  - `analysis_tool.py`: 文档分析器 (`DocumentAnalyzer`)
  - `blog_generator.py`: 内容生成器 (`ContentGenerator`)
  - `ocr_tool.py`: 图像OCR处理器 (`ImageOcrProcessor`)
  - `batch_ocr_tool.py`: 批量OCR处理器 (`BatchOcrProcessor`)
  - `translate_tool.py`: 文档翻译器 (`DocumentTranslator`)

- **`chat/`**: 聊天相关功能
  - `manager.py`: 聊天管理器 (`ChatManager`)
  - `security.py`: 聊天安全守护者 (`ChatSecurityGuard`)
  - `logging.py`: 聊天会话日志记录器 (`ChatSessionLogger`)
  - `search_strategy.py`: 混合搜索引擎 (`HybridSearchEngine`)

- **`document/`**: 文档处理
  - `pdf_processor.py`: PDF处理器 (`PDFProcessor`)
  - `wiki_processor.py`: Wiki处理器 (`BlogWikiProcessor`)

- **`university/`**: 大学相关
  - `manager.py`: 大学文档仓库 (`UniversityRepository`)
  - `tagger.py`: 大学分类器 (`UniversityClassifier`)
  - `search.py`: 向量搜索引擎 (`VectorSearchEngine`)

- **`system/`**: 系统管理
  - `task_manager.py`: 任务管理器 (`TaskManager`)
  - `thread_pool.py`: 并发任务执行器 (`ConcurrentTaskExecutor`)
  - `analytics.py`: 访问分析

- **`tools/`**: 工具类
  - `cache.py`: 缓存工具
  - `ip_geo.py`: 地理位置解析器 (`GeoLocationResolver`)

- **`templates/`**: 模板文件
  - `workflow_template.yml`: 工作流模板

### 向后兼容性
所有原有导入方式继续有效，通过别名机制确保现有代码无需修改。

## 数据库设计 (MongoDB)

### 1. 核心集合
- **`universities`**: 存储大学的招生信息。
    - `university_name`: 大学日文名 (索引)
    - `university_name_zh`: 大学中文名 (索引)
    - `deadline`: 报名截止日期 (BSON 日期类型, 索引)
    - `is_premium`: 布尔值，用于优先排序
    - `content.pdf_file_id`: 指向 GridFS 中存储的 PDF 文件的 ObjectId。
- **`blogs`**: 存储博客文章。
    - `url_title`: URL 友好的标题 (唯一索引)
    - `publication_date`: 发布日期 (索引)
    - `content_md`: Markdown 原文
    - `content_html`: 缓存的 HTML 内容
- **`access_logs`**: 记录页面访问日志，用于仪表盘统计。
- **`chat_logs`**: 记录 AI 对话历史。
- **`ip_geo_cache`**: 缓存 IP 地址的地理位置信息。
- **`processing_tasks`**: 存储 PDF 处理任务的状态和日志。

### 2. PDF 存储 (GridFS)
为了解决 MongoDB 16MB 的文档大小限制，所有上传的 PDF 文件都使用 GridFS 进行存储。`universities` 集合中的文档只包含一个指向 `fs.files` 集合的 `ObjectId` 引用，大大减小了主文档的大小，提高了查询性能。

### 3. 数据生命周期管理
- **创建与更新**: 当通过后台上传新的招生信息时，会为该大学文档创建一个新的向量索引，并替换掉旧的索引（如果存在）。
- **删除**: 当从后台删除一个大学信息时，系统会同时删除 MongoDB 中的文档和 ChromaDB 中对应的向量索引，确保数据和索引的同步，避免产生孤立的索引。

**GridFS 文件元数据:**
```json
{
  "_id": "<ObjectId>",
  "filename": "String", // e.g., "550e8400-e29b-41d4-a716-446655440000" (纯UUID)
  "metadata": {
    "university_name": "String",
    "deadline": "String",
    "upload_time": "DateTime",
    "original_filename": "String", // 原始文件名，用于显示给用户
    "migrated_at": "DateTime" // 迁移时间（如果是迁移的数据）
  }
}
```

### 3. 数据库性能优化
- **连接池**: 应用使用 `pymongo` 的连接池来高效管理数据库连接，避免了为每个请求创建新连接的开销。通过环境变量可配置连接池参数（如 `maxPoolSize`, `minPoolSize`）。

**连接池参数:**
```python
# Connection pool parameters
maxPoolSize=10          # Maximum number of connections in the pool
minPoolSize=1           # Minimum number of connections to maintain
maxIdleTimeMS=300000    # Maximum time a connection can remain idle (5 minutes)
waitQueueTimeoutMS=10000 # Maximum time to wait for a a connection (10 seconds)
```

- **单例模式**: 全局共享一个 MongoDB 客户端实例，并使用线程锁确保线程安全。
- **健康检查**: 使用轻量级的 `ismaster` 命令进行连接健康检查，替代了开销较大的 `ping` 命令。
- **索引**: 为常用查询字段（如 `university_name`, `deadline`, `url_title`）创建了索引，以加速查询。

## 线程池架构

为了高效处理不同类型的后台任务并避免相互干扰，系统设计了三个独立的线程池。

- **用户访问日志线程池** (默认6线程): 处理高频率、轻量级的访问日志记录任务。
- **博客 HTML 构建线程池** (默认8线程): 处理中等频率、有一定计算量的 Markdown 到 HTML 的转换任务。
- **Admin 操作线程池** (默认4线程): 处理低频率、但可能耗时较长的后台管理操作（如数据导入、更新）。

**关键特性**:
- **资源隔离**: 每个线程池独立工作，避免了任务之间的资源竞争。
- **智能降级**: 当线程池满载时，任务会自动切换到同步执行模式，确保操作不会丢失。
- **实时监控**: 管理后台的仪表盘可以实时监控每个线程池的活跃线程数、队列大小和任务统计，便于运维。
- **可配置性**: 可以通过环境变量（如 `BLOG_UPDATE_THREAD_POOL_SIZE`）调整每个线程池的大小。

## 缓存策略

- **数据库查询缓存**: 对不经常变动的数据库查询结果（如首页的大学列表、分类信息）使用 `cachetools.TTLCache` 进行内存缓存，减少数据库负载。
- **博客 HTML 缓存**: 博客的 HTML 内容在首次生成后会被缓存到 `blogs` 集合的 `content_html` 字段中。后续请求会直接使用缓存的 HTML，仅在 Markdown 原文更新后才会重新生成，这被称为“延迟渲染”(Lazy Rebuild) 策略。