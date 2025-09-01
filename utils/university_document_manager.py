"""
大学文档管理器
负责管理大学招生信息文档的获取和验证
"""
import logging
from datetime import datetime
from typing import Dict, Optional, List
from bson.objectid import ObjectId

from utils.mongo_client import get_db

logger = logging.getLogger(__name__)


class UniversityDocumentManager:
    """大学文档管理器"""

    def __init__(self):
        """初始化文档管理器"""
        self.index_cache = {}  # 缓存已构建的索引信息

    def get_latest_university_doc(self, university_name: str) -> Optional[Dict]:
        """
        获取大学最新的招生信息文档
        
        Args:
            university_name: 大学名称
            
        Returns:
            大学文档字典，如果未找到则返回None
        """
        db = get_db()
        if db is None:
            logger.error("数据库连接失败")
            return None

        try:
            # 按deadline降序排序，获取最新的文档
            doc = db.universities.find_one({"university_name": university_name}, sort=[("deadline", -1)])

            if doc:
                logger.info(f"获取到大学文档: {university_name}")
                return doc
            else:
                logger.warning(f"未找到大学文档: {university_name}")
                return None

        except Exception as e:
            logger.error(f"获取大学文档时出错: {e}", exc_info=True)
            return None

    def get_university_by_id(self, university_id: str) -> Optional[Dict]:
        """
        根据ID获取大学文档
        
        Args:
            university_id: 大学文档ID
            
        Returns:
            大学文档字典，如果未找到则返回None
        """
        db = get_db()
        if db is None:
            logger.error("数据库连接失败")
            return None

        try:
            obj_id = ObjectId(university_id)
            doc = db.universities.find_one({"_id": obj_id})

            if doc:
                logger.info(f"获取到大学文档 ID: {university_id}")
                return doc
            else:
                logger.warning(f"未找到大学文档 ID: {university_id}")
                return None

        except Exception as e:
            logger.error(f"获取大学文档时出错: {e}", exc_info=True)
            return None

    def search_universities(self, query: str, limit: int = 10) -> List[Dict]:
        """
        搜索大学
        
        Args:
            query: 搜索关键词
            limit: 返回结果数量限制
            
        Returns:
            匹配的大学列表
        """
        db = get_db()
        if db is None:
            logger.error("数据库连接失败")
            return []

        try:
            # 如果查询为空，返回所有大学（限制数量）
            if not query.strip():
                cursor = db.universities.find({}, {
                    "_id": 1,
                    "university_name": 1,
                    "university_name_zh": 1,
                    "deadline": 1,
                    "is_premium": 1
                }).sort([("is_premium", -1), ("deadline", -1)]).limit(limit)
            else:
                # 构建搜索条件：支持日文名称和中文名称搜索
                search_pattern = {"$regex": query, "$options": "i"}
                search_conditions = {"$or": [{"university_name": search_pattern}, {"university_name_zh": search_pattern}]}

                # 搜索大学，返回基本信息
                cursor = db.universities.find(search_conditions, {
                    "_id": 1,
                    "university_name": 1,
                    "university_name_zh": 1,
                    "deadline": 1,
                    "is_premium": 1
                }).sort([("is_premium", -1), ("deadline", -1)]).limit(limit)

            results = list(cursor)
            logger.info(f"搜索大学 '{query}' 返回 {len(results)} 个结果")

            return results

        except Exception as e:
            logger.error(f"搜索大学时出错: {e}", exc_info=True)
            return []

    def get_all_universities(self, limit: int = 50) -> List[Dict]:
        """
        获取所有大学列表（用于选择器）
        
        Args:
            limit: 返回结果数量限制
            
        Returns:
            大学列表
        """
        db = get_db()
        if db is None:
            logger.error("数据库连接失败")
            return []

        try:
            cursor = db.universities.find({}, {
                "_id": 1,
                "university_name": 1,
                "university_name_zh": 1,
                "deadline": 1,
                "is_premium": 1
            }).sort([("is_premium", -1), ("deadline", -1)]).limit(limit)

            results = list(cursor)
            logger.info(f"获取所有大学列表，返回 {len(results)} 个结果")

            return results

        except Exception as e:
            logger.error(f"获取大学列表时出错: {e}", exc_info=True)
            return []

    def needs_reindex(self, university_id: str, last_updated: Optional[datetime] = None) -> bool:
        """
        检查是否需要重新索引
        
        Args:
            university_id: 大学ID
            last_updated: 上次更新时间
            
        Returns:
            True如果需要重新索引，False否则
        """
        # 检查缓存中是否有索引信息
        cache_key = f"index_{university_id}"

        if cache_key not in self.index_cache:
            logger.info(f"大学 {university_id} 无索引缓存，需要重新索引")
            return True

        cached_info = self.index_cache[cache_key]

        # 如果提供了last_updated，检查是否有更新
        if last_updated and cached_info.get("last_indexed"):
            if last_updated > cached_info["last_indexed"]:
                logger.info(f"大学 {university_id} 文档已更新，需要重新索引")
                return True

        logger.info(f"大学 {university_id} 索引是最新的")
        return False

    def mark_indexed(self, university_id: str) -> None:
        """
        标记大学已被索引
        
        Args:
            university_id: 大学ID
        """
        cache_key = f"index_{university_id}"
        self.index_cache[cache_key] = {"last_indexed": datetime.now(), "status": "completed"}
        logger.info(f"标记大学 {university_id} 已完成索引")

    def extract_content_for_indexing(self, university_doc: Dict) -> List[Dict]:
        """
        提取大学文档中用于索引的内容
        
        Args:
            university_doc: 大学文档
            
        Returns:
            包含文本块的列表，每个文本块都有相应的元数据
        """
        chunks = []
        content = university_doc.get('content', {})
        university_name = university_doc.get('university_name', '未知大学')
        university_id = str(university_doc.get('_id', ''))
        deadline = university_doc.get('deadline', '')

        # 处理原始markdown内容
        original_md = content.get('original_md', '')
        if original_md:
            chunks.extend(
                self._split_content(content=original_md,
                                    content_type='original',
                                    university_name=university_name,
                                    university_id=university_id,
                                    deadline=deadline,
                                    language='japanese'))

        # 处理翻译markdown内容
        translated_md = content.get('translated_md', '')
        if translated_md:
            chunks.extend(
                self._split_content(content=translated_md,
                                    content_type='translated',
                                    university_name=university_name,
                                    university_id=university_id,
                                    deadline=deadline,
                                    language='chinese'))

        # 处理报告markdown内容
        report_md = content.get('report_md', '')
        if report_md:
            chunks.extend(
                self._split_content(content=report_md,
                                    content_type='report',
                                    university_name=university_name,
                                    university_id=university_id,
                                    deadline=deadline,
                                    language='chinese'))

        logger.info(f"从大学 {university_name} 提取了 {len(chunks)} 个文本块")
        return chunks

    def _split_content(self, content: str, content_type: str, university_name: str, university_id: str, deadline: str, language: str) -> List[Dict]:
        """
        分割内容为文本块
        
        Args:
            content: 要分割的内容
            content_type: 内容类型 (original/translated/report)
            university_name: 大学名称
            university_id: 大学ID
            deadline: 截止日期
            language: 语言 (japanese/chinese)
            
        Returns:
            文本块列表
        """
        if not content.strip():
            return []

        # 按段落分割，每个段落作为一个块
        paragraphs = content.split('\n\n')
        chunks = []

        for i, paragraph in enumerate(paragraphs):
            if paragraph.strip():
                # 如果段落太长，进一步分割
                if len(paragraph) > 1000:
                    # 按句子分割
                    sentences = paragraph.split('。' if language == 'chinese' else '。')
                    current_chunk = ""

                    for sentence in sentences:
                        if len(current_chunk + sentence) > 800:
                            if current_chunk:
                                chunks.append(
                                    self._create_chunk(content=current_chunk,
                                                       chunk_index=len(chunks),
                                                       content_type=content_type,
                                                       university_name=university_name,
                                                       university_id=university_id,
                                                       deadline=deadline,
                                                       language=language))
                            current_chunk = sentence
                        else:
                            current_chunk += sentence

                    if current_chunk:
                        chunks.append(
                            self._create_chunk(content=current_chunk,
                                               chunk_index=len(chunks),
                                               content_type=content_type,
                                               university_name=university_name,
                                               university_id=university_id,
                                               deadline=deadline,
                                               language=language))
                else:
                    chunks.append(
                        self._create_chunk(content=paragraph,
                                           chunk_index=i,
                                           content_type=content_type,
                                           university_name=university_name,
                                           university_id=university_id,
                                           deadline=deadline,
                                           language=language))

        return chunks

    def _create_chunk(self, content: str, chunk_index: int, content_type: str, university_name: str, university_id: str, deadline: str, language: str) -> Dict:
        """
        创建文本块对象
        
        Args:
            content: 文本内容
            chunk_index: 块索引
            content_type: 内容类型
            university_name: 大学名称
            university_id: 大学ID
            deadline: 截止日期
            language: 语言
            
        Returns:
            文本块字典
        """
        # 提取标题（取内容的前50个字符作为标题）
        title = content[:50].strip()
        if len(content) > 50:
            title += "..."

        return {
            "content": content,
            "metadata": {
                "university_id": university_id,
                "university_name": university_name,
                "content_type": content_type,
                "chunk_index": chunk_index,
                "title": title,
                "language": language,
                "deadline": deadline
            }
        }
