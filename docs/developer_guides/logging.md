# 日志系统指南

本项目使用 Python 内置的 `logging` 模块来统一记录应用日志。合理的日志配置对于开发、调试和生产环境的监控至关重要。

## 日志文件结构

所有日志文件都存储在 `log/` 目录下，并按日期和类型自动分割。

```
log/
├── app_YYYYMMDD.log           # 主应用日志
├── error_YYYYMMDD.log         # 错误日志
├── retrieval_YYYYMMDD.log     # AI 对话检索专项日志
└── BlogGenerator_YYYYMMDD.log # AI 博客生成器专项日志
```

## 核心日志记录器

### 1. 主应用日志
- **配置**: 在 `app.py` 的 `setup_logging()` 函数中配置。
- **内容**: 记录应用启动、请求处理、数据库操作等一般信息和错误。
- **环境变量 `LOG_LEVEL`**: 控制主应用日志的级别，默认为 `INFO`。可选值：`DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`。

### 2. AI 对话检索日志
- **文件**: `retrieval_YYYYMMDD.log`
- **配置**: `utils/logging_config.py` 中的 `setup_retrieval_logger()`。
- **内容**: 专门记录 AI 对话系统中与 LlamaIndex 检索和混合搜索策略相关的所有详细信息，是分析和优化搜索效果的关键。

### 3. `pymongo` 日志
- **控制**: `pymongo` 库会产生大量自己的日志，为了避免对主日志造成干扰，系统默认将其日志级别上调为 `INFO`。
- **环境变量 `PYMONGO_LOG_LEVEL`**: 在需要调试数据库连接问题时，可以通过此环境变量将 `pymongo` 的日志级别降至 `DEBUG`。

## 如何在开发中使用日志

### 查看实时日志

```bash
# 实时查看主应用日志
tail -f log/app_$(date +%Y%m%d).log

# 实时查看 AI 检索日志
tail -f log/retrieval_$(date +%Y%m%d).log
```

### 调试特定问题

当需要排查问题时，可以在启动应用前设置环境变量来获取更详细的日志输出。

```bash
# 在 .env 文件或启动脚本中设置
LOG_LEVEL=DEBUG
PYMONGO_LOG_LEVEL=DEBUG
```

这将使应用和 `pymongo` 都输出最详细的调试信息，帮助定位问题。
