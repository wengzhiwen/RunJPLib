#!/usr/bin/env python3
"""
增强搜索策略：混合向量搜索和优化的关键词搜索
内存优化版本，适用于内存受限的服务器环境
"""
import re
import time
import gc
import weakref
from typing import Dict, List, Optional, Tuple, Set
from concurrent.futures import ThreadPoolExecutor
import threading
import psutil
import os


class EnhancedSearchStrategy:
    """增强的混合搜索策略 - 内存优化版本"""

    def __init__(self, llama_index_integration, openai_client):
        self.llama_index = llama_index_integration
        self.openai_client = openai_client

        # 内存优化：限制正则缓存大小
        self._regex_cache = {}
        self._cache_lock = threading.Lock()
        self._max_cache_size = 50  # 限制缓存大小

        # 内存监控
        self._memory_threshold = 80  # 内存使用超过80%时触发清理
        self._last_cleanup = time.time()

        # 使用弱引用避免循环引用
        self._weak_refs = set()

    def _check_memory_usage(self) -> float:
        """检查当前内存使用率"""
        try:
            memory_info = psutil.virtual_memory()
            return memory_info.percent
        except Exception:
            return 0.0

    def _cleanup_memory(self, force: bool = False):
        """清理内存"""
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

    def __del__(self):
        """析构时清理资源"""
        try:
            self._cleanup_memory(force=True)
        except Exception:
            pass

    def expand_query_with_keywords(self, original_query: str, university_name: str) -> Dict:
        """
        扩展查询并提取关键词

        Returns:
            {
                "is_valid_query": bool,
                "primary_query": str,
                "expanded_queries": List[str],
                "exact_keywords": List[str],      # 精确匹配关键词
                "fuzzy_keywords": List[str],      # 模糊匹配关键词
                "search_strategy": str            # "hybrid", "keyword_only", "vector_only"
            }
        """
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

关键词提取规则：
1. exact_keywords：专业名称、学科名称等需要精确匹配的术语
2. fuzzy_keywords：相关概念、同义词等可以模糊匹配的词汇
3. search_strategy选择：
   - "keyword_only": 专业名称查询等需要精确匹配的场景
   - "vector_only": 复杂概念查询等需要语义理解的场景  
   - "hybrid": 大部分情况，结合两种方法

