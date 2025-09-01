"""
聊天记录管理器
负责记录用户聊天历史到MongoDB，实现用户限制和降级机制
"""

from datetime import datetime
from datetime import timedelta
import logging
from typing import Any, Dict, List, Optional

from utils.mongo_client import get_db

logger = logging.getLogger(__name__)


class ChatLoggingManager:
    """聊天记录管理器"""

    def __init__(self):
        """初始化聊天记录管理器"""
        # 初始化完成，暂无需要初始化的属性

    def log_chat_session(self, session_data: Dict) -> str:
        """
        记录聊天会话

        Args:
            session_data: 会话数据

        Returns:
            会话记录ID
        """
        db = get_db()
        if db is None:
            logger.error("数据库连接失败")
            return ""

        try:
            # 会话记录结构
            session_record = {
                "session_id": session_data.get("session_id"),
                "user_ip": session_data.get("user_ip"),
                "browser_session_id": session_data.get("browser_session_id"),
                "university_name": session_data.get("university_name"),
                "university_id": session_data.get("university_id"),
                "start_time": datetime.now(),
                "last_activity": datetime.now(),
                "total_messages": 0,
                "messages": [],
                "user_agent": session_data.get("user_agent", ""),
                "referer": session_data.get("referer", ""),
            }

            result = db.chat_sessions.insert_one(session_record)
            log_id = str(result.inserted_id)

            logger.info(f"记录聊天会话: {log_id}")
            return log_id

        except Exception as e:
            logger.error(f"记录聊天会话时出错: {e}", exc_info=True)
            return ""

    def log_chat_message(
        self, session_id: str, user_input: str, ai_response: str, user_ip: str, processing_time: float = 0
    ) -> bool:
        """
        记录聊天消息

        Args:
            session_id: 会话ID
            user_input: 用户输入
            ai_response: AI回答
            user_ip: 用户IP
            processing_time: 处理时间（秒）

        Returns:
            True如果记录成功，False否则
        """
        db = get_db()
        if db is None:
            logger.error("数据库连接失败")
            return False

        try:
            # 消息记录
            message_record = {
                "timestamp": datetime.now(),
                "user_input": user_input,
                "ai_response": ai_response,
                "processing_time": processing_time,
                "input_length": len(user_input),
                "response_length": len(ai_response),
            }

            # 更新会话记录
            update_result = db.chat_sessions.update_one(
                {"session_id": session_id},
                {
                    "$push": {"messages": message_record},
                    "$inc": {"total_messages": 1},
                    "$set": {"last_activity": datetime.now()},
                },
            )

            if update_result.modified_count > 0:
                logger.info(f"记录聊天消息: {session_id}")
                return True
            else:
                # 如果没有找到会话，创建一个简单的记录
                session_record = {
                    "session_id": session_id,
                    "user_ip": user_ip,
                    "university_name": "未知",
                    "university_id": "",
                    "start_time": datetime.now(),
                    "last_activity": datetime.now(),
                    "total_messages": 1,
                    "messages": [message_record],
                    "user_agent": "",
                    "referer": "",
                }

                db.chat_sessions.insert_one(session_record)
                logger.info(f"创建新会话并记录消息: {session_id}")
                return True

        except Exception as e:
            logger.error(f"记录聊天消息时出错: {e}", exc_info=True)
            return False

    def get_user_daily_message_count(self, user_ip: str) -> int:
        """
        获取用户今日消息数量

        Args:
            user_ip: 用户IP

        Returns:
            今日消息数量
        """
        db = get_db()
        if db is None:
            return 0

        try:
            # 计算今日开始时间
            today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)

            # 聚合查询统计今日消息数
            pipeline = [
                {"$match": {"user_ip": user_ip, "last_activity": {"$gte": today_start}}},
                {"$group": {"_id": None, "total_messages": {"$sum": "$total_messages"}}},
            ]

            result = list(db.chat_sessions.aggregate(pipeline))
            count = result[0]["total_messages"] if result else 0

            logger.debug(f"用户 {user_ip} 今日消息数: {count}")
            return count

        except Exception as e:
            logger.error(f"获取用户消息数时出错: {e}", exc_info=True)
            return 0

    def should_apply_degradation(self, user_ip: str) -> tuple:
        """
        检查是否应该应用降级

        Args:
            user_ip: 用户IP

        Returns:
            (是否降级, 延迟秒数)
        """
        daily_count = self.get_user_daily_message_count(user_ip)

        if daily_count <= 10:
            return False, 0

        # 计算降级次数
        degradation_count = (daily_count - 10) // 5

        if degradation_count > 0:
            # 延迟时间：第一次5秒，之后每次增加5秒，最多60秒
            delay_seconds = min(degradation_count * 5, 60)
            logger.info(f"用户 {user_ip} 触发降级，延迟 {delay_seconds} 秒")
            return True, delay_seconds

        return False, 0

    def get_user_chat_sessions(self, user_ip: str, limit: int = 50) -> List[Dict]:
        """
        获取用户的聊天会话列表

        Args:
            user_ip: 用户IP
            limit: 返回数量限制

        Returns:
            会话列表
        """
        db = get_db()
        if db is None:
            return []

        try:
            sessions = list(
                db.chat_sessions.find(
                    {"user_ip": user_ip},
                    {"session_id": 1, "university_name": 1, "start_time": 1, "last_activity": 1, "total_messages": 1},
                )
                .sort("last_activity", -1)
                .limit(limit)
            )

            # 转换ObjectId为字符串
            for session in sessions:
                session["_id"] = str(session["_id"])

            return sessions

        except Exception as e:
            logger.error(f"获取用户会话列表时出错: {e}", exc_info=True)
            return []

    def get_active_session_for_university(
        self, user_ip: str, university_id: str, browser_session_id: str = None, timeout_hours: int = 1
    ) -> Optional[Dict]:
        """
        获取用户在特定大学的活跃会话

        Args:
            user_ip: 用户IP
            university_id: 大学ID
            browser_session_id: 浏览器会话ID（用于隐私保护）
            timeout_hours: 会话超时时间（小时）

        Returns:
            活跃会话信息，如果没有则返回None
        """
        db = get_db()
        if db is None:
            return None

        try:
            # 计算超时时间
            timeout_time = datetime.now() - timedelta(hours=timeout_hours)

            # 构建查询条件 - 优先使用浏览器会话ID，回退到IP地址
            query = {"university_id": university_id, "last_activity": {"$gte": timeout_time}}

            if browser_session_id:
                # 如果有浏览器会话ID，优先使用它来查找
                query["browser_session_id"] = browser_session_id
            else:
                # 回退到IP地址查找（兼容旧会话）
                query["user_ip"] = user_ip

            # 查找该用户在该大学的最新活跃会话
            session = db.chat_sessions.find_one(query, sort=[("last_activity", -1)])

            if session:
                session["_id"] = str(session["_id"])
                logger.info(f"找到用户 {user_ip} 在大学 {university_id} 的活跃会话: {session['session_id']}")
                return session

            return None

        except Exception as e:
            logger.error(f"获取活跃会话时出错: {e}", exc_info=True)
            return None

    def get_chat_session_detail(self, session_id: str) -> Optional[Dict]:
        """
        获取聊天会话详情

        Args:
            session_id: 会话ID

        Returns:
            会话详情，如果不存在则返回None
        """
        db = get_db()
        if db is None:
            return None

        try:
            session = db.chat_sessions.find_one({"session_id": session_id})

            if session:
                session["_id"] = str(session["_id"])
                return session

            return None

        except Exception as e:
            logger.error(f"获取会话详情时出错: {e}", exc_info=True)
            return None

    def get_all_chat_sessions(
        self, skip: int = 0, limit: int = 50, start_date: Optional[datetime] = None, end_date: Optional[datetime] = None
    ) -> List[Dict]:
        """
        获取所有聊天会话（管理员用）

        Args:
            skip: 跳过数量
            limit: 返回数量限制
            start_date: 开始日期
            end_date: 结束日期

        Returns:
            会话列表
        """
        db = get_db()
        if db is None:
            return []

        try:
            # 构建查询条件
            query = {}
            if start_date or end_date:
                query["start_time"] = {}
                if start_date:
                    query["start_time"]["$gte"] = start_date
                if end_date:
                    query["start_time"]["$lte"] = end_date

            sessions = list(
                db.chat_sessions.find(
                    query,
                    {
                        "session_id": 1,
                        "user_ip": 1,
                        "university_name": 1,
                        "start_time": 1,
                        "last_activity": 1,
                        "total_messages": 1,
                        "user_agent": 1,
                    },
                )
                .sort("start_time", -1)
                .skip(skip)
                .limit(limit)
            )

            # 转换ObjectId为字符串
            for session in sessions:
                session["_id"] = str(session["_id"])

            return sessions

        except Exception as e:
            logger.error(f"获取所有会话列表时出错: {e}", exc_info=True)
            return []

    def get_chat_statistics(self) -> Dict[str, Any]:
        """
        获取聊天统计信息

        Returns:
            统计信息字典
        """
        db = get_db()
        if db is None:
            return {}

        try:
            # 计算时间范围
            today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
            week_start = today_start - timedelta(days=7)
            month_start = today_start - timedelta(days=30)

            # 总会话数
            total_sessions = db.chat_sessions.count_documents({})

            # 今日会话数
            today_sessions = db.chat_sessions.count_documents({"start_time": {"$gte": today_start}})

            # 本周会话数
            week_sessions = db.chat_sessions.count_documents({"start_time": {"$gte": week_start}})

            # 本月会话数
            month_sessions = db.chat_sessions.count_documents({"start_time": {"$gte": month_start}})

            # 总消息数
            total_messages_result = list(
                db.chat_sessions.aggregate([{"$group": {"_id": None, "total": {"$sum": "$total_messages"}}}])
            )
            total_messages = total_messages_result[0]["total"] if total_messages_result else 0

            # 活跃用户数（本周）
            active_users = len(db.chat_sessions.distinct("user_ip", {"last_activity": {"$gte": week_start}}))

            # 热门大学（本月）
            popular_universities = list(
                db.chat_sessions.aggregate(
                    [
                        {"$match": {"start_time": {"$gte": month_start}}},
                        {"$group": {"_id": "$university_name", "count": {"$sum": 1}}},
                        {"$sort": {"count": -1}},
                        {"$limit": 10},
                    ]
                )
            )

            return {
                "total_sessions": total_sessions,
                "today_sessions": today_sessions,
                "week_sessions": week_sessions,
                "month_sessions": month_sessions,
                "total_messages": total_messages,
                "active_users": active_users,
                "popular_universities": popular_universities,
            }

        except Exception as e:
            logger.error(f"获取聊天统计时出错: {e}", exc_info=True)
            return {}

    def cleanup_old_sessions(self, days: int = 90) -> int:
        """
        清理旧的聊天会话

        Args:
            days: 保留天数

        Returns:
            删除的会话数量
        """
        db = get_db()
        if db is None:
            return 0

        try:
            cutoff_date = datetime.now() - timedelta(days=days)

            result = db.chat_sessions.delete_many({"start_time": {"$lt": cutoff_date}})

            deleted_count = result.deleted_count
            logger.info(f"清理了 {deleted_count} 个超过 {days} 天的聊天会话")

            return deleted_count

        except Exception as e:
            logger.error(f"清理聊天会话时出错: {e}", exc_info=True)
            return 0


# 全局实例
chat_logger = ChatLoggingManager()
