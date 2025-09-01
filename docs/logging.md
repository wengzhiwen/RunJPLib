# 日志配置说明

本项目使用 Python logging 统一输出应用与三方库日志。本文档说明如何通过环境变量控制日志级别，特别是检索日志系统和 pymongo 日志的开关与粒度。

## 全局日志级别
- 环境变量：LOG_LEVEL
- 作用：控制应用根日志器以及控制台/文件处理器的级别
- 默认值：INFO
- 可选值：DEBUG, INFO, WARNING, ERROR, CRITICAL

## 检索日志系统

### 专用检索日志
- 日志文件：`log/retrieval.log`
- 作用：专门记录 LlamaIndex 检索操作和混合搜索策略的详细信息
- 内容：会话ID、用户查询、搜索结果、搜索策略、性能指标

### 检索日志配置
```python
# utils/logging_config.py
def setup_retrieval_logger() -> logging.Logger:
    """设置专门用于记录检索操作的日志记录器"""
    logger_name = "retrieval"
    log_file_path = os.path.join("log", "retrieval.log")
    
    retrieval_logger = logging.getLogger(logger_name)
    retrieval_logger.setLevel(logging.INFO)
    
    # 关键修复：清除已存在的handlers，确保文件handler总是被正确添加
    if retrieval_logger.hasHandlers():
        retrieval_logger.handlers.clear()
    
    formatter = logging.Formatter("%(asctime)s - %(message)s")
    file_handler = logging.FileHandler(log_file_path, mode='a', encoding='utf-8')
    file_handler.setFormatter(formatter)
    
    retrieval_logger.addHandler(file_handler)
    retrieval_logger.propagate = False
    
    return retrieval_logger
```

### 检索日志内容示例
```
2025-01-26 12:00:01 - 会话ID: session_123, 用户查询: "有计算机系吗？"
2025-01-26 12:00:01 - 查询扩展结果: {"exact_keywords": ["情報工学"], "search_strategy": "hybrid"}
2025-01-26 12:00:01 - 混合搜索耗时: 0.415秒, 内存: 45.2% → 46.1%
2025-01-26 12:00:01 - 搜索结果: 5个精确匹配, 3个向量匹配
```

## pymongo 日志级别
- 环境变量：PYMONGO_LOG_LEVEL
- 作用：单独控制 pymongo 日志器（logging.getLogger('pymongo')）的级别
- 默认值：INFO
- 典型设置：
  - 常规运行：不设置或设置为 INFO
  - 排障阶段：设置为 DEBUG

## 环境变量配置示例

```bash
# .env 或部署环境变量
LOG_LEVEL=INFO
PYMONGO_LOG_LEVEL=DEBUG

# 混合搜索相关日志
HYBRID_SEARCH_ENABLED=true
MEMORY_CLEANUP_THRESHOLD=80
```

## 日志文件结构

```
log/
├── retrieval.log          # 检索操作专用日志
├── app_20250126.log       # 应用日志（按日期）
└── error_20250126.log     # 错误日志（按日期）
```

## 日志监控和分析

### 检索性能监控
```bash
# 查看混合搜索性能
grep "混合搜索耗时" log/retrieval.log | tail -10

# 查看内存使用情况
grep "内存:" log/retrieval.log | tail -10

# 查看搜索策略分布
grep "search_strategy" log/retrieval.log | sort | uniq -c
```

### 错误追踪
```bash
# 查看搜索错误
grep "ERROR" log/retrieval.log

# 查看内存清理操作
grep "内存清理" log/retrieval.log
```

## 生效位置
- 代码位置：`app.py` 中的 `setup_logging()`
- 检索日志：`utils/logging_config.py` 中的 `setup_retrieval_logger()`
- 行为：
  - 根日志器启用文件与控制台处理器
  - 检索日志器专门记录检索操作
  - pymongo 日志级别默认设为 INFO，可被 PYMONGO_LOG_LEVEL 覆盖

## 运维建议

### 生产环境
- 保持 `PYMONGO_LOG_LEVEL=INFO` 或更高，避免大量调试日志
- 定期清理 `retrieval.log` 文件，避免文件过大
- 监控内存使用日志，及时发现问题

### 排障阶段
- 临时提升到 DEBUG，并设置合理的日志轮转与保留策略
- 使用检索日志分析搜索性能问题
- 建议结合外部日志系统（如 ELK/Loki）通过 logger 名称进行筛选与分流

### 性能优化
- 定期分析检索日志，优化搜索策略
- 监控内存使用趋势，调整清理阈值
- 根据搜索模式调整缓存策略

## 变更历史
- **2025-01-26**：新增检索日志系统，支持混合搜索策略监控
- **2025-09-01**：修复检索日志初始化问题，确保日志正确生成
- **2025-08-29**：新增 PYMONGO_LOG_LEVEL，默认将 pymongo 日志上调为 INFO

---

*文档版本：v2.0*
*最后更新：2025-01-26*

