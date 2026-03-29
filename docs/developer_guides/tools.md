# 开发者工具指南

`tools/` 目录下提供了一系列命令行工具，用于帮助开发者进行数据迁移、功能测试和系统维护。

## 常用工具

### 1. 端口管理 (`kill_port.py`)
终止占用特定端口的进程。

```bash
python tools/kill_port.py 5000
```

### 2. 数据库索引管理
索引定义位于 `utils/core/database.py` 的 `ensure_indexes()` 函数。

```bash
# 创建所有索引
python -c "from utils.core.database import ensure_indexes; ensure_indexes()"

# 检查索引状态
python -c "from utils.core.database import check_indexes; check_indexes()"
```

### 3. AI 对话索引状态检查 (`check_index_status.py`)
调试工具，检查特定大学在 MongoDB 中的数据时间戳是否与 LlamaIndex/ChromaDB 向量索引一致。当 AI 回答内容不是最新时，可用此工具定位问题。

## 数据迁移与处理工具

这些工具通常是一次性的，用于处理特定的数据迁移或修复任务。

- **`migrate_deadline_to_date.py`**: 将 `universities` 集合中旧的字符串格式 `deadline` 字段迁移为 BSON 日期类型。
- **`translate_university_names.py`**: 使用 AI 批量将大学的日文名称翻译为简体中文，存入 `university_name_zh` 字段。
- **`fix_markdown_tables.py`**: 修复 Markdown 内容中格式不正确的表格。

## 测试与验证工具

- **`performance_test.py`**: 对应用特定端点进行性能测试。
