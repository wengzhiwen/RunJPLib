# 端口占用清理脚本使用说明

## 概述
这个脚本用于查找并杀掉占用 `FLASK_APP_PORT` 端口的程序。

## 功能特性
- 自动从 `.env` 文件中读取 `FLASK_APP_PORT` 配置
- 查找占用指定端口的进程
- 显示进程详细信息（PID、PPID、命令）
- 提供用户交互界面，支持优雅终止和强制杀掉
- 错误处理和权限检查

## 使用方法

```bash
# 激活虚拟环境（必需）
source venv/bin/activate

# 运行脚本
python3 kill_port.py
```

## 操作选项
当脚本找到占用端口的进程时，会提示你选择操作：
- `y` 或 `yes` - 优雅地终止进程（发送 SIGTERM 信号）
- `f` 或 `force` - 强制杀掉进程（发送 SIGKILL 信号）
- `n` 或 `no` - 取消操作

## 技术实现

### 核心依赖
- `python-dotenv` - 用于加载 `.env` 文件
- `subprocess` - 用于执行系统命令
- `os` - 用于进程信号处理

### 主要功能
1. **环境变量加载**：使用 `load_dotenv()` 加载 `.env` 文件
2. **端口查找**：使用 `lsof -ti :{port}` 查找占用端口的进程
3. **进程信息**：使用 `ps -p {pid}` 获取进程详细信息
4. **进程终止**：使用 `os.kill()` 发送终止信号

## 注意事项
1. **需要激活虚拟环境**，因为依赖 `python-dotenv` 包
2. 确保在项目根目录下运行脚本（包含 `.env` 文件的目录）
3. 脚本需要读取 `.env` 文件中的 `FLASK_APP_PORT` 配置
4. 某些进程可能需要管理员权限才能杀掉
5. 强制杀掉进程可能会导致数据丢失，请谨慎使用

## 示例输出
```
=== 端口占用清理脚本 ===
查找占用端口 5070 的进程...
找到 2 个占用端口 5070 的进程:
  1.  9138 86343 /opt/homebrew/Cellar/python@3.12/3.12.10/Frameworks/Python.framework/Versions/3.12/Resources/Python.app/Contents/MacOS/Python /Users/wengzhiwen/dev/RunJPLib/app.py
  2. 13360  9138 /opt/homebrew/Cellar/python@3.12/3.12.10/Frameworks/Python.framework/Versions/3.12/Resources/Python.app/Contents/MacOS/Python /Users/wengzhiwen/dev/RunJPLib/app.py

是否要杀掉这些进程? (y/n/f - f表示强制杀掉): y
终止进程 9138
终止进程 13360

成功终止了 2 个进程
```

## 代码结构

```python
#!/usr/bin/env python3
"""
端口占用清理脚本
查找并杀掉占用 FLASK_APP_PORT 端口的程序
"""

import os
import sys
import subprocess
import signal
from dotenv import load_dotenv

def main():
    # 加载 .env 文件
    load_dotenv()
    
    # 获取端口号
    port = os.getenv('FLASK_APP_PORT')
    
    # 查找占用端口的进程
    # 显示进程信息
    # 用户交互
    # 终止进程
```

## 更新历史

- **v2.0** - 使用 `python-dotenv` 简化代码，移除复杂的文件解析逻辑
- **v1.0** - 初始版本，手动解析 `.env` 文件
