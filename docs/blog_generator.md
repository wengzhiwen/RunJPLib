# BlogGenerator 设计与实现概览

## 职责
- 作为AI博客生成的核心服务层，封装与 `openai-agents` 的交互，统一调用入口。
- 基于不同模式组织上下文材料，生成结构化JSON：`{"title", "content", "universities"}`。
- 自动对生成结果进行Markdown格式化（仅格式，不改写内容）。
- 记录独立日志，支持排障与运行观测。

## 模块位置
- 代码：`utils/blog_generator.py`
- 关键依赖：`agents.Agent`, `agents.Runner`, `agents.trace`
- 日志：`utils.logging_config.setup_logger("BlogGenerator")`

## 支持的模式
- expand：基于大学材料进行“扩展写作”。
  - 材料来源：MongoDB中所选大学的 `original_md`（必要时先缩减）与 `report_md`。
  - 可选：在开启 `OPENAI_WEB_SEARCH_ENABLED=true` 时注入“网络检索补充材料”（仅日文权威来源）。
  - 系统提示词建议：`PROMPT_EXPAND`。
- compare：多校“对比写作”。
  - 对每所大学先缩减 `original_md`，再并入 `report_md`，最后统一交由写作Agent生成。
  - 系统提示词建议：`PROMPT_COMPARE`。
- user_prompt_only：只基于用户提示词进行写作。
  - 不读取大学材料。
  - 系统提示词建议：`PROMPT_USER_ONLY`。

## 处理流程（通用）
1. 初始化：加载环境变量、设定模型、禁用自动重试（`OPENAI_MAX_RETRIES=0`）。
2. 准备Agent：根据模式选择系统提示词，创建 `Agent` 实例。
3. 组织材料：
   - expand/compare：通过 `_get_university_materials()` 读取 MongoDB 的 `original_md` 与 `report_md`。
   - expand：若启用Web检索，则先调用 `_web_search_supplement()` 拼接补充文本。
   - compare：逐校执行缩减（`PROMPT_REDUCER`）。
4. 写作生成：使用 `_run_agent_and_parse_json()` 同步执行，严格产出JSON；若解析失败，返回“JSON格式错误”的兜底结果（原文透传）。
5. Markdown格式化：调用 `_format_content()`，仅做排版与语法纠正，不改写语义。
6. 返回结果：`{"title", "content", "universities"}`。

## 关键提示词
- `PROMPT_EXPAND`：扩展写作，标题需包含年份（当前年+1），严禁凭空信息，必须使用大学中文全名；返回JSON。
- `PROMPT_COMPARE`：多校对比写作，标题包含当年年份，强调共性与差异，返回JSON。
- `PROMPT_USER_ONLY`：基于用户参考内容重写与优化，限制只提及输入中出现的大学，返回JSON。
- `PROMPT_REDUCER`：招生简章缩减器，遵循严格的“保留/删除/简化”规则，输出语种与输入匹配。
- `PROMPT_FORMATTER`：Markdown格式化器，仅格式化，不改写内容，返回 `{formatted_content}`。
- `PROMPT_WEB_SEARCH`：仅用于补充材料检索，限制“日语权威来源”，输出纯文本（日文）。

## 环境变量
- `OPENAI_BLOG_WRITER_MODEL`（默认 `gpt-4o`）：写作与格式化所用模型。
- `OPENAI_WEB_SEARCH_ENABLED`（默认 `true`）：是否启用网络检索补充。
- `OPENAI_WEB_SEARCH_MODEL`（默认 `gpt-4o-mini`）：网络检索所用模型。
- `OPENAI_API_KEY`：必填。
- 运行时变量：`OPENAI_MAX_RETRIES=0`（禁用自动重试，避免429时重复请求）。

## 数据读取
- 来源：`MongoDB.RunJPLib.universities`
- 字段：`content.original_md`, `content.report_md`, `university_name`
- 访问：通过 `utils.mongo_client.get_mongo_client()` 获取客户端。

## 日志与观测
- 专用Logger：`BlogGenerator`，记录初始化配置、提示词长度、输出长度、解析状态。
- 关键追踪：`with trace("Agent-<name>")` 包裹调用，配合外部追踪系统。
- 典型警告：当检测到429错误时，仅记录警告，不做自动重试。

## 错误与降级策略
- JSON解析失败：返回兜底结构，`content` 保留原始输出，便于人工排查。
- 过长上下文：
  - expand：若 `original_md` > 10000 字，先经 `PROMPT_REDUCER` 缩减；若缩减失败，截断原文至10000字并追加省略号。
  - compare：始终对每所大学执行缩减，随后并入 `report_md`。
- 提示词超长：当组合提示词超过200000字符时实施截断并记录告警。
- Web检索失败：忽略补充材料，继续写作流程。

## 依赖
- `openai`（使用 Responses API）
- `openai-agents`
- `python-dotenv`
- `bson`
- `nest_asyncio`

安装/更新依赖：
```bash
./venv/bin/pip install -r requirements.txt
```

## 与Admin后台/API的关系
- 后端API：`POST /admin/api/blog/generate` 调用本模块生成内容；`POST /admin/api/blog/save` 完成持久化。
- 前端：参见 `docs/blog_creator_usage.md`，支持“直接输入并保存”（无需先生成）。

## 版本与变更要点（对应 2025-09-02 代码）
- 启用独立日志与trace包装，输出解析更稳健。
- compare模式统一“缩减+并入report_md”的材料组织策略。
- expand模式引入可选的日文权威来源Web检索补充材料，并对最终内容执行Markdown格式化。


