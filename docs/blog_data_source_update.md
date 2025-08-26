# 博客数据源迁移至 MongoDB

本文档阐述了将博客数据处理机制从基于文件的系统重构为基于 MongoDB 的系统的过程。

## 1. 变更摘要

获取、显示和管理博客文章的核心逻辑已迁移为使用 MongoDB 作为唯一数据源。此变更消除了博客内容对本地文件系统（`/blogs` 目录）的依赖。

## 2. 迁移原因

- **可扩展性**: 对于日益增多的博客文章，数据库比一组平面文件更适合管理。
- **数据集中化**: 将所有应用数据（大学信息、博客）整合到单个数据库中，简化了数据管理和备份。
- **性能**: MongoDB 的查询，尤其是在有适当索引的情况下，在过滤和排序方面比文件系统操作性能更高。
- **逻辑简化**: 移除了与文件监控、缓存和哈希计算相关的复杂且可能脆弱的代码。

## 3. 代码层面变更

### 文件: `routes/blog.py`

此文件经过了彻底重构。

- **已移除**:
    - `BlogCache` 类：该类负责文件监控和内存缓存，已被完全移除。
    - 所有直接与文件系统交互的函数，如 `get_blog_by_id`, `find_blog_by_title`, `_calculate_files_hash` 等均已删除。
    - `lru_cache` 装饰器：由于数据库现在是数据源，因此不再需要此装饰器。

- **新增/重写**:
    - `get_all_blogs()`: 现在查询 MongoDB 中的 `blogs` 集合以获取所有博客文章的列表（id, title, date）。它按 `publication_date` 降序对结果进行排序。
    - `get_blog_by_url_title(url_title)`: 使用 `url_title` 从 MongoDB 中获取单篇完整的博客文章。它还负责将 Markdown 内容转换为 HTML。
    - `get_random_blogs_with_summary(count)`: 使用 MongoDB 聚合管道 (`$sample`) 来高效检索指定数量的随机博客文章，用于在首页等页面上显示。

- **路由**:
    - `blog_list_route()`: 逻辑被简化。现在默认获取并显示最新的博客文章。
    - `blog_detail_route(url_title)`: 现在完全使用 `get_blog_by_url_title` 来获取数据。基于文件的备用逻辑已被移除。

### 文件: `routes/index.py`

- 此文件无需任何代码更改。现有的对 `get_all_blogs()` 和 `get_random_blogs_with_summary()` 的调用现在无缝地使用了重构后的 `routes/blog.py` 中由 MongoDB 支持的新函数。

## 4. 日志记录

- 在新的 MongoDB 函数（`get_all_blogs`, `get_blog_by_url_title` 等）中添加了 `logging.info` 和 `logging.debug` 语句。
- 这些日志将清楚地表明数据何时从 MongoDB 获取以及找到了多少条记录，这将有助于手动测试和调试。例如：
  ```
  INFO:root:从MongoDB加载所有博客列表...
  INFO:root:成功从MongoDB加载了 X 篇博客。
  INFO:root:从MongoDB获取博客: [some-url-title]
  ```

## 5. 如何测试

1.  确保您的 MongoDB 实例正在运行，并且 `RunJPLib` 数据库中包含一个带有有效文档的 `blogs` 集合。
2.  运行 Flask 应用。
3.  访问 `/blog` 端点。它应该显示数据库中最新的博客文章。
4.  点击侧边栏中不同的博客标题。每个标题都应能正确地从数据库加载内容。
5.  访问主页 (`/`)。页面底部应显示几篇随机的博客摘要。
6.  检查应用日志，确认其中包含从 MongoDB 获取数据的消息。
7.  确认功能正常后，可以安全地删除本地的 `/blogs` 目录。