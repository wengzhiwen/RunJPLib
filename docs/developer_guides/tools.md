# 开发者工具指南

`tools/` 目录下提供了一系列命令行工具，用于帮助开发者进行数据迁移、功能测试和系统维护。

## 常用工具

### 1. 端口管理 (`kill_port.py`)
一个用于终止占用特定端口进程的实用脚本。

- **用途**: 在本地开发时，如果因为异常退出导致应用端口（如 5000）未被释放，可以使用此工具快速清理。
- **使用方法**:
  ```bash
  # 终止占用 5000 端口的进程
  python kill_port.py 5000
  ```

### 2. 数据库索引管理
正确的数据库索引对于应用性能至关重要。

- **创建所有索引**: 在初次部署或索引定义更新后，运行此命令来确保所有必要的索引都已在 MongoDB 中创建。
  ```bash
  python -c "from utils.db_indexes import create_indexes; create_indexes()"
  ```
- **检查索引状态**: 验证当前数据库中的索引是否与代码定义一致。
  ```bash
  python -c "from utils.db_indexes import check_indexes; check_indexes()"
  ```

### 3. AI 对话索引状态检查 (`check_index_status.py`)
- **用途**: 这是一个调试工具，用于检查特定大学在 MongoDB 中的最新数据时间戳，是否与 LlamaIndex/ChromaDB 中向量索引的时间戳一致。当遇到 AI 回答内容不是最新的情况时，可以用此工具来定位问题。

## 数据迁移与处理工具

这些工具通常是一次性的，用于处理特定的数据迁移或修复任务。

- **`migrate_deadline_to_date.py`**: 将 `universities` 集合中旧的字符串格式的 `deadline` 字段，迁移为标准的 BSON 日期类型。
- **`translate_university_names.py`**: 使用 AI 批量将大学的日文名称翻译为简体中文，并存入 `university_name_zh` 字段。
- **`fix_markdown_tables.py`**: 用于修复 Markdown 内容中格式不正确的表格。

## 测试与验证工具

- **`performance_test.py`**: 用于对应用的特定端点进行性能测试。
- **`test_recommendation_algorithm.py`**: (已移除，功能合并到其他测试中) 用于测试博客推荐算法的逻辑。
