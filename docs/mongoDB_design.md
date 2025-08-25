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
    "report_md": "String", // Content of the report markdown file
    "ocr_full_text": "String", // Content of the full OCR text file
    "translation_full_text": "String", // Content of the full translation text file
    "original_pdf": "Binary" // The original PDF file stored as BSON binary data
  }
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
