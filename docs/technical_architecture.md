# 技术架构

本文档描述了 RunJPLib 项目的技术架构，包括模块组织、数据库设计、任务处理、缓存策略和后台并发等核心设计。

## Utils 模块架构

Utils 模块按功能领域组织，每个子包通过 `__init__.py` 提供向后兼容的别名导出，确保原有 `from utils.xxx import Yyy` 的导入方式继续有效。

### 模块组织结构

- **`core/`**: 核心基础设施
  - `config.py`: 配置管理（单例模式）
  - `database.py`: 数据库连接、连接池和索引管理
  - `logging.py`: 日志配置（通用 logger、任务 logger、检索 logger）
  - `proof.py`: 校对归档工具（将 A/B/C 三份 Markdown 保存到 `proof/` 目录）

- **`ai/`**: AI 相关工具
  - `analysis_tool.py`: 文档分析器 (`DocumentAnalyzer`)，三步分析流程 + 再生成支持
  - `blog_generator.py`: 内容生成器 (`ContentGenerator`)，三种模式 + Formatter Agent
  - `ocr_tool.py`: 图像 OCR 处理器 (`ImageOcrProcessor`)
  - `batch_ocr_tool.py`: 批量 OCR 处理器 (`BatchOcrProcessor`)，基于 OpenAI Batch API
  - `translate_tool.py`: 文档翻译器 (`DocumentTranslator`)

- **`chat/`**: 聊天相关功能
  - `manager.py`: 聊天管理器 (`ChatManager`)，会话管理 + 同义词扩展 + 索引自动更新
  - `security.py`: 聊天安全守护者 (`ChatSecurityGuard`)，速率限制与权限控制
  - `logging.py`: 聊天会话日志记录器 (`ChatSessionLogger`)
  - `search_strategy.py`: 混合搜索引擎 (`HybridSearchEngine`)，向量 + 关键词并行搜索 + 内存优化

- **`document/`**: 文档处理
  - `pdf_processor.py`: PDF 处理器 (`PDFProcessor`)，基于 Buffalo Workflow 的五步流水线
  - `wiki_processor.py`: Wiki 处理器 (`BlogWikiProcessor`)，自动大学名称链接

- **`university/`**: 大学相关
  - `manager.py`: 大学文档仓库 (`UniversityRepository`)，CRUD + 搜索 + GridFS
  - `tagger.py`: 大学分类器 (`UniversityClassifier`)，LLM 驱动的批量标签生成
  - `search.py`: 向量搜索引擎 (`VectorSearchEngine`)，LlamaIndex + ChromaDB

- **`system/`**: 系统管理
  - `task_manager.py`: 通用任务管理器 (`TaskManager`)，多类型任务队列 + 并发调度
  - `thread_pool.py`: 并发任务执行器 (`ConcurrentTaskExecutor`)，三池隔离
  - `analytics.py`: 访问分析，异步日志记录

- **`tools/`**: 工具类
  - `cache.py`: 缓存工具（博客列表缓存）
  - `ip_geo.py`: 地理位置解析器 (`GeoLocationResolver`)，MaxMind GeoLite2 + MongoDB 缓存

## Routes 模块架构

路由模块采用 Flask Blueprint 架构，在 `routes/blueprints.py` 中集中定义三个 Blueprint：

| Blueprint | URL 前缀 | 用途 |
|-----------|----------|------|
| `admin_bp` | `/admin` | 后台管理（模板目录指向 `templates/admin`） |
| `blog_bp` | `/blog` | 博客展示 |
| `chat_bp` | `/api/chat` | AI 对话 API |

### admin 子模块（7 个文件）

| 文件 | 职责 |
|------|------|
| `auth.py` | 认证与权限管理（登录/登出、`@admin_required` 装饰器、JWT 验证） |
| `dashboard.py` | 仪表盘（统计数据、SSE 实时推送） |
| `universities.py` | 招生信息管理（CRUD、标签筛选、中文名编辑） |
| `blogs.py` | 博客管理（编辑、AI 异步生成、可见性控制） |
| `pdf_processor.py` | PDF 处理任务管理（上传、队列、重启、状态监控） |
| `chat_logs.py` | 聊天会话履历（会话列表、详情、统计） |
| `analytics.py` | 分析工具（大学标签工具、IP 地理位置、TOP30 访问） |

### blog 子模块

| 文件 | 职责 |
|------|------|
| `views.py` | 博客列表与详情展示、推荐算法、延迟 HTML 渲染 |
| `cache.py` | 推荐博客缓存、博客 HTML 数据库更新 |

### university_chat 子模块

| 文件 | 职责 |
|------|------|
| `chat_api.py` | 对话 API 核心（创建会话、发送消息、获取历史、清除/删除会话） |
| `security.py` | 安全辅助（健康检查端点） |

## 数据库设计 (MongoDB)

### 核心集合

- **`universities`**: 存储大学的招生信息。
    - `university_name`: 大学日文名
    - `university_name_zh`: 大学中文名
    - `deadline`: 报名截止日期 (BSON Date 类型)
    - `is_premium`: 布尔值，用于优先排序
    - `tags`: 大学标签数组
    - `content.pdf_file_id`: 指向 GridFS 中存储的 PDF 文件的 ObjectId。
    - `content.original_md`: OCR 识别的日文原文
    - `content.translated_md`: 翻译后的中文内容
    - `content.report_md`: AI 生成的分析报告

