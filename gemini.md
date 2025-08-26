# Gemini CLI 配置

该文件用于帮助为此项目自定义 Gemini 的行为。

默认情况下请使用中文作为工作语言。

## 项目概述

RunJPLib 是一个基于 Flask 的 Web 应用程序，提供有关大学和博客的信息。

## Gemini 的角色

请扮演一名专攻 Python 和 Flask 的高级软件工程师。在进行更改时，请遵守现有的代码风格和约定。

每次更改完成后都应该参考 pyproject.toml 中的设定，对代码进行格式化。

## 重要约定

 - 用户会自己启动和管理应用服务，不要企图启动或重启flask服务
 - 针对较为大范围的修改，总是应该先阅读 docs 目录下的文档
 - 每次修改完成后，应该更新 docs 目录下的文档，包括 docs/CHANGELOG.md
 - 如果需要更多的python依赖，应该先修改 requirements.txt 再执行 pip install -r requirements.txt

## 关键文件

- `venv/`: python虚拟环境
- `app.py`: 主要的 Flask 应用程序文件。
- `routes/`: 包含 Flask 路由。
- `templates/`: 包含 Jinja2 模板。
- `utils/`: 包含实用工具函数。

## 常用命令

- `flask run`: 运行开发服务器。
- `pytest`: 运行测试。