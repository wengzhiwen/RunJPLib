# 隐私保护机制

## 概述

大学聊天系统实现了基于浏览器会话的隐私保护机制，结合混合搜索策略和内存优化管理，确保用户聊天记录的私密性和安全性。该机制解决了传统基于IP地址的会话管理可能导致的隐私泄露问题，同时优化了搜索性能和内存使用。

## 问题背景

### 传统方案的隐私风险

在传统的基于IP地址的会话管理系统中，存在以下隐私风险：

1. **同一网络下的隐私泄露**：同一WiFi网络下的不同用户可能看到彼此的聊天记录
2. **无痕模式无效**：无痕浏览器与普通模式共享会话，无法实现真正的隐私隔离
3. **多标签页混淆**：同一用户的不同浏览器标签页可能共享会话状态
4. **设备间泄露**：同一用户在不同设备上可能看到其他设备的聊天记录
5. **搜索历史泄露**：混合搜索过程中的查询扩展和关键词可能泄露用户意图

### 解决方案

我们实现了基于浏览器会话ID的隐私保护机制，结合内存优化和搜索策略优化，确保隐私安全的同时提升系统性能。

## 技术实现

### 1. 浏览器会话ID生成

每个浏览器标签页/窗口都会生成唯一的会话标识符：

```javascript
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

**特点**：
- 格式：`bs_timestamp_randomstring`
- 存储：使用 `sessionStorage`，无痕模式下自动隔离
- 生命周期：浏览器标签页关闭时自动清除
- 隐私保护：每个会话独立，无交叉污染

### 2. 双重验证机制

系统采用双重验证机制，优先使用浏览器会话ID，回退到IP地址：

```python
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

### 3. 会话权限验证

严格的会话访问控制：

```python
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

### 4. 混合搜索隐私保护

在混合搜索过程中，确保查询扩展和关键词提取的隐私安全：

```python
def expand_query_with_keywords(self, original_query: str, university_name: str) -> Dict:
    """扩展查询并提取关键词 - 隐私保护版本"""
    prompt = f"""
作为日本大学招生信息专家，分析用户查询并提供搜索关键词。

大学：{university_name}
用户查询：{original_query}

请按以下JSON格式回答：
{{
    "is_valid_query": true/false,
    "query_type": "valid/invalid/unclear",
    "reason": "判断理由",
    "primary_query": "主要查询词",
    "expanded_queries": ["扩展查询1", "扩展查询2", ...],
    "exact_keywords": ["精确匹配关键词1", "关键词2", ...],
    "fuzzy_keywords": ["模糊匹配词1", "模糊匹配词2", ...],
    "search_strategy": "hybrid/keyword_only/vector_only",
    "confidence": 0.0-1.0
}}
"""
    
    # 使用临时变量，搜索完成后立即清理
    try:
        response = self.openai_client.chat.completions.create(
            model="gpt-4.1-nano-2025-04-14",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
            max_tokens=500,
        )
        
        result = json.loads(response.choices[0].message.content)
        
        # 验证和清理关键词
        result["exact_keywords"] = self._clean_keywords(result.get("exact_keywords", []))
        result["fuzzy_keywords"] = self._clean_keywords(result.get("fuzzy_keywords", []))
        
        return result
        
    finally:
        # 清理临时变量，保护隐私
        prompt = None
        response = None
```

### 5. 内存优化隐私保护

实时监控内存使用，自动清理敏感数据：

```python
def _cleanup_memory(self, force: bool = False):
    """清理内存 - 隐私保护版本"""
    current_time = time.time()
    
    # 每30秒最多清理一次，除非强制清理
    if not force and (current_time - self._last_cleanup) < 30:
        return
    
    memory_usage = self._check_memory_usage()
    
    if force or memory_usage > self._memory_threshold:
        # 清理正则缓存
        with self._cache_lock:
            if len(self._regex_cache) > self._max_cache_size:
                # 保留最近使用的一半
                items = list(self._regex_cache.items())
                keep_count = self._max_cache_size // 2
                self._regex_cache = dict(items[-keep_count:])
        
        # 清理弱引用
        self._weak_refs.clear()
        
        # 强制垃圾回收
        gc.collect()
        
        self._last_cleanup = current_time
        
        new_memory_usage = self._check_memory_usage()
        print(f"内存清理: {memory_usage:.1f}% → {new_memory_usage:.1f}%")