- **`blogs`**: 存储博客文章。
    - `url_title`: URL 友好的标题 (唯一索引)
    - `publication_date`: 发布日期
    - `content_md` / `content_html`: Markdown 原文与缓存的 HTML
    - `is_public`: 是否对公众可见（AI 生成的默认为 false）
    - `generation_details`: AI 生成参数（模式、大学 ID、提示词等）

- **`access_logs`**: 记录页面访问日志。
- **`chat_sessions` (即 chat_logs)**: 记录 AI 对话会话与消息。
    - `browser_session_id`: 浏览器会话 ID（隐私保护模式）
    - `session_id`: 会话唯一 ID (唯一索引)
- **`ip_geo_cache`**: 缓存 IP 地址的地理位置信息。
- **`processing_tasks`**: 存储后台任务的状态、类型、PID 和日志。

详细的字段和索引设计参见 [数据库设计文档](developer_guides/database_design.md)。

### PDF 存储 (GridFS)

所有上传的 PDF 文件使用 GridFS 存储，`universities` 集合只包含 `ObjectId` 引用。

### 数据生命周期管理
- **创建与更新**: 上传新招生信息时，自动创建向量索引并替换旧索引。可选附带参考 Markdown 进行校对补强，Proof 归档保存到 `proof/` 目录。
- **删除**: 同时删除 MongoDB 文档和 ChromaDB 中的向量索引。

## 任务管理器

`TaskManager` 是一个通用后台任务管理器，支持多种任务类型的异步处理。

### 支持的任务类型

| 任务类型 | 说明 |
|----------|------|
| `PDF_PROCESSING` | 完整的 PDF 处理流水线（五步流程） |
| `OCR_IMPORT` | 本地 OCR 结果导入，从翻译步骤开始 |
| `TAG_UNIVERSITIES` | LLM 驱动的大学标签批量生成 |
| `REGENERATE_ANALYSIS` | 使用自定义系统提示词重新生成分析报告 |
| `REFINE_AND_REGENERATE` | 校对补强 + 再生成的组合流程 |

### 并发调度

- **可配置并发数**: 通过 `PDF_MAX_CONCURRENT_TASKS` 环境变量控制（默认 1，即顺序执行）。
- **等待通知机制**: 当任务进入长时间等待（如轮询批量 OCR 状态）时，工作线程调用 `notify_task_is_waiting()` 触发立即队列检查，尝试启动新任务，充分利用并发槽位。
- **PID 监控**: 任务启动时记录进程 ID (`pid` 字段)。后台 API 检查 PID 是否仍存活，自动将"僵尸"任务标记为 `interrupted` 状态，管理员可从任意步骤重启。

### 任务日志

- **数据库日志**: 每个任务在 `processing_tasks` 集合中维护独立的 `logs` 数组。
- **文件日志**: `TaskManager` 和 `PDFProcessor` 共享独立的按日分割日志文件 `log/TaskManager_YYYYMMDD.log`。

## 线程池架构

系统设计了三个独立的线程池，实现资源隔离：

| 线程池 | 默认大小 | 用途 | 环境变量 |
|--------|----------|------|----------|
| 用户访问日志线程池 | 6 | 高频、轻量级的访问日志记录 | `ANALYTICS_THREAD_POOL_SIZE` |
| 博客 HTML 构建线程池 | 8 | Markdown 到 HTML 的转换（延迟渲染） | `BLOG_UPDATE_THREAD_POOL_SIZE` |
| Admin 操作线程池 | 4 | 低频但可能耗时的后台管理操作 | `ADMIN_THREAD_POOL_SIZE` |

**关键特性**:
- **资源隔离**: 每个线程池独立工作，避免任务间的资源竞争。
- **智能降级**: 当线程池满载时，任务自动切换到同步执行模式，确保操作不会丢失。
- **实时监控**: 管理后台仪表盘可实时监控每个线程池的活跃线程数、队列大小和任务统计。

## 缓存策略

### 应用级缓存（TTLCache）

| 缓存 | TTL | 用途 |
|------|-----|------|
| `recommended_blogs_cache` | 30 分钟 | 推荐博客列表，博客创建/更新时自动清除 |
| `blog_list_cache` | 5 分钟 | 博客全量列表 |
| `university_list_cache` | 10 分钟 | 首页大学列表 |
| `latest_updates_cache` | 10 分钟 | 首页最新更新列表 |

### 博客 HTML 缓存（数据库）

博客的 HTML 内容在首次生成后缓存到 `blogs.content_html` 字段。后续请求直接使用缓存 HTML，仅在 Markdown 原文更新后触发"延迟渲染"(Lazy Rebuild)——通过博客 HTML 构建线程池异步重新生成。

### 数据库查询缓存

使用 MongoDB 连接池（`maxPoolSize=10`, `minPoolSize=1`）和全局单例客户端，`ismaster` 命令进行轻量级健康检查。

## 安全架构

- **认证**: JWT + HttpOnly Cookie + 访问码。`@admin_required` 装饰器区分页面请求（重定向登录页）和 API 请求（返回 JSON 错误）。
- **CSRF 保护**: 所有 Admin POST 请求（表单和 API）均需携带 CSRF Token（Header: `X-CSRF-TOKEN`）。
- **对话隐私**: 基于 `sessionStorage` 的浏览器会话 ID 隔离对话，同一网络不同用户不可见彼此记录。
- **速率限制**: 聊天系统内置请求频率限制，支持 IP 级别的降级策略。
