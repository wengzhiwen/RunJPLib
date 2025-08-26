# MongoDB Schema Design

This document outlines the design of the MongoDB collections for the RunJPLib project.

## University Information Collection

- **Collection Name:** `universities`
- **Description:** Stores information about university admission details.

**Document Structure:**

```json
{
  "_id": "<ObjectID>",
  "university_name": "String", // e.g., "東京大学"
  "deadline": "String", // e.g., "20241206"
  "created_at": "DateTime", // Timestamp of document creation/update
  "source_path": "String", // Original folder path, e.g., "pdf_with_md/東京大学_20241206"
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
  "publication_date": "String", // e.g., "2023-10-26"
  "created_at": "DateTime", // Timestamp of document creation/update
  "source_file": "String", // Original file name, e.g., "2023-10-26-how-to-apply.md"
  "content_md": "String" // The full markdown content of the blog post
}
```

**Indexes:**

- `publication_date`
- `title`
