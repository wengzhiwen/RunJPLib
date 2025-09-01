# 大学AI对话系统设计文档

## 项目概述

为RunJPLib管理后台开发一个独立的大学AI对话测试系统，允许管理员选择特定大学，通过LlamaIndex进行文档检索，并使用OpenAI Agent进行智能对话。系统同时为普通用户提供基于Web的聊天界面，支持隐私保护和会话管理。

## 功能需求

### 核心功能
1. **大学选择**：参考新建博客的大学选择方式，支持搜索和选择
2. **Lazy Loading索引**：按需加载大学文档到LlamaIndex
3. **实时进度显示**：通过SSE连接显示索引加载进度
4. **智能对话**：基于大学招生信息的AI对话功能
5. **上下文隔离**：确保不同大学信息不混淆
6. **隐私保护**：基于浏览器会话的隐私隔离机制
7. **会话恢复**：智能恢复用户之前的对话历史

### 技术需求
- 嵌入模型：OpenAI text-embedding-ada-002
- 对话模型：gpt-4.1-nano-2025-04-14
- 向量存储：ChromaDB
- 文档处理：LlamaIndex
- 实时通信：Server-Sent Events (SSE)
- 隐私保护：浏览器会话ID + IP双重验证

## 系统架构

### 整体架构
```
用户界面 (Admin) 
    ↓
Flask路由 (chat_bp)
    ↓
大学选择 → 文档加载 → 索引构建 → 对话管理
    ↓
MongoDB (大学数据) → LlamaIndex (文档处理) → ChromaDB (向量存储)
    ↓
OpenAI Agent (对话生成)
```

### 数据流
1. **大学选择**：用户搜索并选择大学
2. **文档验证**：检查是否已有最新索引
3. **文档加载**：从MongoDB获取大学文档
4. **索引构建**：使用LlamaIndex处理文档
5. **向量存储**：存储到ChromaDB
6. **对话处理**：Agent检索并生成回答

## 技术实现

### 1. 依赖管理

**新增依赖包**：

加入到 requirement.txt 然后通过pip -r来安装。

```bash
pip install llama-index
pip install llama-index-embeddings-openai
pip install llama-index-vector-stores-chroma
pip install chromadb
```

**requirements.txt更新**：
```
llama-index>=0.9.0
llama-index-embeddings-openai>=0.1.0
llama-index-vector-stores-chroma>=0.1.0
chromadb>=0.4.0
```

### 2. 核心模块设计

#### 2.1 大学文档管理器
```python
# utils/university_document_manager.py
class UniversityDocumentManager:
    def __init__(self):
        self.db = get_db()
        self.index_cache = {}  # 缓存已构建的索引
    
    def get_latest_university_doc(self, university_name):
        """获取大学最新的招生信息文档"""
        # 按deadline降序排序，获取最新的文档
        return self.db.universities.find_one(
            {"university_name": university_name},
            sort=[("deadline", -1)]
        )
    
    def needs_reindex(self, university_id, last_updated):
        """检查是否需要重新索引"""
        # 检查索引是否存在且是最新的
        pass
```

#### 2.2 LlamaIndex集成器
```python
# utils/llama_index_integration.py
class LlamaIndexIntegration:
    def __init__(self):
        self.embedding_model = OpenAIEmbedding(
            model="text-embedding-ada-002"
        )
        self.chroma_client = chromadb.PersistentClient(
            path="./chroma_db"
        )
    
    def create_university_index(self, university_doc, progress_callback=None):
        """为大学创建索引"""
        # 文档预处理
        # 分块处理
        # 嵌入生成
        # 存储到ChromaDB
        pass
```

#### 2.3 对话管理器
```python
# utils/chat_manager.py
class ChatManager:
    def __init__(self):
        self.model = "gpt-4.1-nano-2025-04-14"
    
    def create_chat_session(self, university_id):
        """创建对话会话"""
        pass
    
    def process_message(self, session_id, user_message):
        """处理用户消息"""
        # 1. 从ChromaDB检索相关文档
        # 2. 构建上下文
        # 3. 调用OpenAI Agent
        # 4. 返回回答
        pass
```

### 3. 路由设计

