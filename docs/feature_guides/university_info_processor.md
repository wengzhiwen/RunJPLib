# 招生信息处理器

招生信息处理器是 RunJPLib 的核心功能之一，它允许管理员上传大学的 PDF 招生简章，系统会自动进行一系列处理，最终将结构化的招生信息存入数据库。

## 功能概述

- **自动化处理流程**: 基于工作流引擎，将复杂的处理过程分解为多个独立的、可管理的步骤。
- **异步任务处理**: 所有 PDF 处理都在后台异步执行，管理员可以提交多个任务而无需等待。
- **多种处理模式**: 支持"普通模式"（实时处理）和"批量模式"（成本优化，约节省 50%）。
- **可选参考校对**: PDF 上传时可附带参考 Markdown（B），用于在 OCR 后对结果进行校对补强。
- **智能名称识别**: 在处理过程中，利用 AI 自动识别并提取大学的简体中文全称。
- **并发任务处理**: 支持可配置的最大并发任务数，充分利用等待时间。
- **任务管理与监控**: 提供完整的后台界面，用于监控任务进度、查看日志，并支持从任意步骤重启失败的任务。

## 处理流水线：Agent 协作工作流

核心是 `utils/document/pdf_processor.py` 中的 `PDFProcessor` 类，基于 `buffalo-workflow` 工作流引擎编排处理流程。每个步骤由专门的工具或 Agent 执行。

### 工作流步骤详解

1.  **PDF 转图片 (`01_pdf2img`)**
    - 使用 `pdf2image` 库将 PDF 每一页转换为指定 DPI 的 PNG 图片。

2.  **OCR 识别 (`02_ocr`)**
    - **普通模式**: `ImageOcrProcessor` 逐一调用 OpenAI Vision API 进行文字识别。
    - **批量模式**: `BatchOcrProcessor` 将识别请求打包，通过 OpenAI Batch API 一次性提交。智能分批（每批最多 40 页），每 5 分钟检查批次状态，失败页面自动用普通模式补救。
    - **可选校对补强**: 如果上传了参考 Markdown（B），OCR 完成后使用 `OPENAI_ANALYSIS_MODEL` 对 A/B 进行校对补强，输出校对后的日文 Markdown（C）。

3.  **翻译 Agent (`03_translate`)**
    - `DocumentTranslator` 接收 OCR 识别的日文文本，参考 `TRANSLATE_TERMS_FILE` 术语表，翻译为简体中文 Markdown。

4.  **分析 Agent (`04_analysis`)**
    - `DocumentAnalyzer` 向 AI 提交包含多个问题的复杂 Prompt（问题列表从 `ANALYSIS_QUESTIONS_FILE` 加载），生成结构化分析报告。
    - 报告开头标识大学简体中文全称，供后续步骤提取。

5.  **发布 (`05_output`)**
    - 从分析报告中提取中文名，将原始 PDF 上传到 GridFS，创建 `universities` 文档并存入数据库。

## 校对补强与 Proof 归档

当发生"校对补强"时，系统在项目根目录 `proof/` 下生成一个以 `时间戳_大学名称` 命名的文件夹，保存三份文件：

- `A_original.md`: OCR 原始结果（A）
- `B_reference.md`: 上传的参考 Markdown（B）
- `C_refined.md`: 校对后的结果（C）

用于质量追踪和事后审计。

## 招生信息再生成

管理员可以在编辑大学信息页面，对已有的分析报告进行重新生成：

1. **入口**: 在"编辑招生信息"页面的分析报告区域，点击"再生成分析报告"按钮。
2. **编辑提示词**: 跳转到再生成页面，系统预填充当前的 `analysis_questions` 内容，管理员可自由编辑。
3. **后台执行**: 提交后创建 `REGENERATE_ANALYSIS` 类型的后台任务，读取已有的 `content.translated_md` 作为输入。
4. **覆盖写入**: 任务成功后，新报告覆盖写入 `content.report_md`（最后写赢策略）。

**设计约束**:
- 再生成任务不支持断点重启，失败后需手动重新提交。
- 提示词不持久化，仅用于本次任务。
- 同一大学可并发提交多个再生成任务。

## 任务管理

### 任务类型

| 类型 | 说明 |
|------|------|
| `PDF_PROCESSING` | 完整的 PDF 五步处理流程 |
| `OCR_IMPORT` | 本地 OCR 结果导入，从翻译步骤开始 |
| `TAG_UNIVERSITIES` | 大学标签批量生成 |
| `REGENERATE_ANALYSIS` | 分析报告再生成 |
| `REFINE_AND_REGENERATE` | 校对补强 + 再生成 |

### 并发调度

- 最大并发数通过 `PDF_MAX_CONCURRENT_TASKS` 环境变量控制（默认 1）。
- 任务进入长时间等待时（如批量 OCR 轮询），通过 `notify_task_is_waiting()` 通知管理器检查队列，尝试启动新任务。

### PID 监控与中断恢复

- 任务启动时记录进程 ID (`pid` 字段)。
- 后台 API 检查 PID 是否存活，自动将"僵尸"任务标记为 `interrupted`。
- 管理员可从任意步骤重启 `interrupted` 或 `failed` 的任务。
- `REGENERATE_ANALYSIS` 类型不支持断点重启。

### 独立任务日志

`TaskManager` 和 `PDFProcessor` 共享独立的按日分割日志文件 `log/TaskManager_YYYYMMDD.log`，详细记录任务的创建、入队、出队、启动、等待和完成过程。
