# MongoDB Schema Design

This document outlines the design of the MongoDB collections for the RunJPLib project.

## Connection Management & Performance Optimization

### Connection Pool Configuration
The application uses a connection pool to efficiently manage MongoDB connections and prevent resource exhaustion:

```python
# Connection pool parameters
maxPoolSize=10          # Maximum number of connections in the pool
minPoolSize=1           # Minimum number of connections to maintain
maxIdleTimeMS=300000    # Maximum time a connection can remain idle (5 minutes)
waitQueueTimeoutMS=10000 # Maximum time to wait for a connection (10 seconds)
serverSelectionTimeoutMS=5000  # Timeout for server selection (5 seconds)
connectTimeoutMS=10000  # Connection establishment timeout (10 seconds)
socketTimeoutMS=30000   # Socket operation timeout (30 seconds)
```

### Singleton Pattern Implementation
- **Global Client Instance**: Uses `_mongo_client` singleton to avoid creating multiple connections
- **Thread Safety**: Implements thread locks to ensure concurrent access safety
- **Health Check**: Uses `ismaster` command instead of `ping` for efficient connection validation
- **Automatic Cleanup**: Registers cleanup function with `atexit` to properly close connections

### Performance Optimizations
- **Connection Reuse**: Eliminates the need to create new connections for each database operation
- **Reduced Ping Operations**: Only performs ping on initial connection creation
- **Dynamic Task Scheduling**: Task manager adjusts database check frequency based on workload
- **Error Handling**: Implements exponential backoff strategy for connection failures

### Monitoring & Maintenance
- **Connection Status**: Monitor active connections using `db.serverStatus().connections`
- **Performance Metrics**: Track CPU usage and response times
- **Log Analysis**: Monitor for excessive database operations or connection errors

## University Information Collection

- **Collection Name:** `universities`
- **Description:** Stores information about university admission details.

**Document Structure:**

```json
{
  "_id": "<ObjectID>",
  "university_name": "String", // e.g., "東京大学"
  "university_name_zh": "String", // Simplified Chinese name, e.g., "东京大学"
  "deadline": "String", // e.g., "20241206"
  "created_at": "DateTime", // Timestamp of document creation
  "is_premium": "Boolean", // Defaults to false. If true, indicates a featured university, used for priority sorting.
  "content": {
    "original_md": "String", // Content of the original markdown file
    "translated_md": "String", // Content of the translated markdown file
    "report_md": "String", // Content of the report markdown file
    "pdf_file_id": "ObjectId" // Reference to PDF file stored in GridFS
  }
}
```

**GridFS Collections:**
- `fs.files`: Stores PDF file metadata
- `fs.chunks`: Stores PDF file chunks (automatically managed by GridFS)

**GridFS File Metadata:**
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
  },
  "length": "Number", // File size in bytes
  "chunkSize": "Number", // Chunk size (default: 255KB)
  "uploadDate": "DateTime"
}
```

**Indexes:**

- `university_name`
- `deadline`
- A compound index on `[("university_name", 1), ("deadline", -1)]` for efficient querying of the latest information for a specific university.

## Blog Post Collection

- **Collection Name:** `blogs`
- **Description:** Stores blog posts.

**Document Structure:**

```json
{
  "_id": "<ObjectID>",
  "title": "String", // e.g., "How to apply for a Japanese university"
  "url_title": "String", // URL-friendly version of the title, e.g., "how-to-apply-for-a-japanese-university"
  "publication_date": "String", // e.g., "2023-10-26". Stored as a string for compatibility, but ISODate is recommended.
  "created_at": "DateTime", // Timestamp of document creation
  "md_last_updated": "DateTime", // Timestamp of the last update to the markdown content
  "html_last_updated": "DateTime", // Timestamp of the last HTML generation
  "content_md": "String", // The full markdown content of the blog post
  "content_html": "String" // The generated HTML content, for caching (Lazy Rebuild)
}
```

**Indexes:**

- `url_title` (Unique): For efficiently finding specific blog posts by their URL.
- `publication_date` (Descending): For sorting blog posts to find the most recent ones.
