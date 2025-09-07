# 功能需求文档：招生信息再生成

**版本:** 1.0
**日期:** 2025年9月7日

## 1.0 背景与目标

### 1.1 背景

当前系统中的招生信息分析流程 (`pdf_processor`) 是一个自动化的多步骤过程。其中，分析步骤仅使用**翻译后的中文 Markdown** (`content.translated_md`) 作为输入，根据预设的系统提示词 (`analysis_questions`) 生成一份基础分析报告，并将其存储在 `content.report_md` 字段中。

此流程的局限性在于，若因提示词不佳或模型理解有误导致 `content.report_md` 内容不理想，管理员无法便捷地仅针对分析步骤进行重试和优化。

### 1.2 目标

为提高 `content.report_md` 的质量和管理员工作效率，引入 **“招生信息再生成”** 功能。该功能允许管理员针对单个大学，使用其已有的中文译文 (`content.translated_md`) 作为数据源，通过在线修改系统提示词，来重新运行分析步骤，并用新结果覆盖旧的 `content.report_md`。

## 2.0 功能概述

1.  **入口点**: 在后台的“编辑大学信息”页面 (`edit_university.html`)，添加一个“再生成分析报告”的按钮。
2.  **再生成界面**: 点击按钮后，跳转到新页面。此页面展示当前的 `analysis_questions` 内容，并允许管理员编辑。
3.  **后台任务**: 管理员提交修改后的提示词后，系统启动一个后台异步任务。
4.  **核心逻辑**: 任务从 MongoDB 读取指定大学的 `content.translated_md` 内容，并使用用户在前端编辑后的“整段系统提示词”调用 `DocumentAnalyzer` 的分析逻辑（不再在后台二次合成）。
5.  **数据更新**: 任务成功后，将新生成的报告更新到该大学文档的 `content.report_md` 字段。
6.  **安全与策略约束（统一说明）**:
    *   CSRF: 所有涉及表单提交的 POST 接口启用 CSRF 防护。
    *   提示词持久化: `new_prompt` 仅用于本次任务，不写回配置或数据库。
    *   并发与覆盖: 不对同一大学的 `REGENERATE_ANALYSIS` 做并发限制，采用“最后写赢”。
    *   用户反馈: 任务创建后仅提示“已创建后台任务”，让管理员在后台任务列表中查看进度与结果。
    *   取消与重启: 不支持取消；不支持任务级断点重启（步骤内允许有限重试由实现决定）。

## 3.0 需求详述

### 3.1 用户界面 (UI)

1.  **入口**:
    *   在 `templates/admin/edit_university.html` 页面，在展示“基础分析报告” (`basic_analysis_report`) 的文本域附近，增加一个按钮。
    *   按钮文字：“再生成分析报告”。
    *   按钮链接指向 `/admin/university/<university_id>/regenerate`。

2.  **再生成页面**:
    *   **URL**: `/admin/university/<university_id>/regenerate`
    *   **页面标题**: "再生成分析报告 - [大学中文名称]"
    *   **内容**:
        *   一个 `<textarea>`，用于显示和编辑系统提示词。
        *   **提示词预填充**: 文本域中应预先填入当前 `config.analysis_questions` 的内容。
        *   一个“开始再生成”按钮。
    *   **模板**: 使用 `templates/admin/regenerate_analysis.html`。
    *   **字段来源**: 大学中文名称优先取文档字段 `name_zh`，若为空则回退 `name`，若仍为空则回退为大学 `_id` 的短格式（前 8 位）。
    *   **CSRF**: 页面表单包含 CSRF 隐藏字段，POST 时校验。

### 3.2 后端逻辑

1.  **新路由**:
    *   `GET /admin/university/<university_id>/regenerate`: 渲染再生成页面，预先在后端通过分析器的合成函数生成“完整系统提示词”，并传给模板（附带 CSRF token）。
    *   `POST /admin/university/<university_id>/regenerate`:
        *   接收修改后的“整段系统提示词” (`full_system_prompt`)。
        *   根据 `university_id` 从数据库中查询对应文档。
        *   读取数据源: 获取该文档的 `content.translated_md` 字段内容。
        *   **创建新任务**: 调用任务管理器，创建一个**新的、独立的后台任务**，类型定义为 `REGENERATE_ANALYSIS`。
        *   将 `university_id` 与 `full_system_prompt` 作为参数传递给新任务（不再传问题列表/术语，后台不进行二次合成）。
        *   重定向回编辑页，并附带提示消息（包含任务创建成功提示与“请前往后台任务列表查看进度”的说明）。
        *   **CSRF**: 必须通过 CSRF 校验后才处理提交。

