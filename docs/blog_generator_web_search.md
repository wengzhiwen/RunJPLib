# Blog生成器：材料扩展模式的 Web Search 支持

## 概述
材料扩展模式（`expand`）在写作前会先基于“用户输入的扩展写作方向”和“已选大学名称”执行一次网络检索（仅限日语权威来源），将检索到的要点整理为“补充材料”。（补充材料为日文纯文本，不包含URL。）随后会把：
- 用户输入内容
- 网络检索补充材料
- MongoDB 中该大学的原始材料（`original_md`）

一起传入写作 Agent，完成文章撰写与后续 Markdown 格式化。

## 环境变量
- `OPENAI_WEB_SEARCH_ENABLED`：是否启用 Web Search（默认 `true`）
- `OPENAI_WEB_SEARCH_MODEL`：用于 Web Search 的模型，默认 `gpt-4o-mini`
- `OPENAI_BLOG_WRITER_MODEL`：写作模型（默认 `gpt-4o`）
- `OPENAI_API_KEY`：OpenAI API Key（必填）

> 说明：当开启时，系统会自动执行一次网络检索；失败或关闭时则不添加补充材料，直接继续原流程。

## 行为说明
- 检索限定“仅使用日语权威来源”，输出为日文纯文本（由专用检索Agent产出，不含URL，不做翻译）。
- 为避免上下文过长，补充内容长度在内部控制（代码当前上限约 10000 字符）。
- 写作阶段仍严格遵循既有系统提示词与“仅基于材料、不得主观臆断”的要求。

## 调试建议
- 如需快速关闭检索：将 `OPENAI_WEB_SEARCH_ENABLED=false`。
- 如需切换更经济的搜索模型：设置 `OPENAI_WEB_SEARCH_MODEL=gpt-4o-mini`（默认）。
- 日志可查看 `BlogGenerator` 相关日志以确认检索与写作阶段输入长度与关键分支。

## 依赖
- `openai>=1.54.0`
- `openai-agents`

如需升级，请先更新 `requirements.txt` 再执行：
```bash
./venv/bin/pip install -r requirements.txt
```