```

## 隐私保护效果

### ✅ 完全隔离的场景

1. **不同浏览器标签页**：每个标签页拥有独立的聊天会话
2. **无痕模式 vs 普通模式**：完全隔离，互不干扰
3. **同一网络不同用户**：无法看到彼此的聊天记录
4. **同一用户不同设备**：各自维护独立会话
5. **浏览器重启**：生成新的会话ID，无法恢复之前会话
6. **搜索查询隔离**：每个会话的查询扩展和关键词独立处理
7. **内存数据隔离**：搜索过程中的临时数据及时清理

### 🔒 安全限制保持

1. **IP级别限制**：防止API滥用和恶意访问
2. **速率限制**：防止攻击和资源耗尽
3. **CSRF保护**：防止跨站请求伪造
4. **会话超时**：1小时无活动自动过期
5. **内存监控**：防止内存泄漏和性能问题

## 数据库设计

### 会话表结构

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
      "response_length": 回答长度,
      "search_strategy": "hybrid/keyword_only/vector_only",  // 新增：搜索策略
      "memory_usage": "45.2%"  // 新增：内存使用率
    }
  ],
  "user_agent": "用户代理",
  "referer": "来源页面"
}
```

### 索引优化

- `browser_session_id + university_id + last_activity`: 隐私保护的会话查找
- `user_ip + start_time`: 用户查询优化（安全限制）
- `university_name + start_time`: 大学统计优化
- `session_id`: 唯一索引
- `start_time`: 时间范围查询优化

## 性能优化

### 1. 内存管理

- **实时监控**：使用psutil监控内存使用率
- **自动清理**：超过80%阈值时自动清理缓存
- **即时释放**：搜索完成后立即释放临时变量
- **垃圾回收**：每次搜索后强制GC

### 2. 搜索优化

- **并行执行**：向量搜索和关键词搜索并行执行
- **缓存策略**：正则表达式缓存，LRU清理
- **超时控制**：设置搜索超时，避免长时间等待

### 3. 隐私优化

- **临时变量清理**：搜索过程中的敏感数据及时清理
- **会话隔离**：每个浏览器会话完全独立
- **查询保护**：查询扩展过程中的隐私保护

## 监控和日志

### 1. 隐私监控

- **会话隔离检查**：确保不同会话间无数据泄露
- **内存使用监控**：防止内存泄漏导致的数据泄露
- **访问权限验证**：严格验证会话访问权限

### 2. 安全日志

- **会话创建日志**：记录会话创建和恢复
- **权限验证日志**：记录访问权限验证结果
- **异常访问日志**：记录异常访问模式

### 3. 性能日志

- **内存清理日志**：记录内存清理操作
- **搜索性能日志**：记录搜索耗时和内存使用
- **错误追踪日志**：记录系统错误和异常

## 最佳实践

### 1. 隐私保护

- **始终使用浏览器会话ID**：确保会话隔离
- **及时清理临时数据**：搜索完成后立即清理
- **监控内存使用**：防止内存泄漏
- **验证访问权限**：严格验证会话归属

### 2. 性能优化

- **并行搜索**：充分利用混合搜索的优势
- **缓存管理**：合理使用缓存，避免内存泄漏
- **超时控制**：设置合理的超时时间
- **资源监控**：实时监控系统资源使用

### 3. 安全考虑

- **定期清理过期会话**：自动清理过期会话
- **监控异常访问**：及时发现和处理异常访问
- **日志审计**：定期审计系统日志
- **权限最小化**：遵循最小权限原则

## 更新日志

### v2.0 (2025-01-26)
- ✅ **混合搜索隐私保护**：查询扩展和关键词提取的隐私安全
- ✅ **内存优化隐私保护**：实时监控和自动清理敏感数据
- ✅ **搜索策略隔离**：每个会话的搜索策略独立处理
- ✅ **性能优化**：内存使用优化，搜索速度提升

### v1.0 (2025-09-01)
- ✅ **浏览器会话隔离**：基于浏览器会话ID的隐私保护
- ✅ **双重验证机制**：浏览器会话ID + IP地址验证
- ✅ **会话权限验证**：严格的访问控制

---

*文档版本：v2.0*
*最后更新：2025-01-26*
