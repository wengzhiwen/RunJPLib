import logging

from utils.mongo_client import get_mongo_client


def ensure_indexes() -> bool:
    """
    Ensure required MongoDB indexes exist.

    Returns True if successful, False otherwise.
    """
    client = get_mongo_client()
    if not client:
        logging.error("ensure_indexes: 无法获取MongoDB客户端")
        return False

    db = client.RunJPLib

    try:
        # universities 复合索引: is_premium 降序 + deadline 降序
        result_name = db.universities.create_index(
            [("is_premium", -1), ("deadline", -1)],
            name="idx_universities_isPremium_deadline_desc",
            background=True,
        )
        logging.info(f"已确保索引存在: universities.{result_name}")

        # access_logs 复合索引: timestamp 降序 + page_type 升序
        result_name_access = db.access_logs.create_index(
            [("timestamp", -1), ("page_type", 1)],
            name="idx_access_logs_timestamp_page_type",
            background=True,
        )
        logging.info(f"已确保索引存在: access_logs.{result_name_access}")

        # processing_tasks 索引: created_at 降序（用于按创建时间排序）
        result_name_tasks = db.processing_tasks.create_index(
            [("created_at", -1)],
            name="idx_processing_tasks_created_at_desc",
            background=True,
        )
        logging.info(f"已确保索引存在: processing_tasks.{result_name_tasks}")

        # processing_tasks 索引: status（用于按状态查询）
        result_name_tasks_status = db.processing_tasks.create_index(
            [("status", 1)],
            name="idx_processing_tasks_status",
            background=True,
        )
        logging.info(f"已确保索引存在: processing_tasks.{result_name_tasks_status}")

        return True
    except Exception as e:
        logging.error(f"创建索引失败: {e}", exc_info=True)
        return False


