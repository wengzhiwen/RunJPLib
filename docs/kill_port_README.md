# 系统工具使用指南

## 端口管理工具

### kill_port.py

一个用于终止占用特定端口的进程的Python脚本。

#### 功能特点
- 自动检测指定端口上的进程
- 安全地终止进程（先尝试SIGTERM，再使用SIGKILL）
- 支持多个端口同时处理
- 提供详细的进程信息

#### 使用方法

```bash
# 终止单个端口
python kill_port.py 5000

# 终止多个端口
python kill_port.py 5000 8000 3000

# 查看帮助
python kill_port.py --help
```

#### 示例输出
```
正在检查端口 5000...
发现进程 PID 12345 (python) 占用端口 5000
正在终止进程...
进程已成功终止
```

#### 安全特性
- 优先使用SIGTERM信号，给进程优雅关闭的机会
- 如果SIGTERM无效，才使用SIGKILL强制终止
- 显示详细的进程信息，便于确认

## 索引状态检查工具

### check_index_status.py

用于检查指定大学在MongoDB中的状态和在LlamaIndex中的索引状态的调试工具。

#### 功能特点
- 检查MongoDB中大学文档的最新状态
- 验证LlamaIndex/ChromaDB中的索引状态
- 比较数据库和索引的时间戳
- 提供详细的诊断信息

#### 使用方法

```bash
# 检查指定大学的索引状态
python tools/check_index_status.py "京都工芸繊維大学"

# 检查其他大学
python tools/check_index_status.py "东京大学"
```

#### 示例输出
```
--- 开始检查大学: 京都工芸繊維大学 ---

[步骤 1/2] 正在查询 MongoDB...
  - MongoDB 文档 ID: 507f1f77bcf86cd799439011
  - MongoDB last_modified: 2025-01-26T10:30:00.000Z (类型: <class 'datetime.datetime'>)

[步骤 2/2] 正在查询 LlamaIndex/ChromaDB...
  - 索引元数据: {'source_last_modified': '2025-01-26T10:30:00.000Z'}
  - 索引 source_last_modified: 2025-01-26T10:30:00.000Z (类型: <class 'str'>)

--- 结论 ---
  - 时间戳一致。数据库版本和索引版本相同。(2025-01-26T10:30:00.000Z)
  - 结论：如果问题仍然存在，说明问题与时间戳检查无关，可能在其他地方。
```

#### 诊断功能
- **时间戳比较**：比较MongoDB和LlamaIndex的时间戳
- **索引存在性检查**：验证索引是否已创建
- **数据一致性验证**：确保数据库和索引数据一致
- **问题定位**：帮助定位索引更新问题

#### 使用场景
- 调试索引更新问题
- 验证混合搜索功能
- 检查数据同步状态
- 系统维护和故障排除

## 系统维护工具

### 数据库索引管理

#### 创建索引
```bash
# 创建所有必要的数据库索引
python -c "from utils.db_indexes import create_indexes; create_indexes()"
```

#### 检查索引状态
```bash
# 检查MongoDB索引
python -c "from utils.db_indexes import check_indexes; check_indexes()"
```

### 日志管理

#### 查看检索日志
```bash
# 实时查看检索日志
tail -f log/retrieval.log

# 查看最近的检索记录
tail -n 50 log/retrieval.log
```

#### 查看应用日志
```bash
# 查看今天的应用日志
cat log/app_$(date +%Y%m%d).log

# 搜索特定大学的日志
grep "京都工芸繊維大学" log/retrieval.log
```

## 性能监控工具

### 内存使用监控

#### 实时监控
```bash
# 监控内存使用率
python -c "
import psutil
import time
while True:
    memory = psutil.virtual_memory()
    print(f'内存使用率: {memory.percent:.1f}%')
    time.sleep(5)
"
```

#### 搜索性能监控
```bash
# 分析搜索性能日志
grep "混合搜索耗时" log/retrieval.log | tail -10
```

## 故障排除指南

### 常见问题

#### 1. 端口被占用
```bash
# 检查端口占用
lsof -i :5000

# 终止占用进程
python kill_port.py 5000
```

#### 2. 索引不同步
```bash
# 检查索引状态
python tools/check_index_status.py "大学名称"

# 重新创建索引
python -c "from utils.llama_index_integration import LlamaIndexIntegration; LlamaIndexIntegration().recreate_index('大学ID')"
```

#### 3. 内存使用过高
```bash
# 检查内存使用
ps aux | grep python

# 重启应用
pkill -f "python app.py"
python app.py
```

#### 4. 搜索功能异常
```bash
# 检查检索日志
tail -f log/retrieval.log

# 检查OpenAI API状态
curl -H "Authorization: Bearer $OPENAI_API_KEY" https://api.openai.com/v1/models
```

### 调试技巧

#### 1. 启用详细日志
```bash
# 设置日志级别为DEBUG
export LOG_LEVEL=DEBUG
python app.py
```

#### 2. 检查环境变量
```bash
# 验证环境变量
python -c "import os; print('OPENAI_API_KEY:', 'SET' if os.getenv('OPENAI_API_KEY') else 'NOT SET')"
```

#### 3. 测试混合搜索
```bash
# 使用测试脚本验证搜索功能
python -c "
from utils.enhanced_search_strategy import EnhancedSearchStrategy
from utils.llama_index_integration import LlamaIndexIntegration
from openai import OpenAI

searcher = EnhancedSearchStrategy(LlamaIndexIntegration(), OpenAI())
result = searcher.expand_query_with_keywords('有计算机系吗？', '京都工芸繊維大学')
print(result)
"
```

## 最佳实践

### 1. 定期维护
- 每周检查索引状态
- 监控内存使用情况
- 清理过期日志文件

### 2. 性能优化
- 定期重启应用释放内存
- 监控搜索响应时间
- 优化数据库查询

### 3. 安全考虑
- 定期更新依赖包
- 监控异常访问日志
- 备份重要数据

---

*文档版本：v2.0*
*最后更新：2025-01-26*