#### 3.1 主要路由
```python
# routes/chat.py
@chat_bp.route('/chat', methods=['GET'])
@admin_required
def chat_page():
    """聊天页面"""
    return render_template('admin/chat.html')

@chat_bp.route('/api/chat/universities/search', methods=['GET'])
@admin_required
def search_universities():
    """搜索大学"""
    pass

@chat_bp.route('/api/chat/load-university', methods=['POST'])
@admin_required
def load_university():
    """加载大学文档"""
    pass

@chat_bp.route('/api/chat/load-progress/<task_id>')
@admin_required
def load_progress(task_id):
    """获取加载进度（SSE）"""
    pass

@chat_bp.route('/api/chat/send-message', methods=['POST'])
@admin_required
def send_message():
    """发送消息"""
    pass
```

## 用户界面设计

### 1. 页面结构

#### 1.1 大学选择页面
```
┌─────────────────────────────────────┐
│ 大学AI对话测试系统                  │
├─────────────────────────────────────┤
│ 1. 选择大学                         │
│    [搜索框] 输入大学名称...          │
│    [搜索结果列表]                   │
│                                     │
│ 2. 已选大学                         │
│    [大学标签] 东京大学 [×]           │
│                                     │
│ [开始对话] 按钮                     │
└─────────────────────────────────────┘
```

#### 1.2 加载进度页面
```
┌─────────────────────────────────────┐
│ 正在加载大学文档...                  │
├─────────────────────────────────────┤
│ 大学：东京大学                      │
│                                     │
│ [进度条] ████████░░ 80%             │
│                                     │
│ 当前步骤：生成向量嵌入               │
│ 预计剩余时间：30秒                   │
│                                     │
│ [取消] 按钮                         │
└─────────────────────────────────────┘
```

#### 1.3 对话界面
```
┌─────────────────────────────────────┐
│ 与东京大学的AI助手对话               │
├─────────────────────────────────────┤
│ [对话历史区域]                      │
│ 用户：这所大学的申请截止日期是什么？   │
│ 助手：根据东京大学的招生信息...       │
│                                     │
│ [输入框] 请输入您的问题...          │
│ [发送] 按钮                         │
├─────────────────────────────────────┤
│ [重新选择大学] [清空对话]            │
└─────────────────────────────────────┘
```

### 2. 交互流程

#### 2.1 大学选择流程
1. 用户在搜索框输入大学名称
2. 系统实时搜索并显示匹配结果
3. 用户点击选择大学
4. 显示已选大学标签
5. 点击"开始对话"进入下一步

#### 2.2 文档加载流程
1. 系统检查是否已有最新索引
2. 如需要，开始异步加载过程
3. 通过SSE实时推送进度信息
4. 显示当前步骤和预计时间
5. 加载完成后自动进入对话界面

#### 2.3 对话流程
1. 用户输入问题
2. 系统检索相关文档片段
3. 构建上下文并调用Agent
4. 返回AI回答
5. 保存对话历史

## 实现细节

### 隐私保护机制

#### 1. 浏览器会话ID生成
```javascript
// 前端会话管理
function getBrowserSessionId() {
    if (browserSessionId) return browserSessionId;
    
    // 尝试从sessionStorage获取
    browserSessionId = sessionStorage.getItem('universityChat_browserSessionId');
    
    if (!browserSessionId) {
        // 生成新的浏览器会话ID
        browserSessionId = 'bs_' + Date.now() + '_' + Math.random().toString(36).substr(2, 9);
        sessionStorage.setItem('universityChat_browserSessionId', browserSessionId);
    }
    
    return browserSessionId;
}
```

#### 2. 双重验证机制
```python
# 后端会话查找
def get_active_session_for_university(self, user_ip: str, university_id: str, browser_session_id: str = None):
    query = {"university_id": university_id, "last_activity": {"$gte": timeout_time}}
    
    if browser_session_id:
        # 优先使用浏览器会话ID查找
        query["browser_session_id"] = browser_session_id
    else:
        # 回退到IP地址查找（兼容旧会话）
        query["user_ip"] = user_ip
    
    return db.chat_sessions.find_one(query, sort=[("last_activity", -1)])
```

