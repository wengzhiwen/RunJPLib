"""
大学文档管理器
负责管理大学招生信息文档的获取和验证
"""
import logging
from typing import Dict, List, Optional

from bson.objectid import ObjectId

from ..core.database import get_db

logger = logging.getLogger(__name__)


class UniversityRepository:
    """大学文档仓库"""

    def __init__(self):
        """初始化文档管理器"""
        # 注意：此处不设置任何实例级缓存，以避免多进程环境下的状态不一致问题。
        pass

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