2.  **任务管理 (Task Management)**
    *   将在系统的任务管理器中注册一个名为 `REGENERATE_ANALYSIS` 的新任务类型。
    *   此任务类型将关联一个专属的处理函数，该函数负责执行完整的再生成逻辑。它独立于处理完整PDF流程的 `run_pdf_processor`。
    *   **重启策略**: 为了简化实现，`REGENERATE_ANALYSIS` 任务类型 **不支持断点重启**。如果任务在执行过程中因任何原因（例如 AI API 调用失败、数据库超时等）而失败，其状态将被置为“失败”。管理员需要从UI界面手动重新发起一个新的再生成任务，而不能从失败点继续。
    *   **取消策略**: 不支持取消。
    *   **并发与覆盖策略**: 不限制同一大学的并发任务；若有多个任务完成，采用“最后写赢”（以完成时间为准）。不做去重。
    *   **用户反馈**: 任务创建后不提供单独详情页跳转，统一提示用户前往后台任务列表查看状态与日志。

3.  **任务执行逻辑 (Task Execution Logic)**
    *   任务处理器接收 `university_id`, `full_system_prompt` 作为输入；`translated_content` 从数据库读取。
    *   **步骤1: 调用分析工具**:
        *   实例化 `DocumentAnalyzer`。
        *   调用 `regenerate_report(md_content=translated_content, full_system_prompt=full_system_prompt)`，获取新的报告内容 `new_report_content`。
        *   **参数策略**: 不论是否再生成，分析阶段统一使用较低温度（降低幻觉）。`DocumentAnalyzer` 的并发由任务管理器统一调度，必要时每任务独立实例化以确保线程安全。
    *   **步骤2: 更新数据库**:
        *   任务成功后，执行数据库更新操作：`db.universities.update_one({"_id": ObjectId(university_id)}, {"$set": {"content.report_md": new_report_content}})`。
    *   **步骤3: 记录状态**:
        *   在任务开始、成功或失败时，更新任务状态和日志。

### 3.3 数据模型 (MongoDB)

*   **读取**: `content.translated_md`
*   **写入/更新**: `content.report_md`（不保留历史版本，直接覆盖）。
*   **提示词持久化**: `new_prompt` 不持久化到数据库或配置，仅用于本次任务。

## 4.0 对 `utils/ai/analysis_tool.py` 的改造方案

### 4.1 改造建议

1.  **抽出提示词合成函数**:
    *   新增 `compose_system_prompt(questions, translate_terms, base_system_prompt=None)`，用于将“基础段+问题+术语+注意/重要提示”合成为“完整系统提示词”。
    *   新增 `get_composed_system_prompt()` 返回基于当前配置合成的完整系统提示词（原流程使用）。

2.  **新增公共方法 `regenerate_report`**:
    *   **方法签名**: `regenerate_report(self, md_content: str, full_system_prompt: str) -> str`
    *   专用于再生成功能：直接用整段系统提示词进行分析（不再在后端重新合成），然后进行审核与报告生成。
    *   **参数策略**: 与原有 `md2report` 保持一致，低温度以降低幻觉风险。

*   **优点**: 对现有流程侵入性小，`md2report` 与原有从PDF开始的流程完全保持一致；再生成以整段系统提示词驱动，逻辑清晰。

## 5.0 验收标准

1.  管理员可以在大学编辑页面看到并使用“再生成分析报告”按钮。
2.  再生成页面能正确加载并允许修改 `analysis_questions`。
3.  提交后，后台创建了一个类型为 `REGENERATE_ANALYSIS` 的新任务。
4.  后台任务能正确读取 `content.translated_md` 的内容作为输入。
5.  后台任务调用 `DocumentAnalyzer` 时，使用的是用户提交的新提示词。
6.  任务成功后，数据库中 `content.report_md` 字段被新报告覆盖。
7.  原有的 `pdf_processor` 完整流程功能正常。
8.  如果一个 `REGENERATE_ANALYSIS` 任务失败，系统没有提供重启该任务的机制。用户唯一的选择是重新提交一个新的任务。
9.  POST 路由启用并通过 CSRF 校验；再生成页面包含 CSRF 字段。
10. `new_prompt` 不持久化；同一大学可并发提交，采用“最后写赢”。
11. 任务创建后编辑页提示“任务已创建，请前往后台任务列表查看状态”。