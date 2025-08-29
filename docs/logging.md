日志配置说明

本项目使用 Python logging 统一输出应用与三方库日志。本文档说明如何通过环境变量控制日志级别，特别是 pymongo 日志的开关与粒度。

全局日志级别
- 环境变量：LOG_LEVEL
- 作用：控制应用根日志器以及控制台/文件处理器的级别
- 默认值：INFO
- 可选值：DEBUG, INFO, WARNING, ERROR, CRITICAL

pymongo 日志级别
- 环境变量：PYMONGO_LOG_LEVEL
- 作用：单独控制 pymongo 日志器（logging.getLogger('pymongo')）的级别
- 默认值：INFO
- 典型设置：
  - 常规运行：不设置或设置为 INFO
  - 排障阶段：设置为 DEBUG

示例（.env 或部署环境变量）：
```
LOG_LEVEL=INFO
PYMONGO_LOG_LEVEL=DEBUG
```

生效位置
- 代码位置：app.py 中的 setup_logging()
- 行为：
  - 根日志器启用文件与控制台处理器
  - pymongo 日志级别默认设为 INFO，可被 PYMONGO_LOG_LEVEL 覆盖

运维建议
- 生产环境保持 PYMONGO_LOG_LEVEL=INFO 或更高，避免大量调试日志
- 排障时临时提升到 DEBUG，并设置合理的日志轮转与保留策略
- 建议结合外部日志系统（如 ELK/Loki）通过 logger 名称进行筛选与分流

变更历史
- 2025-08-29：新增 PYMONGO_LOG_LEVEL，默认将 pymongo 日志上调为 INFO

