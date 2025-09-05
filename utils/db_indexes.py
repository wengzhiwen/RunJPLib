import logging

from utils.mongo_client import get_db


def ensure_indexes() -> bool:
    """
    确保所需的MongoDB索引存在。

    如果成功则返回True，否则返回False。
    """
    db = get_db()
    if db is None:
        logging.error("ensure_indexes: 无法获取MongoDB客户端")
        return False

    try:
        # universities 复合索引: is_premium 降序 + deadline 降序
        result_name = db.universities.create_index(
            [("is_premium", -1), ("deadline", -1)],
            name="idx_universities_isPremium_deadline_desc",
            background=True,
        )
        logging.debug(f"已确保索引存在: universities.{result_name}")

        # access_logs 复合索引: timestamp 降序 + page_type 升序
        result_name_access = db.access_logs.create_index(
            [("timestamp", -1), ("page_type", 1)],
            name="idx_access_logs_timestamp_page_type",
            background=True,
        )
        logging.debug(f"已确保索引存在: access_logs.{result_name_access}")

        # processing_tasks 索引: created_at 降序（用于按创建时间排序）
        result_name_tasks = db.processing_tasks.create_index(
            [("created_at", -1)],
            name="idx_processing_tasks_created_at_desc",
            background=True,
        )
        logging.debug(f"已确保索引存在: processing_tasks.{result_name_tasks}")

        # processing_tasks 索引: status（用于按状态查询）
        result_name_tasks_status = db.processing_tasks.create_index(
            [("status", 1)],
            name="idx_processing_tasks_status",
            background=True,
        )
        logging.debug(f"已确保索引存在: processing_tasks.{result_name_tasks_status}")

        # ip_geo_cache 索引: ip 唯一索引
        result_name_ip_geo = db.ip_geo_cache.create_index(
            [("ip", 1)],
            name="idx_ip_geo_cache_ip_unique",
            unique=True,
            background=True,
        )
        logging.debug(f"已确保索引存在: ip_geo_cache.{result_name_ip_geo}")

        # ip_geo_cache 索引: country_code（用于统计）
        result_name_ip_geo_country = db.ip_geo_cache.create_index(
            [("country_code", 1)],
            name="idx_ip_geo_cache_country_code",
            background=True,
        )
        logging.debug(f"已确保索引存在: ip_geo_cache.{result_name_ip_geo_country}")

        # chat_sessions 索引: user_ip + start_time（用于用户查询和统计）
        result_name_chat_user = db.chat_sessions.create_index(
            [("user_ip", 1), ("start_time", -1)],
            name="idx_chat_sessions_user_ip_start_time",
            background=True,
        )
        logging.debug(f"已确保索引存在: chat_sessions.{result_name_chat_user}")

        # chat_sessions 索引: browser_session_id + university_id + last_activity（用于隐私保护的会话查找）
        result_name_chat_browser = db.chat_sessions.create_index(
            [("browser_session_id", 1), ("university_id", 1), ("last_activity", -1)],
            name="idx_chat_sessions_browser_university_activity",
            background=True,
        )
        logging.debug(f"已确保索引存在: chat_sessions.{result_name_chat_browser}")

        # chat_sessions 索引: university_name + start_time（用于大学统计）
        result_name_chat_uni = db.chat_sessions.create_index(
            [("university_name", 1), ("start_time", -1)],
            name="idx_chat_sessions_university_start_time",
            background=True,
        )
        logging.debug(f"已确保索引存在: chat_sessions.{result_name_chat_uni}")

        # chat_sessions 索引: session_id 唯一索引
        result_name_chat_session = db.chat_sessions.create_index(
            [("session_id", 1)],
            name="idx_chat_sessions_session_id_unique",
            unique=True,
            background=True,
        )
        logging.debug(f"已确保索引存在: chat_sessions.{result_name_chat_session}")

        # chat_sessions 索引: start_time（用于时间范围查询）
        result_name_chat_time = db.chat_sessions.create_index(
            [("start_time", -1)],
            name="idx_chat_sessions_start_time_desc",
            background=True,
        )
        logging.debug(f"已确保索引存在: chat_sessions.{result_name_chat_time}")

        # universities 索引: tags（用于标签筛选）
        result_name_tags = db.universities.create_index(
            [("tags", 1)],
            name="idx_universities_tags",
            background=True,
        )
        logging.debug(f"已确保索引存在: universities.{result_name_tags}")

        # universities 复合索引: tags + is_premium + deadline（用于标签筛选 + 排序）
        result_name_tags_premium_deadline = db.universities.create_index(
            [("tags", 1), ("is_premium", -1), ("deadline", -1)],
            name="idx_universities_tags_premium_deadline",
            background=True,
        )
        logging.debug(f"已确保索引存在: universities.{result_name_tags_premium_deadline}")

        # universities 复合索引: tags + deadline（用于标签筛选 + 截止日期排序）
        result_name_tags_deadline = db.universities.create_index(
            [("tags", 1), ("deadline", -1)],
            name="idx_universities_tags_deadline",
            background=True,
        )
        logging.debug(f"已确保索引存在: universities.{result_name_tags_deadline}")

        return True
    except Exception as e:
        logging.error(f"创建索引失败: {e}", exc_info=True)
        return False
