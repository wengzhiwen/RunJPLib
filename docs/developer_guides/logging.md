# 日志系统指南

本项目使用 Python 内置的 `logging` 模块统一记录应用日志，按功能域分为多个日志文件。

## 日志文件结构

所有日志文件存储在 `log/` 目录下，按日期自动分割。

```
log/
├── app_YYYYMMDD.log              # 主应用日志
├── error_YYYYMMDD.log            # 错误日志
├── retrieval_YYYYMMDD.log        # AI 对话检索专项日志
├── TaskManager_YYYYMMDD.log      # 任务管理器与 PDF 处理器日志
└── BlogGenerator_YYYYMMDD.log    # AI 博客生成器专项日志
```

## 核心日志记录器

### 1. 主应用日志
- **配置**: `app.py` 的 `setup_logging()` 函数。
- **内容**: 记录应用启动、请求处理、数据库操作等一般信息和错误。
- **环境变量 `LOG_LEVEL`**: 控制日志级别，默认 `INFO`。

### 2. AI 对话检索日志
- **文件**: `retrieval_YYYYMMDD.log`
- **配置**: `utils/core/logging.py` 中的 `setup_retrieval_logger()`。
- **内容**: 记录向量检索和混合搜索的详细信息，包括会话 ID、原始查询、扩展查询、搜索结果和 AI 回答。

### 3. 任务管理器日志
- **文件**: `TaskManager_YYYYMMDD.log`
- **配置**: `utils/core/logging.py` 中的 `setup_task_logger()`。
- **内容**: 记录任务创建、入队、出队、启动、等待、完成以及并发槽位状态等详细信息。

### 4. 博客生成器日志
- **文件**: `BlogGenerator_YYYYMMDD.log`
- **配置**: `utils/ai/blog_generator.py` 中的 `setup_logger()`。
- **内容**: 记录 AI 博客生成的详细过程，包括模式选择、材料准备、Agent 调用和错误处理。

### 5. pymongo 日志
- **默认级别**: `INFO`（减少调试信息干扰）。
- **环境变量 `PYMONGO_LOG_LEVEL`**: 需要调试数据库连接时可设为 `DEBUG`。

## 如何使用日志

### 查看实时日志

```bash
# 实时查看主应用日志
tail -f log/app_$(date +%Y%m%d).log

# 实时查看检索日志
tail -f log/retrieval_$(date +%Y%m%d).log

# 实时查看任务管理日志
tail -f log/TaskManager_$(date +%Y%m%d).log
```

### 调试模式

```bash
# 在 .env 文件中设置
LOG_LEVEL=DEBUG
PYMONGO_LOG_LEVEL=DEBUG
```