#### 3. 会话权限验证
```python
# 会话访问控制
def verify_session_access(session_detail, user_ip, browser_session_id, university_id):
    session_browser_id = session_detail.get("browser_session_id")
    session_ip = session_detail.get("user_ip")
    
    # 隐私保护：如果有浏览器会话ID，必须匹配
    if session_browser_id:
        if session_browser_id != browser_session_id:
            return False
    
    # 兼容没有浏览器会话ID的旧会话
    if not session_browser_id and session_ip != user_ip:
        return False
    
    # 验证大学ID
    return session_detail.get("university_id") == university_id
```

### 会话恢复机制

#### 1. 智能会话检测
- 根据浏览器会话ID + 大学ID查找活跃会话
- 1小时内无活动自动过期
- 支持历史消息加载（最近20条）

#### 2. 消息格式转换
```python
# 数据库格式转换为前端格式
def convert_message_format(db_messages):
    formatted_messages = []
    for msg in db_messages[-20:]:
        # 用户消息
        if "user_input" in msg and msg["user_input"]:
            formatted_messages.append({
                "role": "user",
                "content": msg["user_input"],
                "timestamp": msg.get("timestamp").isoformat()
            })
        
        # AI回复
        if "ai_response" in msg and msg["ai_response"]:
            formatted_messages.append({
                "role": "assistant",
                "content": msg["ai_response"],
                "timestamp": msg.get("timestamp").isoformat()
            })
    
    return formatted_messages
```

### 数据库设计

#### 1. 会话表结构
```javascript
{
  "_id": ObjectId,
  "session_id": "会话唯一ID",
  "user_ip": "用户IP地址",
  "browser_session_id": "浏览器会话ID",  // 新增：隐私保护
  "university_name": "大学名称",
  "university_id": "大学MongoDB ID",
  "start_time": ISODate,
  "last_activity": ISODate,
  "total_messages": 消息总数,
  "messages": [
    {
      "timestamp": ISODate,
      "user_input": "用户输入",
      "ai_response": "AI回答",
      "processing_time": 处理时间秒数,
      "input_length": 输入长度,
      "response_length": 回答长度
    }
  ],
  "user_agent": "用户代理",
  "referer": "来源页面"
}
```

#### 2. 索引优化
- `browser_session_id + university_id + last_activity`: 隐私保护的会话查找
- `user_ip + start_time`: 用户查询优化（安全限制）
- `university_name + start_time`: 大学统计优化
- `session_id`: 唯一索引
- `start_time`: 时间范围查询优化

### 1. 文档索引策略

#### 1.1 文档分块
```python
def split_university_document(university_doc):
    """智能分块大学文档"""
    chunks = []
    
    # 获取文档内容
    content = university_doc.get('content', {})
    original_md = content.get('original_md', '')
    translated_md = content.get('translated_md', '')
    report_md = content.get('report_md', '')
    
    # 按内容类型分块
    if original_md:
        chunks.extend(split_markdown(original_md, 'original'))
    if translated_md:
        chunks.extend(split_markdown(translated_md, 'translated'))
    if report_md:
        chunks.extend(split_markdown(report_md, 'report'))
    
    return chunks
```

#### 1.2 元数据设计
```python
chunk_metadata = {
    "university_id": "大学ID",
    "university_name": "大学名称",
    "content_type": "original|translated|report",
    "chunk_index": "块索引",
    "title": "块标题",
    "language": "japanese|chinese"
}
```

### 2. 检索策略

#### 2.1 混合检索
```python
def hybrid_search(query, university_id):
    """混合检索策略"""
    # 1. 关键词匹配
    keyword_results = keyword_search(query, university_id)
    
    # 2. 语义相似度
    semantic_results = semantic_search(query, university_id)
    
    # 3. 结果融合
    combined_results = combine_results(keyword_results, semantic_results)
    
    return combined_results
```

#### 2.2 上下文构建
```python
def build_context(relevant_chunks, conversation_history):
    """构建对话上下文"""
    context_parts = []
    
    # 添加相关文档片段
    for chunk in relevant_chunks:
        context_parts.append(f"--- {chunk['title']} ---")
        context_parts.append(chunk['content'])
    
    # 添加对话历史
    if conversation_history:
        context_parts.append("--- 对话历史 ---")
        for msg in conversation_history[-6:]:  # 最近3轮
            context_parts.append(f"{msg['role']}: {msg['content']}")
    
    return "\n".join(context_parts)
```