示例：
- 查询"有计算机系吗" → exact_keywords:["情報工学","計算機科学"], fuzzy_keywords:["コンピュータ","情報","システム"]
- 查询"学费多少" → exact_keywords:["学费","授業料"], fuzzy_keywords:["費用","料金"], strategy:"keyword_only"
"""

        try:
            response = self.openai_client.chat.completions.create(
                model="gpt-4.1-nano-2025-04-14",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,
                max_tokens=500,
            )

            import json

            result = json.loads(response.choices[0].message.content)

            # 验证和清理关键词
            result["exact_keywords"] = self._clean_keywords(result.get("exact_keywords", []))
            result["fuzzy_keywords"] = self._clean_keywords(result.get("fuzzy_keywords", []))

            return result

        except Exception as e:
            print(f"查询扩展失败: {e}")
            return {
                "is_valid_query": True,
                "primary_query": original_query,
                "expanded_queries": [original_query],
                "exact_keywords": [original_query],
                "fuzzy_keywords": [],
                "search_strategy": "hybrid",
                "confidence": 0.5,
            }

    def _clean_keywords(self, keywords: List[str]) -> List[str]:
        """清理和验证关键词"""
        cleaned = []
        for kw in keywords:
            if isinstance(kw, str) and len(kw.strip()) > 0:
                # 移除特殊字符，保留字母、数字、中日文字符
                clean_kw = re.sub(r"[^\w\u3040-\u309F\u30A0-\u30FF\u4E00-\u9FAF]", "", kw.strip())
                if len(clean_kw) >= 2:  # 最少2个字符
                    cleaned.append(clean_kw)
        return list(set(cleaned))  # 去重

    def optimized_keyword_search(
        self, university_doc: Dict, keywords: List[str], exact_match: bool = True
    ) -> List[Dict]:
        """
        优化的关键词搜索，避免全文检索的性能问题

        Args:
            university_doc: 大学文档
            keywords: 关键词列表
            exact_match: 是否精确匹配
        """
        content = university_doc.get("content", {})
        results = []

        # 内容类型优先级：原文 > 翻译 > 报告
        content_priority = [("original_md", "japanese"), ("translated_md", "chinese"), ("report_md", "chinese")]

        for content_type, language in content_priority:
            text = content.get(content_type, "")
            if not text:
                continue

            matches = self._search_in_text(text, keywords, exact_match)
            if matches:
                results.extend(
                    [
                        {
                            "content": match["context"],
                            "score": match["score"],
                            "metadata": {
                                "content_type": content_type,
                                "language": language,
                                "match_type": "exact" if exact_match else "fuzzy",
                                "matched_keywords": match["keywords"],
                                "position": match["position"],
                            },
                        }
                        for match in matches
                    ]
                )

        # 按匹配质量排序
        results.sort(key=lambda x: x["score"], reverse=True)
        return results[:10]  # 限制返回数量

    def _search_in_text(self, text: str, keywords: List[str], exact_match: bool) -> List[Dict]:
        """在文本中搜索关键词，返回上下文"""
        matches = []
        text_lower = text.lower()

        for keyword in keywords:
            keyword_lower = keyword.lower()

            if exact_match:
                # 精确匹配 - 对于中日文，不使用词边界
                if any(
                    "\u4e00" <= char <= "\u9fff" or "\u3040" <= char <= "\u309f" or "\u30a0" <= char <= "\u30ff"
                    for char in keyword
                ):
                    # 中日文字符，直接匹配
                    pattern = self._get_compiled_regex(re.escape(keyword), re.IGNORECASE)
                else:
                    # 英文字符，使用词边界
                    pattern = self._get_compiled_regex(f"\\b{re.escape(keyword)}\\b", re.IGNORECASE)
            else:
                # 模糊匹配
                pattern = self._get_compiled_regex(re.escape(keyword), re.IGNORECASE)

            for match in pattern.finditer(text):
                start, end = match.span()

                # 提取上下文（前后各100字符）
                context_start = max(0, start - 100)
                context_end = min(len(text), end + 100)
                context = text[context_start:context_end]

                # 计算匹配分数
                score = self._calculate_keyword_score(keyword, context, exact_match)

                matches.append({"keywords": [keyword], "context": context, "score": score, "position": start})

        # 合并重叠的匹配
        return self._merge_overlapping_matches(matches)

    def _get_compiled_regex(self, pattern: str, flags: int = 0) -> re.Pattern:
        """获取预编译的正则表达式（带缓存）"""
        cache_key = (pattern, flags)

        if cache_key not in self._regex_cache:
            with self._cache_lock:
                if cache_key not in self._regex_cache:
                    self._regex_cache[cache_key] = re.compile(pattern, flags)

        return self._regex_cache[cache_key]

    def _calculate_keyword_score(self, keyword: str, context: str, exact_match: bool) -> float:
        """计算关键词匹配分数"""
        base_score = 0.8 if exact_match else 0.6

        # 关键词长度权重
        length_weight = min(len(keyword) / 10, 1.0)

        # 上下文相关性（简单启发式）
        context_lower = context.lower()
        keyword_lower = keyword.lower()

        context_boost = 0.0
        if any(term in context_lower for term in ["課程", "学科", "専攻", "学域"]):
            context_boost += 0.2
        if any(term in context_lower for term in ["募集", "入学", "受験"]):
            context_boost += 0.1

        return min(base_score + length_weight * 0.2 + context_boost, 1.0)

    def _merge_overlapping_matches(self, matches: List[Dict]) -> List[Dict]:
        """合并重叠的匹配结果"""
        if not matches:
            return matches

        # 按位置排序
        matches.sort(key=lambda x: x["position"])

        merged = [matches[0]]
        for current in matches[1:]:
            last = merged[-1]

            # 如果位置重叠，合并结果
            if abs(current["position"] - last["position"]) < 200:
                # 合并关键词
                last["keywords"].extend(current["keywords"])
                last["keywords"] = list(set(last["keywords"]))

                # 使用更高的分数
                last["score"] = max(last["score"], current["score"])

                # 扩展上下文
                if len(current["context"]) > len(last["context"]):
                    last["context"] = current["context"]
            else:
                merged.append(current)

        return merged

    def hybrid_search(self, university_id: str, query_analysis: Dict, top_k: int = 5) -> List[Dict]:
        """
        混合搜索：结合向量搜索和关键词搜索 - 内存优化版本

        Args:
            university_id: 大学ID
            query_analysis: 查询分析结果
            top_k: 返回结果数量
        """
        strategy = query_analysis.get("search_strategy", "hybrid")

        start_time = time.time()
        initial_memory = self._check_memory_usage()

        # 搜索前检查内存
        if initial_memory > self._memory_threshold:
            self._cleanup_memory(force=True)

        try:
            # 并行执行向量搜索和关键词搜索
            with ThreadPoolExecutor(max_workers=2) as executor:

                vector_future = None
                keyword_future = None

                if strategy in ["hybrid", "vector_only"]:
                    # 向量搜索
                    vector_future = executor.submit(
                        self._vector_search_wrapper, university_id, query_analysis.get("primary_query", ""), top_k
                    )

                if strategy in ["hybrid", "keyword_only"]:
                    # 关键词搜索
                    keyword_future = executor.submit(
                        self._keyword_search_wrapper,
                        university_id,
                        query_analysis.get("exact_keywords", []),
                        query_analysis.get("fuzzy_keywords", []),
                    )

                # 收集结果
                vector_results = []
                keyword_results = []

                if vector_future:
                    try:
                        vector_results = vector_future.result(timeout=5.0)
                    except Exception as e:
                        print(f"向量搜索失败: {e}")

                if keyword_future:
                    try:
                        keyword_results = keyword_future.result(timeout=3.0)
                    except Exception as e:
                        print(f"关键词搜索失败: {e}")

            # 合并和重排序结果
            final_results = self._merge_and_rerank(vector_results, keyword_results, query_analysis, top_k)

            search_time = time.time() - start_time
            final_memory = self._check_memory_usage()

            print(f"混合搜索耗时: {search_time:.3f}秒, 内存: {initial_memory:.1f}% → {final_memory:.1f}%")

            return final_results

        finally:
            # 搜索完成后立即清理内存
            try:
                # 清理局部变量
                vector_results = None
                keyword_results = None

                # 如果内存使用增长超过5%，强制清理
                current_memory = self._check_memory_usage()
                if current_memory - initial_memory > 5:
                    self._cleanup_memory(force=True)
                else:
                    # 轻量级清理
                    gc.collect()

            except Exception:
                pass

    def _vector_search_wrapper(self, university_id: str, query: str, top_k: int) -> List[Dict]:
        """向量搜索包装器"""
        try:
            results = self.llama_index.search_university_content(university_id, query, top_k)
            # 为向量搜索结果添加标记
            for result in results:
                result["search_type"] = "vector"
            return results
        except Exception as e:
            print(f"向量搜索异常: {e}")
            return []

    def _keyword_search_wrapper(
        self, university_id: str, exact_keywords: List[str], fuzzy_keywords: List[str]
    ) -> List[Dict]:
        """关键词搜索包装器"""
        try:
            # 获取大学文档
            from utils.mongo_client import get_db

            db = get_db()
            from bson import ObjectId

            university_doc = db.universities.find_one({"_id": ObjectId(university_id)})
            if not university_doc:
                return []

            results = []

            # 精确关键词搜索
            if exact_keywords:
                exact_results = self.optimized_keyword_search(university_doc, exact_keywords, exact_match=True)
                for result in exact_results:
                    result["search_type"] = "keyword_exact"
                results.extend(exact_results)

            # 模糊关键词搜索
            if fuzzy_keywords:
                fuzzy_results = self.optimized_keyword_search(university_doc, fuzzy_keywords, exact_match=False)
                for result in fuzzy_results:
                    result["search_type"] = "keyword_fuzzy"
                results.extend(fuzzy_results)

            return results

        except Exception as e:
            print(f"关键词搜索异常: {e}")
            return []

    def _merge_and_rerank(
        self, vector_results: List[Dict], keyword_results: List[Dict], query_analysis: Dict, top_k: int
    ) -> List[Dict]:
        """合并和重排序搜索结果"""

        # 根据搜索策略调整权重
        strategy = query_analysis.get("search_strategy", "hybrid")

        if strategy == "keyword_only":
            vector_weight, keyword_weight = 0.1, 0.9
        elif strategy == "vector_only":
            vector_weight, keyword_weight = 0.9, 0.1
        else:  # hybrid
            # 对于混合搜索，如果有关键词结果，增加关键词权重
            if keyword_results:
                vector_weight, keyword_weight = 0.4, 0.6  # 关键词优先
            else:
                vector_weight, keyword_weight = 0.8, 0.2  # 向量搜索为主

        # 重新计算分数
        all_results = []

        for result in vector_results:
            result["final_score"] = result.get("score", 0) * vector_weight
            result["score_components"] = {
                "vector_score": result.get("score", 0),
                "keyword_score": 0,
                "weight": vector_weight,
            }
            all_results.append(result)

        for result in keyword_results:
            # 检查是否与向量搜索结果重复
            is_duplicate = False
            for existing in all_results:
                if self._is_similar_content(existing.get("content", ""), result.get("content", "")):
                    # 如果关键词搜索是精确匹配，优先使用关键词结果
                    if result.get("search_type") == "keyword_exact":
                        existing["final_score"] = (
                            result.get("score", 0) * keyword_weight + existing.get("final_score", 0) * 0.5
                        )
                        existing["search_type"] = "hybrid_keyword_priority"
                    else:
                        # 合并分数
                        existing["final_score"] += result.get("score", 0) * keyword_weight

                    existing["score_components"]["keyword_score"] = result.get("score", 0)
                    if existing.get("search_type") != "hybrid_keyword_priority":
                        existing["search_type"] = "hybrid"
                    is_duplicate = True
                    break

            if not is_duplicate:
                # 对精确匹配的关键词结果给予额外加分
                base_score = result.get("score", 0) * keyword_weight
                if result.get("search_type") == "keyword_exact":
                    base_score *= 1.2  # 精确匹配加成20%

                result["final_score"] = base_score
                result["score_components"] = {
                    "vector_score": 0,
                    "keyword_score": result.get("score", 0),
                    "weight": keyword_weight,
                }
                all_results.append(result)

        # 排序并返回前top_k个结果
        all_results.sort(key=lambda x: x["final_score"], reverse=True)

        final_results = all_results[:top_k]

        # 添加调试信息
        for i, result in enumerate(final_results):
            result["rank"] = i + 1
            print(
                f"结果{i+1}: {result.get('search_type', 'unknown')} "
                f"最终分数={result['final_score']:.4f} "
                f"({result['score_components']})"
            )

        return final_results

    def _is_similar_content(self, content1: str, content2: str, threshold: float = 0.7) -> bool:
        """简单的内容相似性检查"""
        if not content1 or not content2:
            return False

        # 简单的重叠率计算
        set1 = set(content1[:200].split())  # 只比较前200字符的词汇
        set2 = set(content2[:200].split())

        if not set1 or not set2:
            return False

        intersection = len(set1 & set2)
        union = len(set1 | set2)

        similarity = intersection / union if union > 0 else 0
        return similarity >= threshold
