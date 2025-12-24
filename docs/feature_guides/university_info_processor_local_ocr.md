# 招生信息处理器 - 本地OCR导入方案设计

本设计文档描述如何将 PDF 的 OCR 环节迁移到本地项目 `/home/wengzhiwen/dev/pdf-craft`，并在 RunJPLib 中新增“OCR 结果导入”流程，使后续翻译与分析仍基于线上 LLM 提供商完成。

> 更新说明：当前后台已移除 ZIP 导入入口，改为在 PDF 上传时可选附带参考 Markdown（B）以进行 OCR 后校对补强。若需恢复 ZIP 导入，请重新启用相关前后端入口。

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

其中 `02_ocr` 会生成：
- `task_dir/original.md`（合并后的 OCR Markdown）
- `task_dir/ocr/page_*.md`（可选的单页 OCR 结果）

## 新流程概览

新增“本地 OCR + 线上后处理”流程：
1. 本地使用 `pdf-craft` 执行 OCR，输出标准化目录与 `manifest.json`。
2. 自动生成带时间戳的 zip 包（包含原始 PDF + OCR 结果 + manifest）。
3. 管理后台上传 zip，系统解压、校验并为每个文档创建任务。
4. 任务从 `03_translate` 开始执行，复用既有翻译/分析/输出逻辑。

## 本地 CLI 设计（pdf-craft）

建议在 `pdf-craft` 中新增 CLI 子命令，例如：

```
pdf-craft runjplib-ocr \
  --input /path/to/pdf_or_dir \
  --output-dir /path/to/output \
  --lang jpn \
  --dpi 300 \
  --mode batch
```

### CLI 行为
- **输入**: 单个 PDF 或包含多个 PDF 的目录。
- **输出**: 在 `--output-dir` 下生成一个带时间戳的 zip 包。
- **单/批量**: 自动识别输入类型，或通过 `--mode` 强制。
- **日志**: 输出每个 PDF 的页数、耗时、成功/失败状态。

### zip 命名约定
```
runjplib-ocr-YYYYMMDD-HHMMSS.zip
```

## zip 包结构设计

为了让 RunJPLib 可直接从 `03_translate` 开始处理，需要在 zip 中包含原始 PDF 与 `original.md`。

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

### 关键字段说明
- `university_name`: 用于任务创建与最终文档归档。
- `original_pdf`: 用于 `05_output` 保存至 GridFS。
- `original_md`: 作为 `03_translate` 的输入。
- `checksums`: 用于防止上传/解压过程中的文件损坏。

## 后台上传与导入设计

### 新增页面/入口
在 `/admin/pdf/processor` 页面新增“OCR 结果导入”区域（或新页面 `/admin/pdf/ocr-import`）。

### 新增 API
```
POST /admin/api/pdf/ocr-zip/upload
```

请求体：
- `zip_file`: zip 包
- `processing_mode`（可选，默认 normal）

返回：
- `created_task_ids` 列表
- `skipped_items`（校验失败、重复等）

### 服务端处理流程
1. **保存上传文件** 到临时目录。
2. **安全解压**（防 Zip Slip）。
3. **读取 manifest.json** 并校验：
   - 文件存在性
   - 校验和
   - item 数量与命名合法性
4. **为每个 item 创建任务**：
   - `task_type`: 复用 `PDF_PROCESSING` 或新增 `OCR_IMPORT`。
   - `params` 新增字段：
     - `pdf_file_path`（original.pdf）
     - `original_md_path`（original.md）
     - `restart_from_step`: `03_translate`
     - `source`: `local_ocr`
5. **任务执行前准备**：
   - 将 `original.md` 复制到任务工作目录 `task_<id>/original.md`。
   - 将 `original.pdf` 作为 `pdf_file_path` 传入 `PDFProcessor`。
6. **运行任务**：
   - `PDFProcessor` 通过 `restart_from_step=03_translate` 直接进入翻译与后续步骤。

## 代码改动建议（高层设计）

### 新增组件
- `utils/document/ocr_importer.py`
  - 解压与校验 zip
  - 生成任务所需的临时文件与参数

### 扩展 TaskManager
- 新增 `create_ocr_import_tasks()` 或复用 `create_task()` 统一创建。
- 在执行阶段识别 `restart_from_step` 与 `original_md_path`。

### 扩展 PDFProcessor 任务初始化
在执行前增加准备步骤：
- 若存在 `original_md_path`，复制到 `task_dir/original.md`。
- 保证 `_load_previous_results()` 可读取到 OCR 结果。

## 失败处理与幂等性

- **校验失败**: 返回明确错误信息，且不创建任何任务。
- **部分失败**: 仅跳过坏 item，正常导入可用 item。
- **重复导入**: 若 `checksums.original_pdf` 与近期已导入一致，可拒绝或标记为重复（策略可配置）。

## 安全与限制

- 限制上传 zip 大小（例如 1GB）。
- 仅允许 `.zip` 文件。
- Zip 解压必须防 Zip Slip。
- 对 manifest 和路径做白名单校验。

## 兼容性

- 现有在线 OCR 与批量 OCR 流程保持不变。
- 管理端仍可上传单个 PDF 进行全流程处理。

## 未来扩展

- 支持只上传 OCR 结果、无需原始 PDF（需变更 `05_output` 的 GridFS 保存策略）。
- 支持 OCR 结果质量评估与人工修订。