### 3. Agent配置

#### 3.1 系统提示词
```
你是一位专业的日本大学招生信息咨询助手。

当前大学：[大学名称]

你只能基于提供的大学信息来回答问题，不要编造任何信息。

注意事项：
1. 只回答与当前大学相关的问题
2. 如果信息不明确，请明确说明
3. 用中文回答
4. 保持专业、友好的语调
5. 拒绝回答与当前大学无关的问题
6. 如果用户询问其他大学的信息，请明确拒绝

请根据以下信息回答用户问题：
[相关文档内容]

当前问题：[用户问题]
```

#### 3.2 温度设置
```python
agent_config = {
    "model": "gpt-4.1-nano-2025-04-14",
    "temperature": 0.1,  # 低温度减少幻觉
    "max_tokens": 1000,
    "top_p": 0.9
}
```

## 性能优化

### 1. 缓存策略
- **索引缓存**：已构建的索引存储在内存中
- **文档缓存**：频繁访问的文档缓存
- **会话缓存**：活跃对话会话缓存

### 2. 异步处理
- **文档加载**：异步加载避免阻塞UI
- **索引构建**：后台异步构建
- **消息处理**：异步处理用户消息

### 3. 资源管理
- **内存管理**：定期清理过期缓存
- **磁盘管理**：ChromaDB数据定期清理
- **连接池**：数据库连接池管理

## 监控和日志

### 1. 性能监控
```python
# 监控指标
metrics = {
    "index_build_time": "索引构建时间",
    "retrieval_time": "检索响应时间",
    "agent_response_time": "Agent响应时间",
    "cache_hit_rate": "缓存命中率",
    "error_rate": "错误率"
}
```

### 2. 日志记录
```python
# 日志级别
logging.info("用户选择了大学: %s", university_name)
logging.info("开始构建索引: %s", university_id)
logging.info("索引构建完成: %s, 耗时: %s", university_id, duration)
logging.warning("检索无结果: %s", query)
logging.error("Agent调用失败: %s", error)
```

## 部署和配置

### 1. 环境变量

已经人工设置到env文件，代码只要直接使用即可。

```bash
# LlamaIndex配置
LLAMA_INDEX_CACHE_DIR=./llama_index_cache
CHROMA_DB_PATH=./chroma_db

# OpenAI配置
OPENAI_API_KEY=your_api_key
OPENAI_EMBEDDING_MODEL=text-embedding-ada-002
OPENAI_CHAT_MODEL=gpt-4.1-nano-2025-04-14

# 系统配置
CHAT_SESSION_TIMEOUT=3600  # 会话超时时间（秒）
MAX_CACHE_SIZE=1000        # 最大缓存条目数
```

### 2. 目录结构
```
project/
├── utils/
│   ├── university_document_manager.py
│   ├── llama_index_integration.py
│   └── chat_manager.py
├── routes/
│   └── chat.py
├── templates/admin/
│   ├── chat.html
│   └── chat_components.html
├── static/admin/js/
│   └── chat.js
├── chroma_db/              # ChromaDB数据目录
└── llama_index_cache/      # LlamaIndex缓存目录
```


## 风险评估及action plan

### 1. 技术风险
- **API限制**：OpenAI API调用频率限制，嵌入式不需要限制，对话进行限制每分钟最大1次人工输入，如果遇到限制
- **内存泄漏**：长时间运行可能导致内存问题，暂时不处理
- **数据一致性**：索引与源数据不一致，以mongoDB中记录的大学名称、创建日期、报名截止日来保证索引的一致性，如果数据发生变化需要重新索引。必要时在mongoDB中增加相关字段来进行管理

### 2. 成本风险
- **API费用**：大量API调用可能产生高费用，暂不考虑
- **存储成本**：向量数据库存储成本，暂不考虑

### 3. 缓解措施
- **资源监控**：实时监控资源使用情况
- **成本控制**：设置API调用预算限制


## 总结

本设计文档提供了一个完整的大学AI对话系统解决方案，通过LlamaIndex实现文档隔离和智能检索，结合OpenAI Agent提供高质量的对话体验。系统采用模块化设计，具有良好的可扩展性和维护性。
