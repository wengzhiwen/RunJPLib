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
        return True
    except Exception as e:
        logging.error(f"创建索引失败: {e}", exc_info=True)
        return False


