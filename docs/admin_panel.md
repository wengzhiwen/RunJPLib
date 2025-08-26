# 管理面板文档

本文档提供了RunJPLib项目管理面板的概述。

## 访问管理面板

管理面板位于应用程序的 `/admin` URL（例如：`http://localhost:5000/admin`）。

访问受到保护。您必须提供 `ACCESS_CODE` 才能登录。此代码通过 `ACCESS_CODE` 环境变量配置。

登录成功后，JWT 会存储在浏览器的本地存储中，用于验证后续的 API 请求。

## 功能特性

管理面板是一个单页应用程序，包含以下几个部分：

### 1. 仪表板

欢迎页面。

### 2. 数据上传

此部分用于将数据从本地文件系统迁移到 MongoDB 数据库。

-   **大学数据**：
    -   从下拉列表中选择一个 `pdf_with_md*` 文件夹。
    -   点击"开始上传"开始处理。
    -   工具将遍历子目录，提取元数据，读取文件内容（markdown、文本和PDF），并将它们上传到 MongoDB 的 `universities` 集合中。
    -   操作使用 `upsert`，这意味着您可以重新运行同一文件夹的上传，以更新现有条目或添加新条目，而不会创建重复项。

-   **博客数据**：
    -   点击"开始上传"上传 `/blogs` 目录中的所有 markdown 文件。
    -   工具从文件名中提取元数据，并将内容上传到 `blogs` 集合。
    -   此操作也使用 `upsert`。

### 3. 数据管理

此部分允许直接管理 MongoDB 中的数据。

-   **大学数据和博客数据**：
    -   **刷新列表**：获取并显示相应集合中所有项目的列表。
    -   **清空所有数据**：删除集合中的所有文档。这是一个破坏性操作，需要确认。
    -   对于每个项目，您可以：
        -   **查看**：在新标签页中打开该项目的用户页面。
        -   **删除**：从数据库中删除特定项目。

### 4. 数据生成

此部分是未来内容生成功能的占位符。目前尚未实现。

## API 端点

管理面板使用 `/admin/api/` 下的一组 API 端点。所有端点都受到保护，需要有效的 JWT。

-   `POST /admin/api/login`：使用访问码进行身份验证并返回 JWT。
-   `GET /admin/api/university_folders`：列出可用的 `pdf_with_md*` 文件夹。
-   `POST /admin/api/upload/university`：开始指定文件夹的大学数据上传。
-   `POST /admin/api/upload/blogs`：开始博客数据上传。
-   `GET /admin/api/universities`：列出数据库中的大学。
-   `DELETE /admin/api/universities/<id>`：删除特定大学。
-   `DELETE /admin/api/universities`：清空大学集合。
-   `GET /admin/api/blogs`：列出数据库中的博客。
-   `DELETE /admin/api/blogs/<id>`：删除特定博客。
-   `DELETE /admin/api/blogs`：清空博客集合。

## 用户界面集成

以下用户界面已修改为从 MongoDB 加载数据（如果存在）：

-   `/university/<name>/<deadline>`
-   `/blog/<title>`

如果在 MongoDB 中找到请求的数据，将从那里提供服务。否则，应用程序将回退到原始的文件系统加载机制。这允许逐步迁移，并确保即使对于尚未上传到数据库的数据，网站仍然保持功能。

新增了路由 `/pdf/resource/<resource_id>` 来从 GridFS 提供 PDF 文件。为了向后兼容，旧版路由 `/pdf/mongo/<item_id>` 仍然支持但已弃用。

## PDF 存储策略

系统现在使用 **GridFS** 进行 PDF 存储，而不是直接在 MongoDB 文档中嵌入二进制数据。这种方法：

- **解决文档大小限制**：GridFS 可以处理大于 MongoDB 16MB 文档限制的文件
- **提高安全性**：使用基于 UUID 的文件名防止注入攻击
- **保持用户体验**：用户仍然看到有意义的文件名（例如："東京学芸大学_20241219.pdf"）
- **优化性能**：没有嵌入的二进制数据，文档加载更快

### GridFS 文件结构
- **内部文件名**：UUID 格式（例如："550e8400-e29b-41d4-a716-446655440000"）
- **用户显示文件名**：在元数据中存储为 `original_filename`
- **文件标识**：通过元数据（`university_name` 和 `deadline`）
