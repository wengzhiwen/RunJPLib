# 招生信息处理器 - 本地 OCR 导入方案设计

> **当前状态**: 后台已移除 ZIP 导入入口，改为在 PDF 上传时可选附带参考 Markdown（B）以进行 OCR 后校对补强。若需恢复 ZIP 导入，请重新启用相关前后端入口。

## 目标与范围

### 目标
- 降低 OCR 阶段的 token 成本，充分利用本地算力。
- 支持单个/批量 PDF 的本地 OCR 处理。
- 将本地 OCR 结果打包为带时间戳的 zip，并在后台一键上传导入。
- 导入后从 `03_translate` 起继续原有处理流程，自动创建对应数量的任务。

### 非目标
- 不替换翻译/分析的 LLM 提供商。
- 不改变现有在线 OCR 的处理模式与界面。

## 现有流程概览

当前 `utils/document/pdf_processor.py` 的核心流程：
`01_pdf2img -> 02_ocr -> 03_translate -> 04_analysis -> 05_output`

## 新流程概览

新增"本地 OCR + 线上后处理"流程：
1. 本地使用 `pdf-craft` 执行 OCR，输出标准化目录与 `manifest.json`。
2. 自动生成带时间戳的 zip 包（包含原始 PDF + OCR 结果 + manifest）。
3. 管理后台上传 zip，系统解压、校验并为每个文档创建任务。
4. 任务从 `03_translate` 开始执行，复用既有翻译/分析/输出逻辑。

## zip 包结构设计

```
/
  manifest.json
  items/
    <item_id>/
      original.pdf
      original.md
      pages/
        page_001.md
        page_002.md
```

### manifest.json 示例
```json
{
  "generated_at": "2025-01-10T12:34:56Z",
  "source": "pdf-craft",
  "version": "1.0.0",
  "items": [
    {
      "item_id": "tokyo_u_2025",
      "university_name": "東京大学",
      "filename": "tokyo_u.pdf",
      "page_count": 42,
      "paths": {
        "original_pdf": "items/tokyo_u_2025/original.pdf",
        "original_md": "items/tokyo_u_2025/original.md",
        "pages_dir": "items/tokyo_u_2025/pages"
      },
      "checksums": {
        "original_pdf": "sha256:...",
        "original_md": "sha256:..."
      }
    }
  ]
}
```

## 后台上传与导入设计

### 新增 API
```
POST /admin/api/pdf/ocr-zip/upload
```

请求体：
- `zip_file`: zip 包
- `processing_mode`（可选，默认 normal）

### 服务端处理流程
1. 保存上传文件到临时目录
2. 安全解压（防 Zip Slip）
3. 读取并校验 `manifest.json`
4. 为每个 item 创建 `OCR_IMPORT` 类型任务，`restart_from_step=03_translate`
5. 将 `original.md` 复制到任务工作目录，`original.pdf` 传入 `PDFProcessor`

## 兼容性

- 现有在线 OCR 与批量 OCR 流程保持不变
- 管理端仍可上传单个 PDF 进行全流程处理
